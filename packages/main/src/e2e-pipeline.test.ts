import { describe, it, expect, vi, beforeEach } from 'vitest';
import type {
  AgentDependencies,
  IMessageBus,
  IStateStore,
  IGitService,
  Message,
  TaskRow,
} from '@agent/core';
import { MESSAGE_TYPES } from '@agent/core';
import { EventMapper } from '@agent/dashboard-server';
import { createAgentFactories } from './agent-factories.js';
import {
  createDashboardDeps,
  createDashboardStateStore,
  createDashboardMessageBus,
  createAgentRegistry,
} from './dashboard-adapter.js';

// ===== Helpers =====

function createMockConfig() {
  return {
    database: { url: 'postgres://localhost/test' },
    github: { token: 'ghp_test', owner: 'test-owner', repo: 'test-repo' },
    claude: { apiKey: 'sk-ant-test' },
    workspace: { workDir: '/tmp/test-workspace' },
    dashboard: { port: 3001, corsOrigins: ['http://localhost:3000'] },
    logging: { level: 'info', isProduction: false },
  };
}

function createMockMessageBus(): IMessageBus & { _allHandlers: Array<(msg: Message) => void | Promise<void>> } {
  const allHandlers: Array<(msg: Message) => void | Promise<void>> = [];
  const typeHandlers = new Map<string, Array<(msg: Message) => void | Promise<void>>>();

  return {
    _allHandlers: allHandlers,
    async publish(message: Message) {
      const handlers = typeHandlers.get(message.type) ?? [];
      for (const h of handlers) await h(message);
      for (const h of allHandlers) await h(message);
    },
    subscribe(type: string, handler: (msg: Message) => void | Promise<void>) {
      const existing = typeHandlers.get(type) ?? [];
      existing.push(handler);
      typeHandlers.set(type, existing);
    },
    subscribeAll(handler: (msg: Message) => void | Promise<void>) {
      allHandlers.push(handler);
    },
    unsubscribe: vi.fn(),
  };
}

function createMockStateStore(): IStateStore {
  const tasks = new Map<string, TaskRow>();

  return {
    registerAgent: vi.fn(),
    getAgent: vi.fn(),
    updateAgentStatus: vi.fn(),
    updateHeartbeat: vi.fn(),
    createTask: vi.fn().mockImplementation(async (task: TaskRow) => {
      tasks.set(task.id, task);
    }),
    getTask: vi.fn().mockImplementation(async (id: string) => tasks.get(id) ?? null),
    updateTask: vi.fn().mockImplementation(async (id: string, updates: Partial<TaskRow>) => {
      const existing = tasks.get(id);
      if (existing) tasks.set(id, { ...existing, ...updates });
    }),
    getTasksByColumn: vi.fn().mockImplementation(async (col: string) =>
      Array.from(tasks.values()).filter((t) => t.boardColumn === col),
    ),
    getTasksByAgent: vi.fn().mockResolvedValue([]),
    getReadyTasksForAgent: vi.fn().mockImplementation(async (agentId: string) =>
      Array.from(tasks.values()).filter(
        (t) => t.boardColumn === 'Ready' && t.assignedAgent === agentId,
      ),
    ),
    claimTask: vi.fn().mockImplementation(async (id: string) => {
      const task = tasks.get(id);
      if (task && task.boardColumn === 'Ready') {
        tasks.set(id, { ...task, boardColumn: 'In Progress', status: 'in-progress' });
        return true;
      }
      return false;
    }),
    createEpic: vi.fn(),
    getEpic: vi.fn(),
    updateEpic: vi.fn(),
    saveMessage: vi.fn(),
    saveArtifact: vi.fn(),
    getAllAgents: vi.fn().mockResolvedValue([
      { id: 'director', domain: 'orchestration', level: 0, status: 'idle', parentId: null, createdAt: new Date(), lastHeartbeat: new Date() },
      { id: 'backend', domain: 'backend', level: 2, status: 'idle', parentId: 'director', createdAt: new Date(), lastHeartbeat: new Date() },
    ]),
    getAllTasks: vi.fn().mockImplementation(async () => Array.from(tasks.values())),
    getAllEpics: vi.fn().mockResolvedValue([]),
    getRecentMessages: vi.fn().mockResolvedValue([]),
    transaction: vi.fn().mockImplementation((fn) => fn({})),
  };
}

