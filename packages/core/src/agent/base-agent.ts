import type {
  AgentConfig,
  IMessageBus,
  IStateStore,
  IGitService,
  MessageHandler,
  Task,
  TaskResult,
  TaskRow,
} from '../types/index.js';
import { MESSAGE_TYPES } from '../types/index.js';
import { createLogger, type Logger } from '../logging/logger.js';

export interface AgentDependencies {
  messageBus: IMessageBus;
  stateStore: IStateStore;
  gitService: IGitService;
}

export type AgentStatus = 'idle' | 'busy' | 'paused' | 'error';

const DEFAULT_TASK_TIMEOUT_MS = 5 * 60 * 1000; // 5분
const MAX_BACKOFF_MS = 60_000; // 최대 1분
const HEARTBEAT_INTERVAL_CYCLES = 3; // 3 poll cycle마다 heartbeat

export abstract class BaseAgent {
  readonly id: string;
  readonly domain: string;
  readonly config: AgentConfig;

  private polling = false;
  private _status: AgentStatus = 'idle';
  private consecutiveErrors = 0;
  private abortController: AbortController | null = null;
  private pollPromise: Promise<void> | null = null;
  private configHandler: MessageHandler;

  protected messageBus: IMessageBus;
  protected stateStore: IStateStore;
  protected gitService: IGitService;
  protected log: Logger;

  constructor(config: AgentConfig, deps: AgentDependencies) {
    this.id = config.id;
    this.domain = config.domain;
    this.config = config;
    this.messageBus = deps.messageBus;
    this.stateStore = deps.stateStore;
    this.gitService = deps.gitService;
    this.log = createLogger(config.id);

    // Subscribe to config updates for hot-reload (store ref for unsubscribe)
    this.configHandler = (msg) => {
      const payload = msg.payload as { agentId: string };
      if (payload.agentId === this.id) {
        this.reloadConfig().catch((err) => {
          this.log.error({ err }, 'Failed to reload config');
        });
      }
    };
    this.messageBus.subscribe(MESSAGE_TYPES.AGENT_CONFIG_UPDATED, this.configHandler);
  }

  /**
   * DB에서 최신 설정을 로드하여 config 객체를 갱신한다.
   * agent.config.updated 메시지 수신 시 자동 호출.
   */
  async reloadConfig(): Promise<void> {
    const dbConfig = await this.stateStore.getAgentConfig(this.id);
    if (!dbConfig) return;

    const mutableConfig = this.config as unknown as Record<string, unknown>;
    mutableConfig.claudeModel = dbConfig.claudeModel;
    mutableConfig.maxTokens = dbConfig.maxTokens;
    mutableConfig.temperature = dbConfig.temperature;
    mutableConfig.tokenBudget = dbConfig.tokenBudget;
    mutableConfig.taskTimeoutMs = dbConfig.taskTimeoutMs;
    mutableConfig.pollIntervalMs = dbConfig.pollIntervalMs;

    this.log.info({ config: dbConfig }, 'Config reloaded');
  }

  get status(): AgentStatus {
    return this._status;
  }

  protected async setStatus(status: AgentStatus, taskId?: string): Promise<void> {
    this._status = status;
    await this.messageBus.publish({
      id: crypto.randomUUID(),
      type: MESSAGE_TYPES.AGENT_STATUS,
      from: this.id,
      to: null,
      payload: { status, ...(taskId ? { taskId } : {}) },
      traceId: crypto.randomUUID(),
      timestamp: new Date(),
    });
  }

  /**
   * Claude API 호출 후 토큰 사용량을 MessageBus에 발행한다.
   * Dashboard에서 에이전트별 토큰 사용량 추적에 사용.
   */
  protected async publishTokenUsage(inputTokens: number, outputTokens: number): Promise<void> {
    await this.messageBus.publish({
      id: crypto.randomUUID(),
      type: MESSAGE_TYPES.TOKEN_USAGE,
      from: this.id,
      to: null,
      payload: { inputTokens, outputTokens },
      traceId: crypto.randomUUID(),
      timestamp: new Date(),
    });
  }

