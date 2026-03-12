import type { IStateStore } from '../types/index.js';
import { createLogger } from '../logging/logger.js';

const log = createLogger('OrphanCleaner');

export interface OrphanCleanerConfig {
  /** 하트비트 만료 시간 ms (기본 60초) */
  heartbeatTimeoutMs?: number;
  /** 정리 주기 ms (기본 30초) */
  intervalMs?: number;
}

/**
 * 고아 태스크 정리 — 죽은 에이전트의 In Progress 태스크를 Ready로 복원.
 * 에이전트가 크래시되면 하트비트가 중단되므로, 일정 시간 초과 시 클레임을 해제한다.
 *
 * setTimeout 재귀 방식으로 이전 cleanup 완료 후에만 다음 주기가 시작된다 (동시 실행 방지).
 */
export class OrphanCleaner {
  private timer: ReturnType<typeof setTimeout> | null = null;
  private running = false;
  private readonly heartbeatTimeoutMs: number;
  private readonly intervalMs: number;

  constructor(
    private stateStore: IStateStore,
    config: OrphanCleanerConfig = {},
  ) {
    this.heartbeatTimeoutMs = config.heartbeatTimeoutMs ?? 60_000;
    this.intervalMs = config.intervalMs ?? 30_000;
  }

  start(): void {
    if (this.running) return;
    this.running = true;
    this.scheduleNext();
    log.info(
      { intervalMs: this.intervalMs, heartbeatTimeoutMs: this.heartbeatTimeoutMs },
      'OrphanCleaner started',
    );
  }

  stop(): void {
    this.running = false;
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }

  private scheduleNext(): void {
    if (!this.running) return;
    this.timer = setTimeout(async () => {
      try {
        await this.cleanup();
      } catch (e) {
        log.error({ err: e }, 'Cleanup failed');
      }
      this.scheduleNext();
    }, this.intervalMs);
  }

  /**
   * 만료된 에이전트의 In Progress 태스크를 Ready로 복원한다.
   * IStateStore를 경유하여 상태 전환 검증을 유지한다.
   */
  async cleanup(): Promise<number> {
    const cutoff = new Date(Date.now() - this.heartbeatTimeoutMs);

    // 1. 모든 에이전트를 조회하여 stale 에이전트 찾기
    const allAgents = await this.stateStore.getAllAgents();
    const staleAgentIds = allAgents
      .filter((a) => {
        if (a.status === 'offline' || a.status === 'paused') return false;
        if (!a.lastHeartbeat) return true;
        return a.lastHeartbeat < cutoff;
      })
      .map((a) => a.id);

    if (staleAgentIds.length === 0) return 0;

    const staleSet = new Set(staleAgentIds);

    // 2. In Progress 태스크 중 stale 에이전트에 할당된 것을 Ready로 복원
    const inProgressTasks = await this.stateStore.getTasksByColumn('In Progress');
    let restored = 0;

    for (const task of inProgressTasks) {
      if (task.assignedAgent && staleSet.has(task.assignedAgent)) {
        await this.stateStore.updateTask(task.id, {
          status: 'ready',
          boardColumn: 'Ready',
          startedAt: null,
        });
        restored++;
        log.warn(
          { taskId: task.id, taskTitle: task.title, staleAgent: task.assignedAgent },
          'Orphan task restored to Ready',
        );
      }
    }

    // 3. 만료 에이전트 상태를 error로 마킹
    for (const agentId of staleAgentIds) {
      await this.stateStore.updateAgentStatus(agentId, 'error');
      log.warn({ agentId }, 'Stale agent marked as error');
    }

    if (restored > 0) {
      log.info({ restored, staleAgents: staleAgentIds.length }, 'Orphan cleanup complete');
    }

    return restored;
  }
}
