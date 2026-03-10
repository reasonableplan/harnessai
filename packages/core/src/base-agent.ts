import type { AgentConfig, IMessageBus, MessageHandler, Task, TaskResult } from './types/index.js';
import { MESSAGE_TYPES } from './types/index.js';

export interface AgentDependencies {
  messageBus: IMessageBus;
  // Week 2에서 추가 예정:
  // stateStore: IStateStore;
  // gitService: IGitService;
}

export type AgentStatus = 'idle' | 'busy' | 'paused' | 'error';

export abstract class BaseAgent {
  readonly id: string;
  readonly domain: string;
  readonly config: AgentConfig;

  private polling = false;
  private _status: AgentStatus = 'idle';

  protected messageBus: IMessageBus;

  constructor(config: AgentConfig, deps: AgentDependencies) {
    this.id = config.id;
    this.domain = config.domain;
    this.config = config;
    this.messageBus = deps.messageBus;
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
   * Board Ready 컬럼에서 자신의 도메인 라벨이 있는 가장 높은 우선순위 태스크를 찾는다.
   * 서브클래스에서 구현한다.
   */
  protected abstract findNextTask(): Promise<Task | null>;

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