  /**
   * Board에서 자신의 도메인 태스크를 폴링하여 실행하는 루프를 시작한다.
   * setTimeout 재귀 방식으로 이전 실행 완료 후에만 다음 폴링이 시작된다.
   * @param intervalMs 폴링 주기 (기본 10초)
   */
  startPolling(intervalMs = 10_000) {
    if (this.polling) return;
    this.polling = true;
    this.abortController = new AbortController();
    this.pollPromise = this.pollLoop(intervalMs);
  }

  stopPolling() {
    this.polling = false;
    this.abortController?.abort();
  }

  /**
   * 현재 실행 중인 태스크가 끝날 때까지 대기한 후 폴링을 멈춘다.
   * Graceful shutdown 시 사용.
   */
  async drain(): Promise<void> {
    this.stopPolling();
    this.messageBus.unsubscribe(MESSAGE_TYPES.AGENT_CONFIG_UPDATED, this.configHandler);
    if (this.pollPromise) {
      await this.pollPromise;
      this.pollPromise = null;
    }
  }

  /**
   * 에이전트를 일시정지한다. 폴링 중지 + 상태를 paused로 변경.
   */
  async pause(): Promise<void> {
    this.stopPolling();
    await this.setStatus('paused');
  }

  /**
   * 에이전트를 재개한다. 상태를 idle로 변경 + 폴링 시작.
   */
  async resume(intervalMs = 10_000): Promise<void> {
    await this.setStatus('idle');
    this.startPolling(intervalMs);
  }

  private async pollLoop(initialIntervalMs: number) {
    let cycleCount = 0;
    const signal = this.abortController?.signal;

    while (this.polling) {
      // 하트비트: N cycle마다 DB에 생존 신호
      if (++cycleCount % HEARTBEAT_INTERVAL_CYCLES === 0) {
        try {
          await this.stateStore.updateHeartbeat(this.id);
        } catch (err) {
          this.log.error({ err }, 'Heartbeat failed');
        }
      }

      if (this._status === 'idle' || this._status === 'error') {
        try {
          // error 상태에서 자동 복구 시도
          if (this._status === 'error') {
            this.log.info('Recovering from error state');
            await this.setStatus('idle');
          }

          const task = await this.findNextTask();
          if (task) {
            await this.setStatus('busy', task.id);
            const result = await this.executeTaskWithTimeout(task);
            await this.onTaskComplete(task, result);
            await this.setStatus('idle');
            this.consecutiveErrors = 0; // 성공 시 리셋
          }
        } catch (error) {
          this.consecutiveErrors++;
          await this.setStatus('error');
          this.log.error(
            { err: error, consecutiveErrors: this.consecutiveErrors },
            'Polling error',
          );
        }
      }

      // Read current poll interval dynamically (hot-reload support)
      const currentIntervalMs = (this.config as unknown as Record<string, unknown>).pollIntervalMs as number | undefined ?? initialIntervalMs;

      // 지수 백오프: 연속 에러 시 대기 시간 증가
      const backoff =
        this.consecutiveErrors > 0
          ? Math.min(currentIntervalMs * Math.pow(2, this.consecutiveErrors - 1), MAX_BACKOFF_MS)
          : currentIntervalMs;

      // AbortController signal로 즉시 깨어남 — graceful shutdown 지원
      await abortableSleep(backoff, signal);
    }
  }

  /**
   * executeTask에 타임아웃을 적용한다. 무한 hang 방지.
   */
  private async executeTaskWithTimeout(task: Task): Promise<TaskResult> {
    const timeoutMs = this.config.taskTimeoutMs ?? DEFAULT_TASK_TIMEOUT_MS;

    let timer: ReturnType<typeof setTimeout>;
    const timeoutPromise = new Promise<TaskResult>((_, reject) => {
      timer = setTimeout(
        () => reject(new Error(`Task "${task.title}" timed out after ${timeoutMs}ms`)),
        timeoutMs,
      );
    });

    try {
      return await Promise.race([this.executeTask(task), timeoutPromise]);
    } finally {
      clearTimeout(timer!);
    }
  }

  /**
   * 특정 메시지 타입을 구독한다.
   */
  protected subscribe(type: string, handler: MessageHandler) {
    this.messageBus.subscribe(type, handler);
  }

