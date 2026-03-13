import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { Message, TaskRow } from '@agent/core';
import { MESSAGE_TYPES } from '@agent/core';
import type { DashboardEvent } from './types.js';
import { createMockStateStore, createMockMessage } from '@agent/testing';
import { EventMapper } from './event-mapper.js';
import type { DashboardStateStore } from './types.js';

// ===== Mock Factories =====

function createLocalMockStateStore(): DashboardStateStore {
  return createMockStateStore({
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
  }) as unknown as DashboardStateStore;
}

function createMessage(overrides: Partial<Message> = {}): Message {
  return createMockMessage({
    type: MESSAGE_TYPES.AGENT_STATUS,
    from: 'backend',
    payload: { status: 'busy' },
    timestamp: new Date('2026-01-01T00:00:00Z'),
    ...overrides,
  });
}

// ===== EventMapper Tests =====

describe('EventMapper', () => {
  let mapper: EventMapper;
  let stateStore: DashboardStateStore;

  beforeEach(() => {
    stateStore = createLocalMockStateStore();
    mapper = new EventMapper(stateStore);
  });

  it('emits a raw message log event for non-high-frequency events', async () => {
    // agent.status is a high-frequency event and should NOT emit a message log
    const msg = createMessage();
    const events = await mapper.map(msg);

    const messageEvent = events.find((e) => e.type === 'message');
    expect(messageEvent).toBeUndefined();

    // agent.status still emits agent.status event
    const statusEvent = events.find((e) => e.type === 'agent.status');
    expect(statusEvent).toBeDefined();
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
      vi.mocked(stateStore.getTask).mockResolvedValue(taskRow as unknown as TaskRow);

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
      } as unknown as TaskRow);

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
      } as unknown as TaskRow);

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
      expect((toast!.payload as Extract<DashboardEvent, { type: 'toast' }>['payload']).message).toContain('#42');
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

  describe('warmCache', () => {
    it('pre-loads active tasks into cache', async () => {
      const activeTasks = [
        { id: 'task-1', status: 'in-progress', boardColumn: 'In Progress', title: 'Active 1' },
        { id: 'task-2', status: 'ready', boardColumn: 'Ready', title: 'Active 2' },
        { id: 'task-3', status: 'review', boardColumn: 'Review', title: 'Review 1' },
        { id: 'task-done', status: 'done', boardColumn: 'Done', title: 'Done 1' },
      ] as unknown as TaskRow[];
      vi.mocked(stateStore.getAllTasks).mockResolvedValue(activeTasks);

      const count = await mapper.warmCache();

      // Only active tasks (not done/failed) should be cached
      expect(count).toBe(3);

      // Verify cache is populated
      expect(mapper.cacheSize).toBe(3);
    });

    it('returns 0 when no active tasks exist', async () => {
      vi.mocked(stateStore.getAllTasks).mockResolvedValue([]);

      const count = await mapper.warmCache();
      expect(count).toBe(0);
      expect(mapper.cacheSize).toBe(0);
    });

    it('skips failed and done tasks', async () => {
      const tasks = [
        { id: 'task-a', status: 'failed', boardColumn: 'Failed', title: 'F' },
        { id: 'task-b', status: 'done', boardColumn: 'Done', title: 'D' },
      ] as unknown as TaskRow[];
      vi.mocked(stateStore.getAllTasks).mockResolvedValue(tasks);

      const count = await mapper.warmCache();
      expect(count).toBe(0);
    });
  });
});