function createMockGitService(): IGitService {
  let issueCounter = 100;
  return {
    validateConnection: vi.fn(),
    createIssue: vi.fn().mockImplementation(() => Promise.resolve(++issueCounter)),
    updateIssue: vi.fn(),
    closeIssue: vi.fn(),
    getIssue: vi.fn().mockImplementation((n: number) =>
      Promise.resolve({
        issueNumber: n,
        title: `Issue #${n}`,
        body: 'test body',
        labels: [],
        column: 'Backlog',
        dependencies: [],
        assignee: null,
        generatedBy: 'test',
        epicId: null,
      }),
    ),
    getIssuesByLabel: vi.fn().mockResolvedValue([]),
    getEpicIssues: vi.fn().mockResolvedValue([]),
    getAllProjectItems: vi.fn().mockResolvedValue([]),
    moveIssueToColumn: vi.fn(),
    addComment: vi.fn(),
    createBranch: vi.fn(),
    createPR: vi.fn(),
  };
}

// ===== Tests =====

describe('E2E Pipeline — Dashboard Adapter Integration', () => {
  let bus: ReturnType<typeof createMockMessageBus>;
  let store: IStateStore;
  let git: IGitService;
  let deps: AgentDependencies;

  beforeEach(() => {
    bus = createMockMessageBus();
    store = createMockStateStore();
    git = createMockGitService();
    deps = { messageBus: bus, stateStore: store, gitService: git };
  });

  it('createDashboardStateStore delegates all methods to real store', async () => {
    const dashStore = createDashboardStateStore(store);

    await dashStore.getAllAgents();
    expect(store.getAllAgents).toHaveBeenCalled();

    await dashStore.getAllTasks();
    expect(store.getAllTasks).toHaveBeenCalled();

    await dashStore.getTask('task-1');
    expect(store.getTask).toHaveBeenCalledWith('task-1');
  });

  it('createDashboardMessageBus delegates publish and subscribeAll', async () => {
    const dashBus = createDashboardMessageBus(bus);
    const handler = vi.fn();

    dashBus.subscribeAll(handler);
    expect(bus._allHandlers).toContain(handler);

    const msg: Message = {
      id: 'test-1',
      type: 'agent.status',
      from: 'backend',
      to: null,
      payload: { status: 'busy' },
      traceId: 'trace-1',
      timestamp: new Date(),
    };
    await dashBus.publish(msg);
    expect(handler).toHaveBeenCalledWith(msg);
  });

  it('createAgentRegistry pause/resume calls agent methods', async () => {
    const config = createMockConfig();
    const factories = createAgentFactories(config);
    const agents = Object.values(factories).map((f) => f(deps));

    // Start polling so pause/resume have effect
    for (const a of agents) a.startPolling(600_000);

    const registry = createAgentRegistry(agents as any[]);

    await registry.pause('backend');
    const backendAgent = agents.find((a) => a.id === 'backend')!;
    expect(backendAgent.status).toBe('paused');

    await registry.resume('backend');
    expect(backendAgent.status).toBe('idle');

    // Cleanup
    for (const a of agents) a.stopPolling();
  });

  it('createAgentRegistry pauseAll/resumeAll affects all agents', async () => {
    const config = createMockConfig();
    const factories = createAgentFactories(config);
    const agents = Object.values(factories).map((f) => f(deps));
    for (const a of agents) a.startPolling(600_000);

    const registry = createAgentRegistry(agents as any[]);

    await registry.pauseAll();
    for (const a of agents) {
      expect(a.status).toBe('paused');
    }

    await registry.resumeAll();
    for (const a of agents) {
      expect(a.status).toBe('idle');
    }

    for (const a of agents) a.stopPolling();
  });

  it('createDashboardDeps returns complete DashboardDependencies', () => {
    const config = createMockConfig();
    const factories = createAgentFactories(config);
    const agents = Object.values(factories).map((f) => f(deps));

    const dashDeps = createDashboardDeps(store, bus, agents as any[]);

    expect(dashDeps.stateStore).toBeDefined();
    expect(dashDeps.messageBus).toBeDefined();
    expect(dashDeps.agentRegistry).toBeDefined();
    expect(dashDeps.agentRegistry!.pause).toBeTypeOf('function');
    expect(dashDeps.agentRegistry!.resume).toBeTypeOf('function');
    expect(dashDeps.agentRegistry!.pauseAll).toBeTypeOf('function');
    expect(dashDeps.agentRegistry!.resumeAll).toBeTypeOf('function');
  });
});

