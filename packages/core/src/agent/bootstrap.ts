import { resolve, dirname } from 'path';
import { existsSync } from 'fs';
import { fileURLToPath } from 'url';
import { createDb, runMigrations, type Database, type DbConnection } from '../db/index.js';
import { MessageBus } from '../messaging/message-bus.js';
import { StateStore } from '../state/state-store.js';
import { GitService, type GitServiceConfig } from '../git-service/index.js';
import { BoardWatcher } from '../board/board-watcher.js';
import { SystemController } from './system-controller.js';
import { OrphanCleaner } from '../resilience/orphan-cleaner.js';
import { HookRegistry } from '../hooks/hook-registry.js';
import { registerBuiltInHooks } from '../hooks/built-in-hooks.js';
import { startCLI } from './cli.js';
import { createLogger } from '../logging/logger.js';
import { loadConfig, type AppConfig } from '../config.js';
import type { BaseAgent } from './base-agent.js';
import type { AgentDependencies } from './base-agent.js';
import type { UserInput } from '../types/index.js';

/**
 * @agent/core 패키지 루트 기준 drizzle 마이그레이션 폴더 절대경로.
 * tsup 번들(dist/index.js) → ../drizzle, dev tsx(src/agent/bootstrap.ts) → ../../drizzle
 */
function findMigrationsDir(): string {
  const thisDir = dirname(fileURLToPath(import.meta.url));
  const candidates = [
    resolve(thisDir, '../drizzle'),
    resolve(thisDir, '../../drizzle'),
  ];
  const found = candidates.find((d) => existsSync(resolve(d, 'meta/_journal.json')));
  if (!found) {
    throw new Error(
      `Cannot find drizzle migrations directory (from ${thisDir}). Searched: ${candidates.join(', ')}`,
    );
  }
  return found;
}

const log = createLogger('Bootstrap');

export interface SystemContext {
  db: Database;
  stateStore: StateStore;
  messageBus: MessageBus;
  gitService: GitService;
  boardWatcher: BoardWatcher;
  systemController: SystemController;
  hookRegistry: HookRegistry;
  agents: BaseAgent[];
  deps: AgentDependencies;
  /** 시작된 리소스를 안전하게 정리한다. */
  shutdown: () => Promise<void>;
}

export type AgentFactory = (deps: AgentDependencies) => BaseAgent | Promise<BaseAgent>;

export interface BootstrapConfig {
  /** Agent factory functions. Key is agent id. */
  agents: Record<string, AgentFactory>;
  /** Pre-loaded configuration. If omitted, loadConfig() is called internally. */
  appConfig?: AppConfig;
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
  let dbConn: DbConnection | null = null;
  let stateStore: StateStore | null = null;
  let boardWatcher: BoardWatcher | null = null;
  let orphanCleaner: OrphanCleaner | null = null;
  const startedAgents: BaseAgent[] = [];
  const registeredAgentIds: string[] = [];

  async function cleanupInternal() {
    // 역순 정리: agents → orphanCleaner → boardWatcher → agent DB status → db
    // drain()은 in-flight 작업이 끝날 때까지 대기한다.
    // Promise.allSettled: 하나의 agent drain 실패가 나머지 drain을 막지 않도록 한다.
    const drainResults = await Promise.allSettled(startedAgents.map((agent) => agent.drain()));
    for (let i = 0; i < drainResults.length; i++) {
      const r = drainResults[i];
      if (r && r.status === 'rejected') {
        log.error({ err: r.reason, agentId: startedAgents[i]?.id }, 'Agent drain failed');
      }
    }
    orphanCleaner?.stop();
    if (boardWatcher) {
      await boardWatcher.drain();
    }

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

    if (dbConn) {
      try {
        await dbConn.close();
      } catch (err) {
        log.error({ err }, 'Failed to close DB pool');
      }
    }
  }

  const CLEANUP_TIMEOUT_MS = 10_000;

  async function cleanup(): Promise<boolean> {
    let timedOut = false;
    await Promise.race([
      cleanupInternal(),
      new Promise<void>((resolve) =>
        setTimeout(() => {
          timedOut = true;
          log.error('Cleanup timed out, forcing exit');
          resolve();
        }, CLEANUP_TIMEOUT_MS),
      ),
    ]);
    return timedOut;
  }

  // OS 시그널 핸들링 — try 밖에 선언하여 catch에서도 접근 가능
  let shuttingDown = false;
  const signalHandler = async () => {
    if (shuttingDown) return;
    shuttingDown = true;
    log.info('Signal received, shutting down...');
    const timedOut = await cleanup();
    process.exit(timedOut ? 1 : 0);
  };

  try {
    // 1. 설정 로드 (외부에서 주입하거나 환경변수에서 자동 로드)
    const appConfig = cfg.appConfig ?? loadConfig();
    log.info('Configuration loaded');

    // 2. PostgreSQL 초기화
    dbConn = createDb(appConfig.database.url);
    const db = dbConn.db;
    if (!cfg.skipMigration) {
      await runMigrations(db, findMigrationsDir());
      log.info('Database migrations applied');
    }
    stateStore = new StateStore(db);
    log.info('Database connected');

    // 3. MessageBus 생성 (stateStore 연결로 메시지 자동 DB 저장)
    const messageBus = new MessageBus(stateStore);
    log.info('MessageBus created');

    // 4. GitService 생성
    const gitConfig: GitServiceConfig = {
      token: appConfig.github.token,
      owner: appConfig.github.owner,
      repo: appConfig.github.repo,
      projectNumber: appConfig.github.projectNumber,
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

    // 6.5. OrphanCleaner 생성 — 죽은 에이전트의 클레임 해제
    orphanCleaner = new OrphanCleaner(stateStore);
    orphanCleaner.start();
    log.info('OrphanCleaner started');

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

    // 8.5 HookRegistry — 내장 훅 등록
    const hookRegistry = new HookRegistry(stateStore);
    await registerBuiltInHooks(hookRegistry, messageBus);
    log.info('HookRegistry initialized with built-in hooks');

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

    // 시그널 핸들러 등록 (try 밖에서 선언됨)
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
      hookRegistry,
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
    process.removeListener('SIGINT', signalHandler);
    process.removeListener('SIGTERM', signalHandler);
    await cleanup();
    throw error;
  }
}
