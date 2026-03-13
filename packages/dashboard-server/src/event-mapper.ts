import type { Message, TaskRow } from '@agent/core';
import { MESSAGE_TYPES } from '@agent/core';
import type { DashboardEvent, DashboardStateStore } from './types.js';

const TASK_CACHE_TTL_MS = 5_000; // 5초 TTL
const SKIP_LOG_EVENTS = new Set(['token.usage', 'agent.status']);

interface CachedTask {
  task: TaskRow;
  cachedAt: number;
}

/**
 * Maps internal MessageBus events to DashboardEvents for the WebSocket clients.
 * Each mapper function returns zero or more DashboardEvents to broadcast.
 * Task 조회에 인메모리 TTL 캐시를 적용하여 N+1 DB 조회를 방지한다.
 */
export class EventMapper {
  private taskCache = new Map<string, CachedTask>();
  private cleanupTimer: ReturnType<typeof setInterval>;

  constructor(private stateStore: DashboardStateStore) {
    // Periodically remove expired cache entries to prevent unbounded growth
    this.cleanupTimer = setInterval(() => {
      const now = Date.now();
      for (const [key, entry] of this.taskCache) {
        if (now - entry.cachedAt >= TASK_CACHE_TTL_MS) {
          this.taskCache.delete(key);
        }
      }
    }, 30_000); // every 30 seconds
    this.cleanupTimer.unref();
  }

  /** Release resources (cleanup timer). Call on server shutdown. */
  dispose(): void {
    clearInterval(this.cleanupTimer);
    this.taskCache.clear();
  }

  /** Number of entries currently in the task cache. */
  get cacheSize(): number {
    return this.taskCache.size;
  }

  /**
   * Pre-load active tasks into cache on server startup.
   * Only caches tasks in active states (backlog, ready, in-progress, review)
   * to avoid wasting memory on completed/failed tasks.
   * Returns the number of tasks cached.
   */
  async warmCache(): Promise<number> {
    const ACTIVE_STATUSES = new Set(['backlog', 'ready', 'in-progress', 'review']);
    const allTasks = await this.stateStore.getAllTasks();
    const now = Date.now();
    let count = 0;

    for (const task of allTasks) {
      if (ACTIVE_STATUSES.has(task.status)) {
        this.taskCache.set(task.id, { task, cachedAt: now });
        count++;
      }
    }

    return count;
  }

  private async getTaskCached(taskId: string): Promise<TaskRow | null> {
    const now = Date.now();
    const cached = this.taskCache.get(taskId);
    if (cached && now - cached.cachedAt < TASK_CACHE_TTL_MS) {
      return cached.task;
    }
    const task = await this.stateStore.getTask(taskId);
    if (task) {
      this.taskCache.set(taskId, { task, cachedAt: now });
    } else {
      this.taskCache.delete(taskId);
    }
    return task;
  }

  /** 캐시에서 특정 task를 무효화한다 (task 상태 변경 시 사용). */
  invalidateTask(taskId: string): void {
    this.taskCache.delete(taskId);
  }

  /**
   * Convert an internal Message into DashboardEvents to broadcast.
   * Always returns the raw message-log event, plus type-specific events.
   */
  async map(message: Message): Promise<DashboardEvent[]> {
    const events: DashboardEvent[] = [];

    // Emit the raw message log, but skip high-frequency events to reduce noise
    if (!SKIP_LOG_EVENTS.has(message.type)) {
      events.push({
        type: 'message',
        payload: {
          id: message.id,
          type: message.type,
          from: message.from,
          content: JSON.stringify(message.payload),
          timestamp: message.timestamp.toISOString(),
        },
      });
    }

    // Type-specific mappings
    switch (message.type) {
      case MESSAGE_TYPES.AGENT_STATUS:
        events.push(...this.mapAgentStatus(message));
        break;

      case MESSAGE_TYPES.BOARD_MOVE:
        events.push(...(await this.mapBoardMove(message)));
        break;

      case MESSAGE_TYPES.REVIEW_REQUEST:
        events.push(...this.mapReviewRequest(message));
        break;

      case MESSAGE_TYPES.EPIC_PROGRESS:
        events.push(...this.mapEpicProgress(message));
        break;

      case MESSAGE_TYPES.BOARD_REMOVE:
        events.push(...this.mapBoardRemove(message));
        break;

      case MESSAGE_TYPES.TOKEN_USAGE:
        events.push(...this.mapTokenUsage(message));
        break;

      case MESSAGE_TYPES.AGENT_CONFIG_UPDATED:
        events.push(...this.mapAgentConfigUpdated(message));
        break;

      case MESSAGE_TYPES.REVIEW_FEEDBACK: {
        const reviewPayload = message.payload as { approved: boolean; taskId: string };
        events.push({
          type: 'toast',
          payload: {
            type: reviewPayload.approved ? 'success' : 'info',
            title: reviewPayload.approved ? 'Review Approved' : 'Revision Requested',
            message: `Task ${reviewPayload.taskId}`,
          },
        });
        break;
      }
    }

    return events;
  }