describe('E2E Pipeline — Message Flow', () => {
  let bus: ReturnType<typeof createMockMessageBus>;

  beforeEach(() => {
    bus = createMockMessageBus();
  });

  it('board.move event flows from BoardWatcher through MessageBus to subscribers', async () => {
    const received: Message[] = [];
    bus.subscribe('board.move', (msg) => { received.push(msg); });

    const boardMoveMsg: Message = {
      id: 'bm-1',
      type: 'board.move',
      from: 'board-watcher',
      to: null,
      payload: {
        issueNumber: 42,
        title: 'Test task',
        fromColumn: 'Ready',
        toColumn: 'In Progress',
        labels: ['agent:backend'],
      },
      traceId: 'trace-1',
      timestamp: new Date(),
    };

    await bus.publish(boardMoveMsg);

    expect(received).toHaveLength(1);
    expect(received[0].type).toBe('board.move');
    expect((received[0].payload as any).issueNumber).toBe(42);
  });

  it('review.request triggers Director review flow', async () => {
    const reviewRequests: Message[] = [];
    bus.subscribe('review.request', (msg) => { reviewRequests.push(msg); });

    // Simulate worker completing a task
    const reviewMsg: Message = {
      id: 'rr-1',
      type: 'review.request',
      from: 'backend',
      to: null,
      payload: {
        taskId: 'task-gh-42',
        result: { success: true, artifacts: ['src/routes/users.ts'] },
      },
      traceId: 'trace-2',
      timestamp: new Date(),
    };

    await bus.publish(reviewMsg);

    expect(reviewRequests).toHaveLength(1);
    expect((reviewRequests[0].payload as any).taskId).toBe('task-gh-42');
  });

  it('subscribeAll receives all message types for dashboard broadcast', async () => {
    const allMessages: Message[] = [];
    bus.subscribeAll((msg) => { allMessages.push(msg); });

    await bus.publish({
      id: 'a', type: 'agent.status', from: 'backend', to: null,
      payload: { status: 'busy' }, traceId: 't1', timestamp: new Date(),
    });
    await bus.publish({
      id: 'b', type: 'board.move', from: 'board-watcher', to: null,
      payload: { issueNumber: 1 }, traceId: 't2', timestamp: new Date(),
    });
    await bus.publish({
      id: 'c', type: 'epic.progress', from: 'director', to: null,
      payload: { epicId: 'e1' }, traceId: 't3', timestamp: new Date(),
    });

    expect(allMessages).toHaveLength(3);
    expect(allMessages.map((m) => m.type)).toEqual(['agent.status', 'board.move', 'epic.progress']);
  });
});

