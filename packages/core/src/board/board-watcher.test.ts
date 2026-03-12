import { describe, it, expect, vi, beforeEach } from 'vitest';
import { BoardWatcher } from './board-watcher.js';
import type { IGitService, IStateStore, IMessageBus, BoardIssue } from '../types/index.js';

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

function createMockStateStore(): IStateStore {
  return {
    registerAgent: vi.fn(),
    getAgent: vi.fn(),
    updateAgentStatus: vi.fn(),
    updateHeartbeat: vi.fn(),
    createTask: vi.fn(),
    getTask: vi.fn().mockResolvedValue(null),
    updateTask: vi.fn(),
    getTasksByColumn: vi.fn(),
    getTasksByAgent: vi.fn(),
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

function createMockMessageBus(): IMessageBus {
  return {
    publish: vi.fn(),
    subscribe: vi.fn(),
    subscribeAll: vi.fn(),
    unsubscribe: vi.fn(),
  };
}

function makeIssue(overrides: Partial<BoardIssue> = {}): BoardIssue {
  return {
    issueNumber: 1,
    title: 'Test issue',
    body: 'Test body',
    labels: ['agent:git'],
    column: 'Ready',
    dependencies: [],
    assignee: null,
    generatedBy: 'git',
    epicId: null,
    ...overrides,
  };
}

describe('BoardWatcher', () => {
  let gitService: IGitService;
  let stateStore: IStateStore;
  let messageBus: IMessageBus;
  let watcher: BoardWatcher;

  beforeEach(() => {
    gitService = createMockGitService();
    stateStore = createMockStateStore();
    messageBus = createMockMessageBus();
    watcher = new BoardWatcher(gitService, stateStore, messageBus);
  });

  it('sync calls getAllProjectItems once per cycle', async () => {
    await watcher.sync();
    expect(gitService.getAllProjectItems).toHaveBeenCalledTimes(1);
  });

  it('sync creates new tasks from board issues', async () => {
    const issue = makeIssue({ issueNumber: 42, column: 'Ready' });
    vi.mocked(gitService.getAllProjectItems).mockResolvedValueOnce([issue]);
    vi.mocked(stateStore.getTask).mockResolvedValue(null);

    await watcher.sync();

    expect(stateStore.createTask).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 'task-gh-42',
        title: 'Test issue',
        boardColumn: 'Ready',
        status: 'ready',
        assignedAgent: 'git', // extracted from agent:git label
      }),
    );
  });

  it('sync updates existing tasks', async () => {
    const issue = makeIssue({ issueNumber: 42, column: 'In Progress' });
    vi.mocked(gitService.getAllProjectItems).mockResolvedValueOnce([issue]);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    vi.mocked(stateStore.getTask).mockResolvedValue({ id: 'task-gh-42' } as any);

    await watcher.sync();

    expect(stateStore.updateTask).toHaveBeenCalledWith('task-gh-42', {
      boardColumn: 'In Progress',
      status: 'in-progress',
      assignedAgent: 'git',
      labels: ['agent:git'],
      dependencies: [],
    });
  });

  it('sync detects column changes and publishes board.move', async () => {
    const issueReady = makeIssue({ issueNumber: 10, column: 'Ready' });
    const issueInProgress = makeIssue({ issueNumber: 10, column: 'In Progress' });

    // First sync: issue in Ready
    vi.mocked(gitService.getAllProjectItems).mockResolvedValueOnce([issueReady]);
    await watcher.sync();

    // Second sync: issue moved to In Progress
    vi.mocked(gitService.getAllProjectItems).mockResolvedValueOnce([issueInProgress]);
    await watcher.sync();

    expect(messageBus.publish).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'board.move',
        payload: expect.objectContaining({
          issueNumber: 10,
          fromColumn: 'Ready',
          toColumn: 'In Progress',
        }),
      }),
    );
  });

  it('sync does not publish board.move when column unchanged', async () => {
    const issue = makeIssue({ issueNumber: 10, column: 'Ready' });
    vi.mocked(gitService.getAllProjectItems).mockResolvedValue([issue]);

    await watcher.sync();
    await watcher.sync();

    expect(messageBus.publish).not.toHaveBeenCalled();
  });

  it('sync extracts assignedAgent from agent:X label', async () => {
    const issue = makeIssue({
      issueNumber: 5,
      labels: ['agent:backend', 'type:api'],
      column: 'Backlog',
    });
    vi.mocked(gitService.getAllProjectItems).mockResolvedValueOnce([issue]);

    await watcher.sync();

    expect(stateStore.createTask).toHaveBeenCalledWith(
      expect.objectContaining({ assignedAgent: 'backend' }),
    );
  });

  it('start and stop control polling state', () => {
    watcher.start();
    watcher.start(); // no-op
    watcher.stop();
  });

  // ===== Diff-based optimization =====

  it('skips DB sync for unchanged issues on subsequent syncs', async () => {
    const issue = makeIssue({ issueNumber: 10, column: 'Ready' });
    vi.mocked(gitService.getAllProjectItems).mockResolvedValue([issue]);

    // First sync: new issue → should create task
    await watcher.sync();
    expect(stateStore.createTask).toHaveBeenCalledTimes(1);

    // Second sync: same column → should NOT call getTask or createTask again
    vi.mocked(stateStore.createTask).mockClear();
    vi.mocked(stateStore.getTask).mockClear();
    await watcher.sync();
    expect(stateStore.getTask).not.toHaveBeenCalled();
    expect(stateStore.createTask).not.toHaveBeenCalled();
  });

  it('syncs DB when issue column changes', async () => {
    const issueReady = makeIssue({ issueNumber: 10, column: 'Ready' });
    vi.mocked(gitService.getAllProjectItems).mockResolvedValueOnce([issueReady]);
    await watcher.sync();

    // Column changed → should sync
    const issueInProgress = makeIssue({ issueNumber: 10, column: 'In Progress' });
    vi.mocked(gitService.getAllProjectItems).mockResolvedValueOnce([issueInProgress]);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    vi.mocked(stateStore.getTask).mockResolvedValueOnce({
      id: 'task-gh-10',
      status: 'ready',
    } as any);
    await watcher.sync();

    expect(stateStore.getTask).toHaveBeenCalledWith('task-gh-10');
    expect(stateStore.updateTask).toHaveBeenCalled();
  });

  // ===== Deleted issue handling =====

  it('publishes board.remove when issue disappears from board', async () => {
    const issue = makeIssue({ issueNumber: 20, column: 'In Progress' });
    vi.mocked(gitService.getAllProjectItems).mockResolvedValueOnce([issue]);
    await watcher.sync();

    // Second sync: issue gone
    vi.mocked(gitService.getAllProjectItems).mockResolvedValueOnce([]);
    await watcher.sync();

    expect(messageBus.publish).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'board.remove',
        payload: { issueNumber: 20, lastColumn: 'In Progress' },
      }),
    );
  });

  it('does not publish board.remove on first sync (no previous state)', async () => {
    vi.mocked(gitService.getAllProjectItems).mockResolvedValueOnce([]);
    await watcher.sync();
    expect(messageBus.publish).not.toHaveBeenCalled();
  });

  // ===== Webhook triggerSync =====

  it('triggerSync calls sync immediately', async () => {
    const issue = makeIssue({ issueNumber: 30, column: 'Backlog' });
    vi.mocked(gitService.getAllProjectItems).mockResolvedValueOnce([issue]);

    await watcher.triggerSync();

    expect(gitService.getAllProjectItems).toHaveBeenCalledTimes(1);
    expect(stateStore.createTask).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'task-gh-30' }),
    );
  });

  it('triggerSync handles errors without throwing', async () => {
    vi.mocked(gitService.getAllProjectItems).mockRejectedValueOnce(new Error('API down'));

    // Should not throw
    await expect(watcher.triggerSync()).resolves.toBeUndefined();
  });
});
