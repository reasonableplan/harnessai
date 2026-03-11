import { describe, it, expect, vi, beforeEach } from 'vitest';
import { GitAgent } from './git-agent.js';
import type {
  AgentDependencies,
  Task,
  IMessageBus,
  IStateStore,
  IGitService,
} from '@agent/core';

// ===== Mocks =====

function createMockMessageBus(): IMessageBus {
  return {
    publish: vi.fn(),
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
    getTask: vi.fn(),
    updateTask: vi.fn(),
    getTasksByColumn: vi.fn(),
    getTasksByAgent: vi.fn(),
    getReadyTasksForAgent: vi.fn(),
    claimTask: vi.fn(),
    createEpic: vi.fn(),
    getEpic: vi.fn(),
    updateEpic: vi.fn(),
    saveMessage: vi.fn(),
    saveArtifact: vi.fn(),
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
    getEpicIssues: vi.fn().mockResolvedValue([]),
    getAllProjectItems: vi.fn(),
    moveIssueToColumn: vi.fn(),
    addComment: vi.fn(),
    createBranch: vi.fn(),
    createPR: vi.fn().mockResolvedValue(42),
  };
}

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-1',
    epicId: 'epic-1',
    title: 'Create branch for epic',
    description: 'Branch task',
    assignedAgent: 'git',
    status: 'in-progress',
    githubIssueNumber: 10,
    boardColumn: 'In Progress',
    dependencies: [],
    priority: 2,
    complexity: 'low',
    retryCount: 0,
    artifacts: [],
    ...overrides,
  };
}

// ===== Tests =====