  /**
   * DB에서 Ready 컬럼의 자기 도메인 태스크 중 우선순위가 가장 높은 것을 가져온다.
   * BoardWatcher가 GitHub Board → DB 동기화를 담당하므로, Agent는 DB만 읽는다.
   * 서브클래스에서 오버라이드 가능하다.
   */
  protected async findNextTask(): Promise<Task | null> {
    const rows = await this.stateStore.getReadyTasksForAgent(this.id);
    if (rows.length === 0) return null;

    // Pick highest priority (lowest number = highest priority)
    rows.sort((a, b) => (a.priority ?? 3) - (b.priority ?? 3));

    // Try to claim — atomic UPDATE WHERE status='ready' prevents race conditions
    for (const row of rows) {
      const claimed = await this.stateStore.claimTask(row.id);
      if (!claimed) continue; // another agent got it first

      // Sync Board — 실패 시 DB 롤백
      if (row.githubIssueNumber) {
        try {
          await this.gitService.moveIssueToColumn(row.githubIssueNumber, 'In Progress');
        } catch (error) {
          this.log.warn(
            { err: error instanceof Error ? error.message : error, taskId: row.id },
            'Failed to sync Board after claim, rolling back',
          );
          await this.stateStore.updateTask(row.id, {
            status: 'ready',
            boardColumn: 'Ready',
            startedAt: null,
          });
          continue;
        }
      }

      return this.taskRowToTask(row);
    }

    return null; // all candidates were claimed by others
  }

  /**
   * TaskRow (DB) → Task (domain object) 변환.
   */
  protected taskRowToTask(row: TaskRow): Task {
    return taskRowToTask(row);
  }

  /**
   * 태스크를 실행한다. 서브클래스에서 구현한다.
   */
  protected abstract executeTask(task: Task): Promise<TaskResult>;

  /**
   * 태스크 완료 후 처리. 기본 구현은 DB 상태 갱신 + review.request 발행.
   * 서브클래스에서 오버라이드 가능하다 (super.onTaskComplete 호출 권장).
   */
  protected async onTaskComplete(task: Task, result: TaskResult): Promise<void> {
    const newStatus = result.success ? 'review' : 'failed';
    const newColumn = result.success ? 'Review' : 'Failed';

    await this.stateStore.updateTask(task.id, {
      status: newStatus,
      boardColumn: newColumn,
    });

    if (task.githubIssueNumber) {
      try {
        await this.gitService.moveIssueToColumn(task.githubIssueNumber, newColumn);
      } catch (error) {
        this.log.warn(
          { err: error instanceof Error ? error.message : error, taskId: task.id, column: newColumn },
          'Failed to sync Board column after task complete, continuing with review',
        );
      }
    }

    await this.messageBus.publish({
      id: crypto.randomUUID(),
      type: MESSAGE_TYPES.REVIEW_REQUEST,
      from: this.id,
      to: null,
      payload: { taskId: task.id, result },
      traceId: crypto.randomUUID(),
      timestamp: new Date(),
    });
  }
}

/**
 * AbortSignal을 지원하는 sleep. signal이 abort되면 즉시 resolve된다.
 * Graceful shutdown 시 polling sleep을 즉시 깨우는 데 사용.
 */
function abortableSleep(ms: number, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) return Promise.resolve();
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener('abort', () => {
      clearTimeout(timer);
      resolve();
    }, { once: true });
  });
}

/**
 * TaskRow (DB) → Task (domain object) 변환. standalone 함수.
 */
export function taskRowToTask(row: TaskRow): Task {
  return {
    id: row.id,
    epicId: row.epicId,
    title: row.title,
    description: row.description ?? '',
    assignedAgent: row.assignedAgent,
    status: (row.status as Task['status']) ?? 'in-progress',
    githubIssueNumber: row.githubIssueNumber,
    boardColumn: row.boardColumn ?? 'In Progress',
    dependencies: (row.dependencies as string[]) ?? [],
    priority: (row.priority ?? 3) as Task['priority'],
    complexity: (row.complexity ?? 'medium') as Task['complexity'],
    retryCount: row.retryCount ?? 0,
    artifacts: [],
    labels: (row.labels as string[]) ?? [],
    reviewNote: row.reviewNote ?? null,
  };
}
