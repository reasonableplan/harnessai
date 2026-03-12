import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { BaseAgent } from './base-agent.js';
import type {
  AgentConfig,
  IMessageBus,
  IStateStore,
  IGitService,
  Message,
  Task,
  TaskResult,
} from '../types/index.js';

class TestAgent extends BaseAgent {
  public executeTaskFn = vi
    .fn<(task: Task) => Promise<TaskResult>>()
    .mockResolvedValue({ success: true, artifacts: [] });

  protected async executeTask(task: Task): Promise<TaskResult> {
    return this.executeTaskFn(task);
  }
}

function createMockMessageBus(): IMessageBus {
  return {
    publish: vi.fn<(msg: Message) => Promise<void>>().mockResolvedValue(undefined),
    subscribe: vi.fn(),
    subscribeAll: vi.fn(),
    unsubscribe: vi.fn(),
  };
}

function createMockStateStore(): IStateStore {
  return {
    registerAgent: vi.fn(),
    getAgent: vi.fn(),
    updateAgentStatus: vi.fn(),
    updateHeartbeat: vi.fn(),
    createTask: vi.fn(),
    getTask: vi.fn().mockResolvedValue(null),
    updateTask: vi.fn(),
    getTasksByColumn: vi.fn().mockResolvedValue([]),
    getTasksByAgent: vi.fn().mockResolvedValue([]),
    getReadyTasksForAgent: vi.fn().mockResolvedValue([]),
    claimTask: vi.fn().mockResolvedValue(true),
    createEpic: vi.fn(),
    getEpic: vi.fn(),
    updateEpic: vi.fn(),
    saveMessage: vi.fn(),
    saveArtifact: vi.fn(),
    getAllAgents: vi.fn().mockResolvedValue([]),
    getAllTasks: vi.fn().mockResolvedValue([]),
    getAllEpics: vi.fn().mockResolvedValue([]),
    getRecentMessages: vi.fn().mockResolvedValue([]),
    transaction: vi.fn().mockImplementation((fn) => fn({})),
  };
}

function createMockGitService(): IGitService {
  return {
    validateConnection: vi.fn(),
    createIssue: vi.fn(),
    updateIssue: vi.fn(),
    closeIssue: vi.fn(),
    getIssue: vi.fn(),
    getIssuesByLabel: vi.fn(),
    getEpicIssues: vi.fn(),
    getAllProjectItems: vi.fn().mockResolvedValue([]),
    moveIssueToColumn: vi.fn(),
    addComment: vi.fn(),
    createBranch: vi.fn(),
    createPR: vi.fn(),
  };
}

const TEST_CONFIG: AgentConfig = {
  id: 'test-agent',
  domain: 'test',
  level: 2,
  claudeModel: 'claude-sonnet-4-20250514',
  maxTokens: 8192,
  temperature: 0.2,
  tokenBudget: 50_000,
};

const MOCK_TASK_ROW = {
  id: 'task-001',
  epicId: 'epic-001',
  title: 'Test task',
  description: 'A test task',
  assignedAgent: 'test-agent',
  status: 'ready',
  githubIssueNumber: 1,
  boardColumn: 'Ready',
  priority: 3,
  complexity: 'medium',
  dependencies: [],
  labels: [],
  retryCount: 0,
  createdAt: new Date(),
  startedAt: null,
  completedAt: null,
  reviewNote: null,
};

/**
 * Flush all pending microtasks and timers for one poll cycle.
 * BaseAgent uses `setTimeout` recursive loop, so we advance timers
 * and flush microtasks to let the async poll loop proceed.
 */
async function flushPollCycle(intervalMs: number) {
  // Flush pending microtasks first (any in-flight async work)
  await vi.advanceTimersByTimeAsync(intervalMs);
}