describe('GitAgent', () => {
  let deps: AgentDependencies;
  let gitService: IGitService;
  let stateStore: IStateStore;
  let agent: GitAgent;

  beforeEach(() => {
    gitService = createMockGitService();
    stateStore = createMockStateStore();
    deps = {
      messageBus: createMockMessageBus(),
      stateStore,
      gitService,
    };
    agent = new GitAgent(deps, { workDir: '/tmp/test-work' });
  });

  it('has correct id and domain', () => {
    expect(agent.id).toBe('git');
    expect(agent.domain).toBe('git');
    expect(agent.config.level).toBe(2);
  });

  // ===== detectTaskType (tested via executeTask) =====

  it('handles branch task and calls createBranch', async () => {
    const task = makeTask({ title: 'Create branch for epic-1' });
    // Access executeTask via the public-facing method (cast to any for testing private)
    const result = await (agent as any).executeTask(task);

    expect(result.success).toBe(true);
    expect(result.data.branchName).toBe('epic/epic-1');
    expect(gitService.createBranch).toHaveBeenCalledWith('epic/epic-1');
  });

  it('handles duplicate branch gracefully', async () => {
    (gitService.createBranch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('Reference already exists'),
    );

    const task = makeTask({ title: 'Create branch for epic-1' });
    const result = await (agent as any).executeTask(task);

    expect(result.success).toBe(true);
    expect(result.data.alreadyExisted).toBe(true);
  });

  it('handles PR task and calls createPR', async () => {
    const task = makeTask({
      title: '[GIT] Epic epic-1 PR',
      description: 'PR body',
      epicId: 'epic-1',
    });
    // title contains 'pr' → detected as PR task
    const result = await (agent as any).executeTask(task);

    expect(result.success).toBe(true);
    expect(result.data.prNumber).toBe(42);
    expect(gitService.createPR).toHaveBeenCalledWith(
      'Epic epic-1 PR',
      'PR body',
      'epic/epic-1',
      'main',
    );
  });

  it('handles duplicate PR gracefully', async () => {
    (gitService.createPR as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('A pull request already exists for this branch'),
    );

    const task = makeTask({ title: '[GIT] PR for epic', epicId: 'epic-2' });
    const result = await (agent as any).executeTask(task);

    expect(result.success).toBe(true);
    expect(result.data.alreadyExisted).toBe(true);
  });

  it('returns error for unknown task type', async () => {
    const task = makeTask({ title: 'do something random' });
    const result = await (agent as any).executeTask(task);

    expect(result.success).toBe(false);
    expect(result.error?.message).toContain('Unknown git task type');
  });

  // ===== onTaskComplete (BaseAgent 기본: Review 컬럼 → review.request) =====

  it('moves issue to Review on success (Director review 대기)', async () => {
    const task = makeTask({ githubIssueNumber: 10 });
    const result = { success: true, artifacts: [] };

    await (agent as any).onTaskComplete(task, result);

    expect(gitService.moveIssueToColumn).toHaveBeenCalledWith(10, 'Review');
    expect(stateStore.updateTask).toHaveBeenCalledWith('task-1', expect.objectContaining({
      status: 'review',
      boardColumn: 'Review',
    }));
    // review.request 메시지 발행 확인
    expect(deps.messageBus.publish).toHaveBeenCalledWith(expect.objectContaining({
      type: 'review.request',
      from: 'git',
      payload: expect.objectContaining({ taskId: 'task-1' }),
    }));
  });

  it('moves issue to Failed on failure', async () => {
    const task = makeTask({ githubIssueNumber: 10 });
    const result = { success: false, error: { message: 'oops' }, artifacts: [] };

    await (agent as any).onTaskComplete(task, result);

    expect(gitService.moveIssueToColumn).toHaveBeenCalledWith(10, 'Failed');
    expect(stateStore.updateTask).toHaveBeenCalledWith('task-1', expect.objectContaining({
      status: 'failed',
      boardColumn: 'Failed',
    }));
  });

  it('skips board move when no githubIssueNumber', async () => {
    const task = makeTask({ githubIssueNumber: null });
    const result = { success: true, artifacts: [] };

    await (agent as any).onTaskComplete(task, result);

    expect(gitService.moveIssueToColumn).not.toHaveBeenCalled();
    expect(stateStore.updateTask).toHaveBeenCalled();
  });

  // ===== extractBranchName =====

  it('generates branch name from epicId', () => {
    const task = makeTask({ epicId: 'auth-system' });
    const name = (agent as any).extractBranchName(task);
    expect(name).toBe('epic/auth-system');
  });

  it('uses "feature" when epicId is null', () => {
    const task = makeTask({ epicId: null });
    const name = (agent as any).extractBranchName(task);
    expect(name).toBe('epic/feature');
  });

  // ===== checkAndTriggerPR =====

  it('triggers PR issue when all code and commits are done', async () => {
    (gitService.getEpicIssues as ReturnType<typeof vi.fn>).mockResolvedValueOnce([
      { issueNumber: 1, labels: ['agent:backend'], column: 'Done' },
      { issueNumber: 2, labels: ['type:commit'], column: 'Done' },
    ]);

    await (agent as any).checkAndTriggerPR('epic-1');

    expect(gitService.createIssue).toHaveBeenCalledWith(
      expect.objectContaining({
        labels: expect.arrayContaining(['agent:git', 'type:pr', 'epic:epic-1']),
      }),
    );
  });

  it('does not trigger PR when commits are not done', async () => {
    (gitService.getEpicIssues as ReturnType<typeof vi.fn>).mockResolvedValueOnce([
      { issueNumber: 1, labels: ['agent:backend'], column: 'Done' },
      { issueNumber: 2, labels: ['type:commit'], column: 'In Progress' },
    ]);

    await (agent as any).checkAndTriggerPR('epic-1');

    expect(gitService.createIssue).not.toHaveBeenCalled();
  });

  it('does not trigger PR when one already exists', async () => {
    (gitService.getEpicIssues as ReturnType<typeof vi.fn>).mockResolvedValueOnce([
      { issueNumber: 1, labels: ['agent:backend'], column: 'Done' },
      { issueNumber: 2, labels: ['type:commit'], column: 'Done' },
      { issueNumber: 3, labels: ['type:pr'], column: 'In Progress' },
    ]);

    await (agent as any).checkAndTriggerPR('epic-1');

    expect(gitService.createIssue).not.toHaveBeenCalled();
  });
});