describe('E2E Pipeline — Task Lifecycle', () => {
  let store: IStateStore;

  beforeEach(() => {
    store = createMockStateStore();
  });

  it('task goes through full lifecycle: create → claim → complete', async () => {
    // 1. Director creates task in Backlog
    const taskRow: TaskRow = {
      id: 'task-gh-101',
      epicId: 'epic-1',
      title: 'Create user API',
      description: 'Build user CRUD endpoints',
      assignedAgent: 'backend',
      status: 'backlog',
      githubIssueNumber: 101,
      boardColumn: 'Backlog',
      priority: 2,
      complexity: 'medium',
      dependencies: [],
      labels: ['agent:backend'],
      retryCount: 0,
      createdAt: new Date(),
      startedAt: null,
      completedAt: null,
      reviewNote: null,
    };
    await store.createTask(taskRow);

    // 2. Dispatcher promotes to Ready
    await store.updateTask('task-gh-101', { status: 'ready', boardColumn: 'Ready' });

    // 3. Worker claims the task
    const claimed = await store.claimTask('task-gh-101');
    expect(claimed).toBe(true);

    // 4. Verify task is now In Progress
    const inProgress = await store.getTask('task-gh-101');
    expect(inProgress?.boardColumn).toBe('In Progress');
    expect(inProgress?.status).toBe('in-progress');

    // 5. Worker completes → moves to Review
    await store.updateTask('task-gh-101', { status: 'review', boardColumn: 'Review' });

    // 6. Director approves → Done
    await store.updateTask('task-gh-101', {
      status: 'done',
      boardColumn: 'Done',
      completedAt: new Date(),
    });

    const done = await store.getTask('task-gh-101');
    expect(done?.status).toBe('done');
    expect(done?.boardColumn).toBe('Done');
    expect(done?.completedAt).toBeInstanceOf(Date);
  });

  it('task retry: review rejection → back to Ready with feedback', async () => {
    await store.createTask({
      id: 'task-gh-201',
      epicId: null,
      title: 'Fix bug',
      description: 'Fix null pointer',
      assignedAgent: 'backend',
      status: 'review',
      githubIssueNumber: 201,
      boardColumn: 'Review',
      priority: 3,
      complexity: 'low',
      dependencies: [],
      labels: [],
      retryCount: 0,
      createdAt: new Date(),
      startedAt: new Date(),
      completedAt: null,
      reviewNote: null,
    });

    // Director rejects with feedback
    await store.updateTask('task-gh-201', {
      status: 'ready',
      boardColumn: 'Ready',
      retryCount: 1,
      reviewNote: 'Missing error handling in catch block',
    });

    const retried = await store.getTask('task-gh-201');
    expect(retried?.status).toBe('ready');
    expect(retried?.retryCount).toBe(1);
    expect(retried?.reviewNote).toBe('Missing error handling in catch block');
  });

  it('task fails after max retries', async () => {
    await store.createTask({
      id: 'task-gh-301',
      epicId: null,
      title: 'Complex task',
      description: 'Hard to get right',
      assignedAgent: 'frontend',
      status: 'review',
      githubIssueNumber: 301,
      boardColumn: 'Review',
      priority: 3,
      complexity: 'high',
      dependencies: [],
      labels: [],
      retryCount: 3,
      createdAt: new Date(),
      startedAt: new Date(),
      completedAt: null,
      reviewNote: null,
    });

    // Max retries reached → Failed
    await store.updateTask('task-gh-301', {
      status: 'failed',
      boardColumn: 'Failed',
      reviewNote: 'Final failure after 3 attempts',
    });

    const failed = await store.getTask('task-gh-301');
    expect(failed?.status).toBe('failed');
    expect(failed?.boardColumn).toBe('Failed');
  });

  it('dependency chain: completing task promotes dependents', async () => {
    // Task A (no deps) and Task B (depends on A)
    await store.createTask({
      id: 'task-gh-401', epicId: 'epic-2', title: 'Task A',
      description: '', assignedAgent: 'backend', status: 'done',
      githubIssueNumber: 401, boardColumn: 'Done', priority: 2,
      complexity: 'medium', dependencies: [], labels: [],
      retryCount: 0, createdAt: new Date(), startedAt: new Date(),
      completedAt: new Date(), reviewNote: null,
    });
    await store.createTask({
      id: 'task-gh-402', epicId: 'epic-2', title: 'Task B',
      description: '', assignedAgent: 'frontend', status: 'backlog',
      githubIssueNumber: 402, boardColumn: 'Backlog', priority: 3,
      complexity: 'medium', dependencies: ['task-gh-401'], labels: [],
      retryCount: 0, createdAt: new Date(), startedAt: null,
      completedAt: null, reviewNote: null,
    });

    // Check Task A is done
    const depTask = await store.getTask('task-gh-401');
    expect(depTask?.boardColumn).toBe('Done');

    // Simulate Dispatcher promoting Task B (all deps done)
    const backlogTasks = await store.getTasksByColumn('Backlog');
    for (const task of backlogTasks) {
      const depIds = (task.dependencies as string[]) ?? [];
      let allDone = true;
      for (const depId of depIds) {
        const dep = await store.getTask(depId);
        if (!dep || dep.boardColumn !== 'Done') allDone = false;
      }
      if (allDone && depIds.length > 0) {
        await store.updateTask(task.id, { status: 'ready', boardColumn: 'Ready' });
      }
    }

    const promoted = await store.getTask('task-gh-402');
    expect(promoted?.status).toBe('ready');
    expect(promoted?.boardColumn).toBe('Ready');
  });
});

