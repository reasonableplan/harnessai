import { describe, it, expect, vi, beforeEach } from 'vitest';
import { DirectorAgent } from './director-agent.js';
import type { IClaudeClient } from './director-agent.js';
import type {
  AgentDependencies,
  IMessageBus,
  IStateStore,
  IGitService,
  Message,
  Task,
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
    getTasksByColumn: vi.fn().mockResolvedValue([]),
    getTasksByAgent: vi.fn(),
    getReadyTasksForAgent: vi.fn().mockResolvedValue([]),
    claimTask: vi.fn(),
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
  let issueCounter = 100;
  return {
    validateConnection: vi.fn(),
    createIssue: vi.fn().mockImplementation(() => Promise.resolve(++issueCounter)),
    updateIssue: vi.fn(),
    closeIssue: vi.fn(),
    getIssue: vi.fn(),
    getIssuesByLabel: vi.fn(),
    getEpicIssues: vi.fn().mockResolvedValue([]),
    getAllProjectItems: vi.fn(),
    moveIssueToColumn: vi.fn(),
    addComment: vi.fn(),
    createBranch: vi.fn(),
    createPR: vi.fn(),
  };
}

function createMockClaude(response: unknown): IClaudeClient {
  return {
    chat: vi.fn().mockResolvedValue({
      content: JSON.stringify(response),
      usage: { inputTokens: 100, outputTokens: 50 },
    }),
    chatJSON: vi.fn().mockResolvedValue({
      data: response,
      usage: { inputTokens: 100, outputTokens: 50 },
    }),
  };
}

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-1',
    epicId: null,
    title: 'Test task',
    description: 'Test description',
    assignedAgent: 'director',
    status: 'in-progress',
    githubIssueNumber: null,
    boardColumn: 'In Progress',
    dependencies: [],
    priority: 3,
    complexity: 'medium',
    retryCount: 0,
    artifacts: [],
    ...overrides,
  };
}

function makeReviewMessage(taskId: string, success: boolean): Message {
  return {
    id: 'msg-1',
    type: 'review.request',
    from: 'backend',
    to: null,
    payload: {
      taskId,
      result: success
        ? { success: true, artifacts: [] }
        : { success: false, error: { message: 'oops' }, artifacts: [] },
    },
    traceId: 'trace-1',
    timestamp: new Date(),
  };
}

// ===== Tests =====

