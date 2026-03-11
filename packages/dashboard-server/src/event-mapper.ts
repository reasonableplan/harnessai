import type { Message, TaskRow } from '@agent/core';
import { MESSAGE_TYPES } from '@agent/core';
import type { DashboardEvent, DashboardStateStore } from './types.js';

/**
 * Maps internal MessageBus events to DashboardEvents for the WebSocket clients.
 * Each mapper function returns zero or more DashboardEvents to broadcast.
 */
export class EventMapper {
  constructor(private stateStore: DashboardStateStore) {}

  /**
   * Convert an internal Message into DashboardEvents to broadcast.
   * Always returns the raw message-log event, plus type-specific events.
   */
  async map(message: Message): Promise<DashboardEvent[]> {
    const events: DashboardEvent[] = [];

    // Always emit the raw message log
    events.push({ type: 'message-log', payload: { message } });

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
    }

    return events;
  }

  private mapAgentStatus(message: Message): DashboardEvent[] {
    const payload = message.payload as { status: string; taskId?: string };
    const events: DashboardEvent[] = [
      {
        type: 'agent-state',
        payload: {
          agentId: message.from,
          status: payload.status,
          task: payload.taskId,
        },
      },
    ];

    // Generate bubble update for agent activity
    if (payload.status === 'busy') {
      events.push({
        type: 'bubble-update',
        payload: {
          agentId: message.from,
          content: 'Working...',
          type: 'working',
        },
      });
    } else if (payload.status === 'idle') {
      events.push({
        type: 'bubble-update',
        payload: {
          agentId: message.from,
          content: null,
        },
      });
    } else if (payload.status === 'error') {
      events.push({
        type: 'bubble-update',
        payload: {
          agentId: message.from,
          content: 'Error!',
          type: 'error',
        },
      });
    }

    return events;
  }

  private async mapBoardMove(message: Message): Promise<DashboardEvent[]> {
    const payload = message.payload as { taskId: string; from: string; to: string };
    const events: DashboardEvent[] = [];

    // Try to get the full task row for the board update
    const task = await this.stateStore.getTask(payload.taskId);
    if (task) {
      events.push({
        type: 'board-update',
        payload: {
          taskId: payload.taskId,
          column: payload.to,
          task,
        },
      });
    }

    // Generate toast for task completion or failure
    if (payload.to === 'Done') {
      events.push({
        type: 'toast',
        payload: {
          type: 'success',
          title: 'Task Completed',
          message: task ? `"${task.title}" moved to Done` : `Task ${payload.taskId} completed`,
        },
      });
    } else if (payload.to === 'Failed') {
      events.push({
        type: 'toast',
        payload: {
          type: 'error',
          title: 'Task Failed',
          message: task ? `"${task.title}" moved to Failed` : `Task ${payload.taskId} failed`,
        },
      });
    }

    // Bubble update for the assigned agent
    if (task?.assignedAgent) {
      if (payload.to === 'In Progress') {
        events.push({
          type: 'bubble-update',
          payload: {
            agentId: task.assignedAgent,
            content: task.title,
            type: 'working',
          },
        });
      } else if (payload.to === 'Done' || payload.to === 'Failed') {
        events.push({
          type: 'bubble-update',
          payload: {
            agentId: task.assignedAgent,
            content: null,
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
        type: 'agent-state',
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
        type: 'epic-update',
        payload: {
          epicId: payload.epicId,
          title: payload.title,
          progress: payload.progress,
        },
      },
    ];
  }

  private mapBoardRemove(message: Message): DashboardEvent[] {
    const payload = message.payload as { taskId: string };
    return [
      {
        type: 'toast',
        payload: {
          type: 'info',
          title: 'Task Removed',
          message: `Task ${payload.taskId} was removed from the board`,
        },
      },
    ];
  }
}
