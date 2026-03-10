import type {
  AgentConfig,
  IMessageBus,
  IStateStore,
  IGitService,
  MessageHandler,
  Task,
  TaskResult,
  TaskRow,
} from './types/index.js';
import { MESSAGE_TYPES } from './types/index.js';

export interface AgentDependencies {
  messageBus: IMessageBus;
  stateStore: IStateStore;
  gitService: IGitService;
}

export type AgentStatus = 'idle' | 'busy' | 'paused' | 'error';

export abstract class BaseAgent {
  readonly id: string;
  readonly domain: string;
  readonly config: AgentConfig;

  private polling = false;
  private _status: AgentStatus = 'idle';

  protected messageBus: IMessageBus;
  protected stateStore: IStateStore;
  protected gitService: IGitService;

  constructor(config: AgentConfig, deps: AgentDependencies) {
    this.id = config.id;
    this.domain = config.domain;
    this.config = config;
    this.messageBus = deps.messageBus;
    this.stateStore = deps.stateStore;
    this.gitService = deps.gitService;
  }

  get status(): AgentStatus {
    return this._status;
  }

  protected setStatus(status: AgentStatus) {
    this._status = status;
    this.messageBus.publish({
      id: crypto.randomUUID(),
      type: MESSAGE_TYPES.AGENT_STATUS,
      from: this.id,
      to: null,
      payload: { status },
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
    this.pollLoop(intervalMs);
  }

  stopPolling() {
    this.polling = false;
  }

  private async pollLoop(intervalMs: number) {
    while (this.polling) {
      if (this._status === 'idle') {
        try {
          const task = await this.findNextTask();
          if (task) {
            this.setStatus('busy');
            const result = await this.executeTask(task);
            await this.onTaskComplete(task, result);
            this.setStatus('idle');
          }
        } catch (error) {
          this.setStatus('error');
          console.error(`[${this.id}] Polling error:`, error);
        }
      }
      await new Promise((r) => setTimeout(r, intervalMs));
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

      // Sync Board
      if (row.githubIssueNumber) {
        await this.gitService.moveIssueToColumn(row.githubIssueNumber, 'In Progress');
      }

      return this.taskRowToTask(row);
    }

    return null; // all candidates were claimed by others
  }

  /**
   * TaskRow (DB) → Task (domain object) 변환.
   */
  protected taskRowToTask(row: TaskRow): Task {
    return {
      id: row.id,
      epicId: row.epicId,
      title: row.title,
      description: row.description ?? '',
      assignedAgent: row.assignedAgent,
      status: 'in-progress',
      githubIssueNumber: row.githubIssueNumber,
      boardColumn: 'In Progress',
      dependencies: (row.dependencies as string[]) ?? [],
      priority: (row.priority ?? 3) as Task['priority'],
      complexity: (row.complexity ?? 'medium') as Task['complexity'],
      retryCount: row.retryCount ?? 0,
      artifacts: [],
    };
  }

  /**
   * 태스크를 실행한다. 서브클래스에서 구현한다.
   */
  protected abstract executeTask(task: Task): Promise<TaskResult>;

  /**
   * 태스크 완료 후 처리. 기본 구현은 review.request를 발행한다.
   * 서브클래스에서 오버라이드 가능하다.
   */
  protected async onTaskComplete(task: Task, result: TaskResult): Promise<void> {
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
