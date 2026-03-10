import { config } from 'dotenv';
import { createDb, runMigrations, type Database } from './db/index.js';
import { MessageBus } from './message-bus.js';
import { StateStore } from './state-store.js';
import { GitService, type GitServiceConfig } from './git-service/index.js';
import { BoardWatcher } from './board-watcher.js';
import { SystemController } from './system-controller.js';
import { startCLI } from './cli.js';
import { createLogger } from './logger.js';
import type { BaseAgent } from './base-agent.js';
import type { AgentDependencies } from './base-agent.js';
import type { UserInput } from './types/index.js';

const log = createLogger('Bootstrap');

export interface SystemContext {
  db: Database;
  stateStore: StateStore;
  messageBus: MessageBus;
  gitService: GitService;
  boardWatcher: BoardWatcher;
  systemController: SystemController;
  agents: BaseAgent[];
  deps: AgentDependencies;
  /** 시작된 리소스를 안전하게 정리한다. */
  shutdown: () => Promise<void>;
}

export type AgentFactory = (deps: AgentDependencies) => BaseAgent | Promise<BaseAgent>;

export interface BootstrapConfig {
  /** Agent factory functions. Key is agent id. */
  agents: Record<string, AgentFactory>;
  /** Skip GitHub validation (for testing). */
  skipGitValidation?: boolean;
  /** Skip CLI (for testing or programmatic use). */
  skipCLI?: boolean;
  /** Skip BoardWatcher auto-start. */
  skipBoardWatcher?: boolean;
  /** Skip DB migration (if already migrated). */
  skipMigration?: boolean;
}

/**
 * 시스템 부트스트랩. 순서대로 초기화하고 SystemContext를 반환한다.
 * Agent 생성은 외부에서 factory로 주입 — 패키지 간 의존성을 core에 넣지 않기 위함.
 * 초기화 도중 에러 발생 시 이미 시작된 리소스를 정리하고 에러를 다시 던진다.
 */
export async function bootstrap(cfg: BootstrapConfig): Promise<SystemContext> {
  // 이미 시작된 리소스 추적 (에러 시 cleanup용)
  let db: Database | null = null;
  let stateStore: StateStore | null = null;
  let boardWatcher: BoardWatcher | null = null;
  const startedAgents: BaseAgent[] = [];
  const registeredAgentIds: string[] = [];

  async function cleanupInternal() {
    // 역순 정리: agents → boardWatcher → agent DB status → db
    for (const agent of startedAgents) {
      agent.stopPolling();
    }
    boardWatcher?.stop();

    // 등록된 에이전트 상태를 offline으로 변경
    if (stateStore) {
      for (const agentId of registeredAgentIds) {
        try {
          await stateStore.updateAgentStatus(agentId, 'offline');
        } catch (err) {
          log.error({ err, agentId }, 'Failed to set agent offline');
        }
      }
    }

    if (db) {
      // Drizzle pg Pool 종료
      try {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        await (db as any).$client?.end?.();
      } catch (err) {
        log.error({ err }, 'Failed to close DB pool');
      }
    }
  }

  const CLEANUP_TIMEOUT_MS = 10_000;

  async function cleanup() {
    await Promise.race([
      cleanupInternal(),
      new Promise<void>((resolve) =>
        setTimeout(() => {
          log.error('Cleanup timed out, forcing exit');
          resolve();
        }, CLEANUP_TIMEOUT_MS),
      ),
    ]);
  }

  try {
    // 1. 환경 변수 로드
    config();
    log.info('Configuration loaded');

    // 2. PostgreSQL 초기화
    const databaseUrl = process.env.DATABASE_URL;
    if (!databaseUrl) throw new Error('DATABASE_URL is required');
    db = createDb(databaseUrl);
    if (!cfg.skipMigration) {
      await runMigrations(db, './drizzle');
      log.info('Database migrations applied');
    }
    stateStore = new StateStore(db);
    log.info('Database connected');

    // 3. MessageBus 생성 (stateStore 연결로 메시지 자동 DB 저장)
    const messageBus = new MessageBus(stateStore);
    log.info('MessageBus created');

    // 4. GitService 생성
    const gitConfig: GitServiceConfig = {
      token: process.env.GITHUB_TOKEN ?? '',
      owner: process.env.GITHUB_OWNER ?? '',
      repo: process.env.GITHUB_REPO ?? '',
      projectNumber: Number(process.env.GITHUB_PROJECT_NUMBER) || undefined,
    };
    const gitService = new GitService(gitConfig);

    if (!cfg.skipGitValidation) {
      await gitService.validateConnection();
      log.info('GitService connected');
    }

    // 5. 공유 의존성
    const deps: AgentDependencies = { messageBus, stateStore, gitService };

    // 6. BoardWatcher 생성
    boardWatcher = new BoardWatcher(gitService, stateStore, messageBus);
    if (!cfg.skipBoardWatcher) {
      boardWatcher.start();
      log.info('BoardWatcher started');
    }

    // 7. 에이전트 등록
    const agents: BaseAgent[] = [];
    for (const [id, factory] of Object.entries(cfg.agents)) {
      const agent = await factory(deps);
      await stateStore.registerAgent({
        id: agent.id,
        domain: agent.domain,
        level: agent.config.level,
        status: 'idle',
      });
      registeredAgentIds.push(agent.id);
      agents.push(agent);
      log.info({ agentId: id }, 'Agent registered');
    }

    // 8. SystemController
    const systemController = new SystemController(agents, stateStore);

    // 9. 에이전트 폴링 시작
    for (const agent of agents) {
      agent.startPolling();
      startedAgents.push(agent);
    }
    log.info({ agentCount: agents.length }, 'Agents polling');

    // 10. CLI
    if (!cfg.skipCLI) {
      const director = agents.find((a) => a.id === 'director');

      if (!director) {
        log.warn('Director agent not found — CLI will only accept system commands');
      }

      startCLI({
        systemController,
        onDirectorInput: director
          ? (input: UserInput) =>
              messageBus.publish({
                id: crypto.randomUUID(),
                type: 'user.input',
                from: 'cli',
                to: 'director',
                payload: input,
                traceId: crypto.randomUUID(),
                timestamp: new Date(),
              })
          : null,
      });
      log.info('CLI ready');
    }

    // OS 시그널 핸들링 — Ctrl+C / kill 시 자동 정리
    let shuttingDown = false;
    const signalHandler = async () => {
      if (shuttingDown) return; // 중복 호출 방지
      shuttingDown = true;
      log.info('Signal received, shutting down...');
      await cleanup();
      process.exit(0);
    };
    process.on('SIGINT', signalHandler);
    process.on('SIGTERM', signalHandler);

    log.info('System ready');

    return {
      db,
      stateStore,
      messageBus,
      gitService,
      boardWatcher,
      systemController,
      agents,
      deps,
      shutdown: async () => {
        // 수동 shutdown 호출 시 시그널 핸들러 제거
        process.removeListener('SIGINT', signalHandler);
        process.removeListener('SIGTERM', signalHandler);
        await cleanup();
      },
    };
  } catch (error) {
    log.error('Startup failed, cleaning up...');
    await cleanup();
    throw error;
  }
}