  private mapAgentStatus(message: Message): DashboardEvent[] {
    const payload = message.payload as { status: string; taskId?: string };
    // 클라이언트 렌더링은 'working'을 기대하므로 'busy' → 'working'으로 정규화
    const normalizedStatus = payload.status === 'busy' ? 'working' : payload.status;
    const events: DashboardEvent[] = [
      {
        type: 'agent.status',
        payload: {
          agentId: message.from,
          status: normalizedStatus,
          task: payload.taskId,
        },
      },
    ];

    // Generate bubble update for agent activity
    if (normalizedStatus === 'working') {
      events.push({
        type: 'agent.bubble',
        payload: {
          agentId: message.from,
          bubble: { content: 'Working...', type: 'task' },
        },
      });
    } else if (payload.status === 'idle') {
      events.push({
        type: 'agent.bubble',
        payload: {
          agentId: message.from,
          bubble: null,
        },
      });
    } else if (payload.status === 'error') {
      events.push({
        type: 'agent.bubble',
        payload: {
          agentId: message.from,
          bubble: { content: 'Error!', type: 'error' },
        },
      });
    }

    return events;
  }

  private async mapBoardMove(message: Message): Promise<DashboardEvent[]> {
    // board.move payload: { issueNumber, title, fromColumn, toColumn, labels }
    const payload = message.payload as {
      issueNumber: number;
      title: string;
      fromColumn: string;
      toColumn: string;
      labels: string[];
    };
    const taskId = `task-gh-${payload.issueNumber}`;
    const events: DashboardEvent[] = [];

    // Force DB fetch by invalidating stale cache entry first (board.move = state changed)
    this.invalidateTask(taskId);
    const task = await this.getTaskCached(taskId);
    if (task) {
      events.push({
        type: 'task.update',
        payload: {
          ...task,
          taskId,
          boardColumn: payload.toColumn,
        },
      });
    }

    // Generate toast for task completion or failure
    if (payload.toColumn === 'Done') {
      events.push({
        type: 'toast',
        payload: {
          type: 'success',
          title: 'Task Completed',
          message: `"${payload.title}" moved to Done`,
        },
      });
    } else if (payload.toColumn === 'Failed') {
      events.push({
        type: 'toast',
        payload: {
          type: 'error',
          title: 'Task Failed',
          message: `"${payload.title}" moved to Failed`,
        },
      });
    }

    // Bubble update for the assigned agent
    if (task?.assignedAgent) {
      if (payload.toColumn === 'In Progress') {
        events.push({
          type: 'agent.bubble',
          payload: {
            agentId: task.assignedAgent,
            bubble: { content: payload.title, type: 'task' },
          },
        });
      } else if (payload.toColumn === 'Done' || payload.toColumn === 'Failed') {
        events.push({
          type: 'agent.bubble',
          payload: {
            agentId: task.assignedAgent,
            bubble: null,
          },
        });
      }
    }

    return events;
  }

  private mapReviewRequest(message: Message): DashboardEvent[] {
    const payload = message.payload as { taskId: string };
    return [
      {
        type: 'agent.status',
        payload: {
          agentId: message.from,
          status: 'reviewing',
          task: payload.taskId,
        },
      },
      {
        type: 'toast',
        payload: {
          type: 'info',
          title: 'Review Requested',
          message: `Agent ${message.from} submitted task ${payload.taskId} for review`,
        },
      },
    ];
  }

  private mapEpicProgress(message: Message): DashboardEvent[] {
    const payload = message.payload as { epicId: string; title: string; progress: number };
    return [
      {
        type: 'epic.progress',
        payload: {
          epicId: payload.epicId,
          title: payload.title,
          progress: payload.progress,
        },
      },
    ];
  }

  private mapTokenUsage(message: Message): DashboardEvent[] {
    const payload = message.payload as { inputTokens: number; outputTokens: number };
    return [
      {
        type: 'token.usage',
        payload: {
          agentId: message.from,
          inputTokens: payload.inputTokens,
          outputTokens: payload.outputTokens,
        },
      },
    ];
  }

  private mapAgentConfigUpdated(message: Message): DashboardEvent[] {
    const payload = message.payload as { agentId: string; config: Record<string, unknown> };
    return [
      {
        type: 'agent.config' as const,
        payload: {
          agentId: payload.agentId,
          // payload.config는 Record<string, unknown>으로 수신되나 DashboardEvent 타입은
          // AgentConfigRow를 요구한다. 런타임 값은 동일하므로 이중 캐스트(as unknown as)로
          // 타입 시스템을 통과시킨다 — 구조적 호환성은 EventMapper 호출부에서 보장됨.
          config: payload.config as unknown as import('@agent/core').AgentConfigRow,
        },
      },
      {
        type: 'toast',
        payload: {
          type: 'info',
          title: 'Config Updated',
          message: `Agent ${payload.agentId} configuration updated`,
        },
      },
    ];
  }

  private mapBoardRemove(message: Message): DashboardEvent[] {
    const payload = message.payload as { issueNumber: number; lastColumn: string };
    return [
      {
        type: 'toast',
        payload: {
          type: 'info',
          title: 'Task Removed',
          message: `Issue #${payload.issueNumber} was removed from the board (was in ${payload.lastColumn})`,
        },
      },
    ];
  }
}