describe('E2E Pipeline — Dashboard Event Mapping', () => {
  let store: IStateStore;
  let mapper: EventMapper;

  beforeEach(() => {
    store = createMockStateStore();
    const dashStore = createDashboardStateStore(store);
    mapper = new EventMapper(dashStore);
  });

  it('token.usage message maps to token.usage dashboard event', async () => {
    const msg: Message = {
      id: 'tu-1',
      type: MESSAGE_TYPES.TOKEN_USAGE,
      from: 'backend',
      to: null,
      payload: { inputTokens: 500, outputTokens: 200 },
      traceId: 'trace-tu-1',
      timestamp: new Date(),
    };

    const events = await mapper.map(msg);

    const tokenEvent = events.find((e) => e.type === 'token.usage');
    expect(tokenEvent).toBeDefined();
    expect(tokenEvent!.payload).toMatchObject({
      agentId: 'backend',
      inputTokens: 500,
      outputTokens: 200,
    });

    // Also emits raw message log
    const messageEvent = events.find((e) => e.type === 'message');
    expect(messageEvent).toBeDefined();
  });

  it('agent.status with taskId passes through to dashboard event', async () => {
    const msg: Message = {
      id: 'as-1',
      type: MESSAGE_TYPES.AGENT_STATUS,
      from: 'frontend',
      to: null,
      payload: { status: 'busy', taskId: 'task-gh-42' },
      traceId: 'trace-as-1',
      timestamp: new Date(),
    };

    const events = await mapper.map(msg);

    const statusEvent = events.find((e) => e.type === 'agent.status');
    expect(statusEvent).toBeDefined();
    expect(statusEvent!.payload).toMatchObject({
      agentId: 'frontend',
      status: 'working',
      task: 'task-gh-42',
    });

    const bubbleEvent = events.find((e) => e.type === 'agent.bubble');
    expect(bubbleEvent).toBeDefined();
    expect((bubbleEvent!.payload as any).bubble.type).toBe('task');
  });

  it('full message flow: MessageBus → EventMapper → DashboardEvents', async () => {
    const bus = createMockMessageBus();
    const dashBus = createDashboardMessageBus(bus);

    const collectedEvents: Array<{ type: string; payload: unknown }> = [];

    dashBus.subscribeAll(async (message) => {
      const events = await mapper.map(message);
      collectedEvents.push(...events);
    });

    // 1. Agent goes busy
    await bus.publish({
      id: 'f-1', type: MESSAGE_TYPES.AGENT_STATUS, from: 'backend', to: null,
      payload: { status: 'busy', taskId: 'task-1' }, traceId: 't1', timestamp: new Date(),
    });

    // 2. Token usage reported
    await bus.publish({
      id: 'f-2', type: MESSAGE_TYPES.TOKEN_USAGE, from: 'backend', to: null,
      payload: { inputTokens: 1000, outputTokens: 500 }, traceId: 't2', timestamp: new Date(),
    });

    // 3. Agent goes idle
    await bus.publish({
      id: 'f-3', type: MESSAGE_TYPES.AGENT_STATUS, from: 'backend', to: null,
      payload: { status: 'idle' }, traceId: 't3', timestamp: new Date(),
    });

    // Verify event sequence
    const types = collectedEvents.map((e) => e.type);
    expect(types).toContain('agent.status');
    expect(types).toContain('agent.bubble');
    expect(types).toContain('token.usage');
    expect(types).toContain('message');

    // Verify token event content
    const tokenEvt = collectedEvents.find((e) => e.type === 'token.usage');
    expect((tokenEvt!.payload as any).inputTokens).toBe(1000);

    // Verify idle clears bubble
    const bubbleEvents = collectedEvents.filter((e) => e.type === 'agent.bubble');
    const lastBubble = bubbleEvents[bubbleEvents.length - 1];
    expect((lastBubble.payload as any).bubble).toBeNull();
  });

  it('epic.progress event flows correctly', async () => {
    const msg: Message = {
      id: 'ep-1',
      type: MESSAGE_TYPES.EPIC_PROGRESS,
      from: 'director',
      to: null,
      payload: { epicId: 'epic-1', title: 'Dashboard MVP', progress: 0.75 },
      traceId: 'trace-ep-1',
      timestamp: new Date(),
    };

    const events = await mapper.map(msg);
    const epicEvent = events.find((e) => e.type === 'epic.progress');
    expect(epicEvent!.payload).toMatchObject({
      epicId: 'epic-1',
      progress: 0.75,
    });
  });
});