describe('BaseAgent', () => {
  let bus: IMessageBus;
  let store: IStateStore;
  let git: IGitService;
  let agent: TestAgent;

  beforeEach(() => {
    vi.useFakeTimers();
    bus = createMockMessageBus();
    store = createMockStateStore();
    git = createMockGitService();
    agent = new TestAgent(TEST_CONFIG, {
      messageBus: bus,
      stateStore: store,
      gitService: git,
    });
  });

  afterEach(() => {
    agent.stopPolling();
    vi.useRealTimers();
  });

  it('초기 상태는 idle이다', () => {
    expect(agent.status).toBe('idle');
  });

  it('config에서 id, domain이 설정된다', () => {
    expect(agent.id).toBe('test-agent');
    expect(agent.domain).toBe('test');
  });

  it('startPolling 후 findNextTask가 DB를 조회한다', async () => {
    agent.startPolling(50);

    await flushPollCycle(50);

    expect(store.getReadyTasksForAgent).toHaveBeenCalledWith('test-agent');
  });

  it('DB에 Ready 태스크가 있으면 claimTask 후 executeTask가 호출된다', async () => {
    vi.mocked(store.getReadyTasksForAgent).mockResolvedValueOnce([MOCK_TASK_ROW]);
    vi.mocked(store.claimTask).mockResolvedValueOnce(true);
    agent.startPolling(50);

    await flushPollCycle(50);

    expect(store.claimTask).toHaveBeenCalledWith('task-001');
    expect(agent.executeTaskFn).toHaveBeenCalled();
    expect(git.moveIssueToColumn).toHaveBeenCalledWith(1, 'In Progress');
  });

  it('claimTask 실패 시 다음 태스크를 시도한다', async () => {
    const task1 = { ...MOCK_TASK_ROW, id: 'task-claimed', priority: 1 };
    const task2 = { ...MOCK_TASK_ROW, id: 'task-available', priority: 2, githubIssueNumber: 2 };
    vi.mocked(store.getReadyTasksForAgent).mockResolvedValueOnce([task1, task2]);
    vi.mocked(store.claimTask)
      .mockResolvedValueOnce(false) // task1: already claimed
      .mockResolvedValueOnce(true); // task2: success
    agent.startPolling(50);

    await flushPollCycle(50);

    expect(store.claimTask).toHaveBeenCalledTimes(2);
    expect(agent.executeTaskFn).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'task-available' }),
    );
  });

  it('모든 claimTask 실패 시 executeTask가 호출되지 않는다', async () => {
    vi.mocked(store.getReadyTasksForAgent).mockResolvedValueOnce([MOCK_TASK_ROW]);
    vi.mocked(store.claimTask).mockResolvedValueOnce(false);
    agent.startPolling(50);

    await flushPollCycle(50);

    expect(agent.executeTaskFn).not.toHaveBeenCalled();
  });

  it('태스크 실행 완료 후 review.request가 발행된다', async () => {
    vi.mocked(store.getReadyTasksForAgent).mockResolvedValueOnce([MOCK_TASK_ROW]);
    agent.startPolling(50);

    await flushPollCycle(50);

    const publishCalls = (bus.publish as ReturnType<typeof vi.fn>).mock.calls;
    const reviewMessages = publishCalls.filter(([msg]: [Message]) => msg.type === 'review.request');
    expect(reviewMessages.length).toBeGreaterThanOrEqual(1);
  });

  it('executeTask 에러 시 error 상태 후 다음 폴링에서 자동 복구된다', async () => {
    vi.mocked(store.getReadyTasksForAgent).mockResolvedValueOnce([MOCK_TASK_ROW]);
    agent.executeTaskFn.mockRejectedValueOnce(new Error('fail'));

    agent.startPolling(50);

    // 첫 폴링 (에러 발생)
    await flushPollCycle(50);
    // 백오프 후 두 번째 폴링 (복구)
    await flushPollCycle(100);

    expect(agent.status).toBe('idle');
  });

  it('중복 startPolling은 무시된다', () => {
    agent.startPolling(50);
    agent.startPolling(50); // 두 번째 호출은 무시
  });

  it('subscribe는 messageBus.subscribe를 호출한다', () => {
    const handler = vi.fn();
    (agent as unknown as { subscribe: (type: string, handler: unknown) => void }).subscribe(
      'board.move',
      handler,
    );
    expect(bus.subscribe).toHaveBeenCalledWith('board.move', handler);
  });

  it('Ready 태스크가 없으면 executeTask가 호출되지 않는다', async () => {
    vi.mocked(store.getReadyTasksForAgent).mockResolvedValue([]);
    agent.startPolling(50);

    await flushPollCycle(50);

    expect(agent.executeTaskFn).not.toHaveBeenCalled();
  });

  it('여러 Ready 태스크 중 priority가 높은 것(숫자 낮은 것)을 선택한다', async () => {
    const lowPriority = { ...MOCK_TASK_ROW, id: 'task-low', priority: 5 };
    const highPriority = { ...MOCK_TASK_ROW, id: 'task-high', priority: 1, githubIssueNumber: 2 };
    vi.mocked(store.getReadyTasksForAgent).mockResolvedValueOnce([lowPriority, highPriority]);

    agent.startPolling(50);
    await flushPollCycle(50);

    expect(agent.executeTaskFn).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'task-high', priority: 1 }),
    );
  });

  it('drain()은 현재 태스크 완료 후 폴링을 멈춘다', async () => {
    vi.mocked(store.getReadyTasksForAgent).mockResolvedValueOnce([MOCK_TASK_ROW]);
    agent.startPolling(50);

    await flushPollCycle(50);

    // drain 호출 — 즉시 폴링 중지
    const drainPromise = agent.drain();
    await flushPollCycle(50);
    await drainPromise;

    // drain 후 더 이상 폴링하지 않음
    vi.mocked(store.getReadyTasksForAgent).mockClear();
    await flushPollCycle(50);
    expect(store.getReadyTasksForAgent).not.toHaveBeenCalled();
  });
});
