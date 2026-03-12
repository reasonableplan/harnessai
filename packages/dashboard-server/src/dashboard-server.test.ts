import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { Message } from '@agent/core';
import { MESSAGE_TYPES } from '@agent/core';
import { EventMapper } from './event-mapper.js';
import type { DashboardStateStore, DashboardMessageBus } from './types.js';

// ===== Mock Factories =====

function createMockStateStore(): DashboardStateStore {
  return {
    getAgent: vi.fn().mockResolvedValue(null),
    getTask: vi.fn().mockResolvedValue(null),
    updateTask: vi.fn(),
    getTasksByColumn: vi.fn().mockResolvedValue([]),
    getAllAgents: vi.fn().mockResolvedValue([
      { id: 'director', domain: 'orchestration', level: 0, status: 'idle', parentId: null, createdAt: new Date(), lastHeartbeat: new Date() },
      { id: 'backend', domain: 'backend', level: 2, status: 'idle', parentId: 'director', createdAt: new Date(), lastHeartbeat: new Date() },
    ]),
    getAllTasks: vi.fn().mockResolvedValue([
      { id: 'task-1', epicId: 'epic-1', title: 'Test task', boardColumn: 'Ready', status: 'ready', assignedAgent: 'backend', priority: 3, complexity: 'medium', dependencies: [], labels: [], retryCount: 0, createdAt: new Date(), startedAt: null, completedAt: null, githubIssueNumber: 10, reviewNote: null },
    ]),
    getAllEpics: vi.fn().mockResolvedValue([
      { id: 'epic-1', title: 'Test Epic', description: 'Test', status: 'active', progress: 0.5, createdAt: new Date(), completedAt: null, githubMilestoneNumber: null },
    ]),
    getRecentMessages: vi.fn().mockResolvedValue([]),
  };
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars -- kept for future test expansion
function createMockMessageBus(): DashboardMessageBus {
  return {
    publish: vi.fn(),
    subscribeAll: vi.fn(),
  };
}

function createMessage(overrides: Partial<Message> = {}): Message {
  return {
    id: 'msg-1',
    type: MESSAGE_TYPES.AGENT_STATUS,
    from: 'backend',
    to: null,
    payload: { status: 'busy' },
    traceId: 'trace-1',
    timestamp: new Date('2026-01-01T00:00:00Z'),
    ...overrides,
  };
}

// ===== EventMapper Tests =====

describe('EventMapper', () => {
  let mapper: EventMapper;
  let stateStore: DashboardStateStore;

  beforeEach(() => {
    stateStore = createMockStateStore();
    mapper = new EventMapper(stateStore);
  });

  it('always emits a raw message log event', async () => {
    const msg = createMessage();
    const events = await mapper.map(msg);

    const messageEvent = events.find((e) => e.type === 'message');
    expect(messageEvent).toBeDefined();
    expect(messageEvent!.payload).toMatchObject({
      id: 'msg-1',
      type: MESSAGE_TYPES.AGENT_STATUS,
      from: 'backend',
    });
  });

  describe('agent.status mapping', () => {
    it('maps busy status to agent.status + agent.bubble', async () => {
      const msg = createMessage({
        type: MESSAGE_TYPES.AGENT_STATUS,
        payload: { status: 'busy' },
      });
      const events = await mapper.map(msg);

      const statusEvent = events.find((e) => e.type === 'agent.status');
      expect(statusEvent).toBeDefined();
      expect(statusEvent!.payload).toMatchObject({
        agentId: 'backend',
        status: 'working',
      });

      const bubbleEvent = events.find((e) => e.type === 'agent.bubble');
      expect(bubbleEvent).toBeDefined();
      expect(bubbleEvent!.payload).toMatchObject({
        agentId: 'backend',
        bubble: { content: 'Working...', type: 'task' },
      });
    });

    it('maps idle status to null bubble', async () => {
      const msg = createMessage({
        type: MESSAGE_TYPES.AGENT_STATUS,
        payload: { status: 'idle' },
      });
      const events = await mapper.map(msg);

      const bubbleEvent = events.find((e) => e.type === 'agent.bubble');
      expect(bubbleEvent).toBeDefined();
      expect(bubbleEvent!.payload).toMatchObject({
        agentId: 'backend',
        bubble: null,
      });
    });

    it('maps error status to error bubble', async () => {
      const msg = createMessage({
        type: MESSAGE_TYPES.AGENT_STATUS,
        payload: { status: 'error' },
      });
      const events = await mapper.map(msg);

      const bubbleEvent = events.find((e) => e.type === 'agent.bubble');
      expect(bubbleEvent!.payload).toMatchObject({
        bubble: { content: 'Error!', type: 'error' },
      });
    });
  });

  describe('board.move mapping', () => {
    it('emits task.update when task found in DB', async () => {
      const taskRow = {
        id: 'task-gh-10',
        title: 'Test task',
        boardColumn: 'In Progress',
        assignedAgent: 'backend',
        status: 'in-progress',
      };
      vi.mocked(stateStore.getTask).mockResolvedValue(taskRow as any);

      const msg = createMessage({
        type: MESSAGE_TYPES.BOARD_MOVE,
        payload: {
          issueNumber: 10,
          title: 'Test task',
          fromColumn: 'Ready',
          toColumn: 'In Progress',
          labels: ['agent:backend'],
        },
      });
      const events = await mapper.map(msg);

      const taskEvent = events.find((e) => e.type === 'task.update');
      expect(taskEvent).toBeDefined();
      expect(taskEvent!.payload).toMatchObject({ taskId: 'task-gh-10', boardColumn: 'In Progress' });
    });

    it('emits success toast for Done column', async () => {
      const msg = createMessage({
        type: MESSAGE_TYPES.BOARD_MOVE,
        payload: {
          issueNumber: 10,
          title: 'Completed task',
          fromColumn: 'Review',
          toColumn: 'Done',
          labels: [],
        },
      });
      const events = await mapper.map(msg);

      const toast = events.find((e) => e.type === 'toast');
      expect(toast).toBeDefined();
      expect(toast!.payload).toMatchObject({ type: 'success', title: 'Task Completed' });
    });

    it('emits error toast for Failed column', async () => {
      const msg = createMessage({
        type: MESSAGE_TYPES.BOARD_MOVE,
        payload: {
          issueNumber: 10,
          title: 'Failed task',
          fromColumn: 'In Progress',
          toColumn: 'Failed',
          labels: [],
        },
      });
      const events = await mapper.map(msg);

      const toast = events.find((e) => e.type === 'toast');
      expect(toast!.payload).toMatchObject({ type: 'error', title: 'Task Failed' });
    });

    it('emits agent bubble for In Progress with assigned agent', async () => {
      vi.mocked(stateStore.getTask).mockResolvedValue({
        id: 'task-gh-10',
        assignedAgent: 'frontend',
        boardColumn: 'In Progress',
      } as any);

      const msg = createMessage({
        type: MESSAGE_TYPES.BOARD_MOVE,
        payload: {
          issueNumber: 10,
          title: 'UI task',
          fromColumn: 'Ready',
          toColumn: 'In Progress',
          labels: [],
        },
      });
      const events = await mapper.map(msg);

      const bubble = events.find((e) => e.type === 'agent.bubble');
      expect(bubble).toBeDefined();
      expect(bubble!.payload).toMatchObject({
        agentId: 'frontend',
        bubble: { content: 'UI task', type: 'task' },
      });
    });

    it('clears agent bubble on Done/Failed', async () => {
      vi.mocked(stateStore.getTask).mockResolvedValue({
        id: 'task-gh-10',
        assignedAgent: 'backend',
        boardColumn: 'Done',
      } as any);

      const msg = createMessage({
        type: MESSAGE_TYPES.BOARD_MOVE,
        payload: {
          issueNumber: 10,
          title: 'Done task',
          fromColumn: 'Review',
          toColumn: 'Done',
          labels: [],
        },
      });
      const events = await mapper.map(msg);

      const bubble = events.find((e) => e.type === 'agent.bubble');
      expect(bubble!.payload).toMatchObject({ agentId: 'backend', bubble: null });
    });
  });

  describe('review.request mapping', () => {
    it('emits agent status + toast', async () => {
      const msg = createMessage({
        type: MESSAGE_TYPES.REVIEW_REQUEST,
        from: 'frontend',
        payload: { taskId: 'task-gh-11' },
      });
      const events = await mapper.map(msg);

      const statusEvent = events.find((e) => e.type === 'agent.status');
      expect(statusEvent!.payload).toMatchObject({
        agentId: 'frontend',
        status: 'reviewing',
        task: 'task-gh-11',
      });

      const toast = events.find((e) => e.type === 'toast');
      expect(toast!.payload).toMatchObject({ type: 'info', title: 'Review Requested' });
    });
  });

  describe('epic.progress mapping', () => {
    it('emits epic.progress event', async () => {
      const msg = createMessage({
        type: MESSAGE_TYPES.EPIC_PROGRESS,
        payload: { epicId: 'epic-1', title: 'MVP', progress: 0.75 },
      });
      const events = await mapper.map(msg);

      const epicEvent = events.find((e) => e.type === 'epic.progress');
      expect(epicEvent!.payload).toMatchObject({
        epicId: 'epic-1',
        title: 'MVP',
        progress: 0.75,
      });
    });
  });

  describe('board.remove mapping', () => {
    it('emits toast for removed issue', async () => {
      const msg = createMessage({
        type: MESSAGE_TYPES.BOARD_REMOVE,
        payload: { issueNumber: 42, lastColumn: 'Ready' },
      });
      const events = await mapper.map(msg);

      const toast = events.find((e) => e.type === 'toast');
      expect(toast!.payload).toMatchObject({
        type: 'info',
        title: 'Task Removed',
      });
      expect((toast!.payload as any).message).toContain('#42');
    });
  });

  describe('unknown message type', () => {
    it('emits only the raw message log event', async () => {
      const msg = createMessage({ type: 'custom.event', payload: { foo: 'bar' } });
      const events = await mapper.map(msg);

      expect(events).toHaveLength(1);
      expect(events[0].type).toBe('message');
    });
  });
});