describe('DirectorAgent', () => {
  let deps: AgentDependencies;
  let messageBus: IMessageBus;
  let stateStore: IStateStore;
  let gitService: IGitService;
  let mockClaude: IClaudeClient;
  let agent: DirectorAgent;

  beforeEach(() => {
    messageBus = createMockMessageBus();
    stateStore = createMockStateStore();
    gitService = createMockGitService();
    deps = { messageBus, stateStore, gitService };
    mockClaude = createMockClaude({ action: 'clarify', message: 'default' });
    agent = new DirectorAgent(deps, { claudeClient: mockClaude });
  });

  // ===== Basic Structure =====

  it('has correct id, domain, and level', () => {
    expect(agent.id).toBe('director');
    expect(agent.domain).toBe('orchestration');
    expect(agent.config.level).toBe(0);
  });

  it('subscribes to review.request and board.move on construction', () => {
    expect(messageBus.subscribe).toHaveBeenCalledWith('review.request', expect.any(Function));
    expect(messageBus.subscribe).toHaveBeenCalledWith('board.move', expect.any(Function));
  });

  // ===== handleUserInput =====

  it('handles create_epic action from Claude with named task ids', async () => {
    mockClaude = createMockClaude({
      action: 'create_epic',
      title: 'Login Feature',
      description: 'Implement login',
      tasks: [
        {
          id: 'branch',
          title: 'Create branch',
          agent: 'git',
          description: 'Branch for login',
          dependencies: [],
        },
        {
          id: 'api',
          title: 'Backend API',
          agent: 'backend',
          description: 'Login endpoint',
          dependencies: ['branch'],
        },
      ],
    });
    agent = new DirectorAgent(deps, { claudeClient: mockClaude });

    const result = await agent.handleUserInput('로그인 기능 만들어줘');

    expect(result).toContain('Login Feature');
    expect(result).toContain('2 tasks');
    expect(stateStore.createEpic).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Login Feature',
        status: 'planning',
      }),
    );
    expect(stateStore.createTask).toHaveBeenCalledTimes(2);
    expect(gitService.createIssue).toHaveBeenCalledTimes(2);

    // 두 번째 issue의 body에 Epic 컨텍스트와 의존성 정보가 포함되어야 함
    const secondCall = vi.mocked(gitService.createIssue).mock.calls[1][0] as {
      body: string;
      dependencies: number[];
    };
    expect(secondCall.body).toContain('**Epic:** Login Feature');
    expect(secondCall.body).toContain('**Depends on:** #101');
    expect(secondCall.dependencies).toEqual([101]); // branch task의 issue number

    expect(gitService.moveIssueToColumn).toHaveBeenCalledWith(expect.any(Number), 'Ready');
    expect(stateStore.updateEpic).toHaveBeenCalledWith(expect.any(String), { status: 'active' });
    expect(messageBus.publish).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'epic.progress',
      }),
    );
  });

  it('handles clarify action from Claude', async () => {
    mockClaude = createMockClaude({ action: 'clarify', message: '어떤 인증 방식을 원하시나요?' });
    agent = new DirectorAgent(deps, { claudeClient: mockClaude });

    const result = await agent.handleUserInput('로그인');
    expect(result).toBe('어떤 인증 방식을 원하시나요?');
  });

  it('handles Claude API error gracefully', async () => {
    mockClaude = { chatJSON: vi.fn().mockRejectedValue(new Error('API rate limit exceeded')) };
    agent = new DirectorAgent(deps, { claudeClient: mockClaude });

    const result = await agent.handleUserInput('뭔가 해줘');
    expect(result).toContain('Error processing request');
    expect(result).toContain('API rate limit exceeded');
  });

  it('handles JSON parse failure gracefully', async () => {
    mockClaude = { chatJSON: vi.fn().mockRejectedValue(new SyntaxError('Unexpected token')) };
    agent = new DirectorAgent(deps, { claudeClient: mockClaude });

    const result = await agent.handleUserInput('뭔가 해줘');
    expect(result).toContain('Error processing request');
    expect(result).toContain('Unexpected token');
  });

  // ===== Dependency Promotion (Dispatcher) =====

  it('promotes dependent tasks to Ready when all deps are Done', async () => {
    vi.mocked(stateStore.getTasksByColumn).mockResolvedValueOnce([
      {
        id: 'task-gh-102',
        title: 'Backend API',
        dependencies: ['task-gh-101'],
        boardColumn: 'Backlog',
        githubIssueNumber: 102,
      },
    ] as never);
    vi.mocked(stateStore.getTask).mockResolvedValueOnce({
      id: 'task-gh-101',
      boardColumn: 'Done',
    } as never);

    await (
      agent as never as { checkAndPromoteDependents: (n: number) => Promise<void> }
    ).checkAndPromoteDependents(101);

    expect(gitService.moveIssueToColumn).toHaveBeenCalledWith(102, 'Ready');
    expect(stateStore.updateTask).toHaveBeenCalledWith(
      'task-gh-102',
      expect.objectContaining({
        status: 'ready',
        boardColumn: 'Ready',
      }),
    );
  });

  it('does not promote tasks when deps are not all Done', async () => {
    vi.mocked(stateStore.getTasksByColumn).mockResolvedValueOnce([
      {
        id: 'task-gh-103',
        title: 'PR',
        dependencies: ['task-gh-101', 'task-gh-102'],
        boardColumn: 'Backlog',
        githubIssueNumber: 103,
      },
    ] as never);
    vi.mocked(stateStore.getTask)
      .mockResolvedValueOnce({ id: 'task-gh-101', boardColumn: 'Done' } as never)
      .mockResolvedValueOnce({ id: 'task-gh-102', boardColumn: 'In Progress' } as never);

    await (
      agent as never as { checkAndPromoteDependents: (n: number) => Promise<void> }
    ).checkAndPromoteDependents(101);

    expect(gitService.moveIssueToColumn).not.toHaveBeenCalled();
  });

  it('is idempotent — promoting an already Ready task is safe', async () => {
    // Task is already Ready but promotion is called again (race condition)
    vi.mocked(stateStore.getTasksByColumn).mockResolvedValueOnce([
      {
        id: 'task-gh-102',
        title: 'API',
        dependencies: ['task-gh-101'],
        boardColumn: 'Backlog',
        githubIssueNumber: 102,
      },
    ] as never);
    vi.mocked(stateStore.getTask).mockResolvedValueOnce({
      id: 'task-gh-101',
      boardColumn: 'Done',
    } as never);

    // Call twice — should not throw
    await (
      agent as never as { checkAndPromoteDependents: (n: number) => Promise<void> }
    ).checkAndPromoteDependents(101);

    // Second call: no more backlog tasks
    vi.mocked(stateStore.getTasksByColumn).mockResolvedValueOnce([]);
    await (
      agent as never as { checkAndPromoteDependents: (n: number) => Promise<void> }
    ).checkAndPromoteDependents(101);

    // moveIssueToColumn only called once (first call)
    expect(gitService.moveIssueToColumn).toHaveBeenCalledTimes(1);
  });

  // ===== Review Handler =====

  it('calls Claude review on successful task and approves', async () => {
    // mockClaude의 chatJSON이 handleUserInput + reviewWithClaude 모두에서 호출됨
    // 첫 호출은 beforeEach default, 두 번째는 review
    const reviewClaude = {
      chatJSON: vi.fn().mockResolvedValue({
        data: { approved: true, reason: 'Looks good' },
        usage: { inputTokens: 50, outputTokens: 20 },
      }),
    };
    agent = new DirectorAgent(deps, { claudeClient: reviewClaude });

    vi.mocked(stateStore.getTask).mockResolvedValueOnce(
      makeTask({
        id: 'task-gh-50',
        title: 'API endpoint',
        description: 'Build login API',
        githubIssueNumber: 50,
      }),
    );

    await (agent as never as { onReviewRequest: (m: Message) => Promise<void> }).onReviewRequest(
      makeReviewMessage('task-gh-50', true),
    );

    // Claude review가 호출되었는지 확인
    expect(reviewClaude.chatJSON).toHaveBeenCalledWith(
      expect.stringContaining('code reviewer'),
      expect.stringContaining('API endpoint'),
    );
    // 승인 시 Done으로 이동 + reviewNote 클리어 + 의존성 체인 트리거
    expect(stateStore.updateTask).toHaveBeenCalledWith(
      'task-gh-50',
      expect.objectContaining({
        status: 'done',
        boardColumn: 'Done',
        reviewNote: null,
      }),
    );
    expect(gitService.moveIssueToColumn).toHaveBeenCalledWith(50, 'Done');
    expect(gitService.addComment).toHaveBeenCalledWith(50, expect.stringContaining('Approved'));
  });

  it('retries task when Claude review rejects — saves reviewNote and adds comment', async () => {
    const reviewClaude = {
      chatJSON: vi.fn().mockResolvedValue({
        data: { approved: false, reason: 'Missing tests' },
        usage: { inputTokens: 50, outputTokens: 20 },
      }),
    };
    agent = new DirectorAgent(deps, { claudeClient: reviewClaude });

    vi.mocked(stateStore.getTask).mockResolvedValueOnce(
      makeTask({ id: 'task-gh-50', retryCount: 0, githubIssueNumber: 50 }),
    );

    await (agent as never as { onReviewRequest: (m: Message) => Promise<void> }).onReviewRequest(
      makeReviewMessage('task-gh-50', true),
    );

    // reviewNote가 DB에 저장되어야 함
    expect(stateStore.updateTask).toHaveBeenCalledWith(
      'task-gh-50',
      expect.objectContaining({
        retryCount: 1,
        status: 'ready',
        boardColumn: 'Ready',
        reviewNote: 'Missing tests',
      }),
    );

    // GitHub Issue에 피드백 코멘트 작성
    expect(gitService.addComment).toHaveBeenCalledWith(
      50,
      expect.stringContaining('Revision Requested'),
    );
    expect(gitService.addComment).toHaveBeenCalledWith(
      50,
      expect.stringContaining('Missing tests'),
    );

    // review.feedback 메시지 발행
    expect(messageBus.publish).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'review.feedback',
        to: 'director', // makeTask default assignedAgent
        payload: expect.objectContaining({
          taskId: 'task-gh-50',
          feedback: 'Missing tests',
          retryCount: 1,
        }),
      }),
    );
  });

  it('rejects when Claude review call fails (fail-closed)', async () => {
    const reviewClaude = {
      chatJSON: vi.fn().mockRejectedValue(new Error('API unavailable')),
    };
    agent = new DirectorAgent(deps, { claudeClient: reviewClaude });

    vi.mocked(stateStore.getTask).mockResolvedValueOnce(
      makeTask({ id: 'task-gh-50', githubIssueNumber: 50, retryCount: 0 }),
    );

    await (agent as never as { onReviewRequest: (m: Message) => Promise<void> }).onReviewRequest(
      makeReviewMessage('task-gh-50', true),
    );

    // Fail-closed: 리뷰 서비스 장애 시 거부하여 품질 게이트 유지
    expect(stateStore.updateTask).toHaveBeenCalledWith(
      'task-gh-50',
      expect.objectContaining({
        status: 'ready',
        boardColumn: 'Ready',
        retryCount: 1,
      }),
    );
    expect(gitService.moveIssueToColumn).toHaveBeenCalledWith(50, 'Ready');
  });

  it('retries failed task when under max retries — saves error as reviewNote', async () => {
    vi.mocked(stateStore.getTask).mockResolvedValueOnce({
      id: 'task-gh-50',
      retryCount: 1,
      githubIssueNumber: 50,
    } as never);

    await (agent as never as { onReviewRequest: (m: Message) => Promise<void> }).onReviewRequest(
      makeReviewMessage('task-gh-50', false),
    );

    expect(stateStore.updateTask).toHaveBeenCalledWith(
      'task-gh-50',
      expect.objectContaining({
        retryCount: 2,
        status: 'ready',
        boardColumn: 'Ready',
        reviewNote: 'oops',
      }),
    );
    expect(gitService.moveIssueToColumn).toHaveBeenCalledWith(50, 'Ready');
    expect(gitService.addComment).toHaveBeenCalledWith(50, expect.stringContaining('oops'));
  });

  it('marks task as failed when max retries exceeded — includes final feedback', async () => {
    vi.mocked(stateStore.getTask).mockResolvedValueOnce({
      id: 'task-gh-50',
      retryCount: 3,
      githubIssueNumber: 50,
    } as never);

    await (agent as never as { onReviewRequest: (m: Message) => Promise<void> }).onReviewRequest(
      makeReviewMessage('task-gh-50', false),
    );

    // 최대 재시도 초과 시 Failed로 마킹 + 최종 피드백 저장
    expect(stateStore.updateTask).toHaveBeenCalledWith(
      'task-gh-50',
      expect.objectContaining({
        status: 'failed',
        boardColumn: 'Failed',
        reviewNote: expect.stringContaining('oops'),
      }),
    );
    expect(gitService.moveIssueToColumn).toHaveBeenCalledWith(50, 'Failed');
    expect(gitService.addComment).toHaveBeenCalledWith(
      50,
      expect.stringContaining('max retries exceeded'),
    );
  });

  // ===== executeTask =====

  it('executeTask delegates to handleUserInput', async () => {
    mockClaude = createMockClaude({ action: 'clarify', message: 'What do you need?' });
    agent = new DirectorAgent(deps, { claudeClient: mockClaude });

    const task = makeTask({ title: 'Plan new feature', description: 'Build a todo app' });
    const result = await (
      agent as never as {
        executeTask: (t: Task) => Promise<{ success: boolean; data: { response: string } }>;
      }
    ).executeTask(task);

    expect(result.success).toBe(true);
    expect(result.data.response).toBe('What do you need?');
  });
});
