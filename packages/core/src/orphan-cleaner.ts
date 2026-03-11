import { eq, notInArray } from 'drizzle-orm';
import type { Database } from './db/index.js';
import { agents, tasks } from './db/schema.js';
import { createLogger } from './logger.js';

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
 */
export class OrphanCleaner {
  private timer: ReturnType<typeof setInterval> | null = null;
  private readonly heartbeatTimeoutMs: number;
  private readonly intervalMs: number;

  constructor(
    private db: Database,
    config: OrphanCleanerConfig = {},
  ) {
    this.heartbeatTimeoutMs = config.heartbeatTimeoutMs ?? 60_000;
    this.intervalMs = config.intervalMs ?? 30_000;
  }

  start(): void {
    if (this.timer) return;
    this.timer = setInterval(() => this.cleanup().catch((e) => log.error({ err: e }, 'Cleanup failed')), this.intervalMs);
    log.info({ intervalMs: this.intervalMs, heartbeatTimeoutMs: this.heartbeatTimeoutMs }, 'OrphanCleaner started');
  }

  stop(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  /**
   * 만료된 에이전트의 In Progress 태스크를 Ready로 복원한다.
   */
  async cleanup(): Promise<number> {
    const now = new Date();
    const cutoff = new Date(now.getTime() - this.heartbeatTimeoutMs);

    // 1. 하트비트가 만료된 에이전트 찾기 — offline/paused를 DB 레벨에서 필터
    const activeAgents = await this.db
      .select()
      .from(agents)
      .where(notInArray(agents.status, ['offline', 'paused']));
    const staleAgentIds = activeAgents
      .filter((a) => {
        if (!a.lastHeartbeat) return true; // 한 번도 하트비트 안 보낸 에이전트
        return a.lastHeartbeat < cutoff;
      })
      .map((a) => a.id);

    if (staleAgentIds.length === 0) return 0;

    // 2. 해당 에이전트의 In Progress 태스크를 Ready로 복원
    const inProgressTasks = await this.db
      .select()
      .from(tasks)
      .where(eq(tasks.boardColumn, 'In Progress'));

    let restored = 0;
    for (const task of inProgressTasks) {
      if (task.assignedAgent && staleAgentIds.includes(task.assignedAgent)) {
        await this.db
          .update(tasks)
          .set({
            status: 'ready',
            boardColumn: 'Ready',
            startedAt: null,
          })
          .where(eq(tasks.id, task.id));

        restored++;
        log.warn(
          { taskId: task.id, taskTitle: task.title, staleAgent: task.assignedAgent },
          'Orphan task restored to Ready',
        );
      }
    }

    // 3. 만료 에이전트 상태를 error로 마킹
    for (const agentId of staleAgentIds) {
      await this.db
        .update(agents)
        .set({ status: 'error' })
        .where(eq(agents.id, agentId));
      log.warn({ agentId }, 'Stale agent marked as error');
    }

    if (restored > 0) {
      log.info({ restored, staleAgents: staleAgentIds.length }, 'Orphan cleanup complete');
    }

    return restored;
  }
}
