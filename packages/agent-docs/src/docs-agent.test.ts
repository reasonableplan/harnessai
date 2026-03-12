import { describe, it, expect, vi, beforeEach } from 'vitest';
import { DocsAgent } from './docs-agent.js';
import { detectTaskType } from './task-router.js';
import type { IClaudeClient } from './doc-generator.js';
import type { AgentDependencies, IMessageBus, IStateStore, IGitService, Task } from '@agent/core';

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
  let issueCounter = 400;
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
      usage: { inputTokens: 250, outputTokens: 300 },
    }),
    chatJSON: vi.fn().mockResolvedValue({
      data: response,
      usage: { inputTokens: 250, outputTokens: 300 },
    }),
  };
}

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-1',
    epicId: 'epic-1',
    title: 'Generate README.md',
    description: 'Create a comprehensive README for the project',
    assignedAgent: 'docs',
    status: 'in-progress',
    githubIssueNumber: 70,
    boardColumn: 'In Progress',
    dependencies: [],
    priority: 3,
    complexity: 'medium',
    retryCount: 0,
    artifacts: [],
    ...overrides,
  };
}

const MOCK_README_GENERATED = {
  files: [
    {
      path: 'README.md',
      content: '# My Project\n\nA multi-agent orchestration system.',
      action: 'create' as const,
      language: 'markdown',
    },
  ],
  summary: 'Generated comprehensive README.md with overview, installation, and usage',
};

const MOCK_API_DOCS_GENERATED = {
  files: [
    {
      path: 'docs/api.md',
      content: '# API Reference\n\n## GET /api/users',
      action: 'create' as const,
      language: 'markdown',
    },
    {
      path: 'docs/api-errors.md',
      content: '# Error Codes\n\n| Code | Description |',
      action: 'create' as const,
      language: 'markdown',
    },
  ],
  summary: 'Generated API documentation with endpoints and error codes',
};

const MOCK_CHANGELOG_GENERATED = {
  files: [
    {
      path: 'CHANGELOG.md',
      content: '# Changelog\n\n## [1.0.0] - 2026-03-10\n\n### Added\n- Initial release',
      action: 'create' as const,
      language: 'markdown',
    },
  ],
  summary: 'Updated CHANGELOG with version 1.0.0 entries',
};

// ===== Task Type Detection (Unit) =====

describe('detectTaskType', () => {
  it('returns label-based type when type:* label exists', () => {
    const task = makeTask({ labels: ['type:changelog.update'] });
    expect(detectTaskType(task)).toBe('changelog.update');
  });

  it('ignores invalid label values', () => {
    const task = makeTask({ title: 'Generate README.md', labels: ['type:invalid'] });
    expect(detectTaskType(task)).toBe('readme.generate');
  });

  it('detects analyze from title', () => {
    expect(detectTaskType(makeTask({ title: 'Analyze documentation gaps', description: '' }))).toBe(
      'analyze',
    );
  });

  it('detects readme.generate from title', () => {
    expect(detectTaskType(makeTask({ title: 'Generate README.md', description: '' }))).toBe(
      'readme.generate',
    );
  });

  it('detects readme.update from title', () => {
    expect(
      detectTaskType(makeTask({ title: 'Update README with new features', description: '' })),
    ).toBe('readme.update');
  });

  it('detects api-docs.generate from title', () => {
    expect(detectTaskType(makeTask({ title: 'Generate API documentation', description: '' }))).toBe(
      'api-docs.generate',
    );
  });

  it('detects api-docs.update from description', () => {
    expect(
      detectTaskType(makeTask({ title: 'Update API docs', description: 'API 문서 수정' })),
    ).toBe('api-docs.update');
  });

  it('detects changelog.update from title', () => {
    expect(detectTaskType(makeTask({ title: 'Update CHANGELOG', description: '' }))).toBe(
      'changelog.update',
    );
  });

  it('detects architecture.generate from title', () => {
    expect(
      detectTaskType(makeTask({ title: 'Generate architecture document', description: '' })),
    ).toBe('architecture.generate');
  });

  it('detects jsdoc.add from title', () => {
    expect(
      detectTaskType(makeTask({ title: 'Add JSDoc comments to auth module', description: '' })),
    ).toBe('jsdoc.add');
  });

  it('detects contributing.generate from title', () => {
    expect(detectTaskType(makeTask({ title: 'Generate CONTRIBUTING.md', description: '' }))).toBe(
      'contributing.generate',
    );
  });

  it('detects env-example.update from title', () => {
    expect(detectTaskType(makeTask({ title: 'Update .env.example', description: '' }))).toBe(
      'env-example.update',
    );
  });

  it('detects activity-log from Korean keyword', () => {
    expect(detectTaskType(makeTask({ title: '작업 이력 문서 생성', description: '' }))).toBe(
      'activity-log.generate',
    );
  });

  it('detects report.daily from keyword', () => {
    expect(detectTaskType(makeTask({ title: 'Generate daily report', description: '' }))).toBe(
      'report.daily',
    );
  });

  it('detects report.epic from keyword', () => {
    expect(
      detectTaskType(makeTask({ title: 'Generate epic progress report', description: '' })),
    ).toBe('report.epic');
  });

  it('detects Korean readme', () => {
    expect(detectTaskType(makeTask({ title: '리드미 생성', description: '' }))).toBe(
      'readme.generate',
    );
  });

  it('detects Korean changelog', () => {
    expect(detectTaskType(makeTask({ title: '변경 이력 갱신', description: '' }))).toBe(
      'changelog.update',
    );
  });

  it('detects generic document keyword with create intent as readme', () => {
    expect(detectTaskType(makeTask({ title: '프로젝트 문서 작성', description: '' }))).toBe(
      'readme.generate',
    );
  });

  it('detects generic document keyword without create intent as analyze', () => {
    expect(detectTaskType(makeTask({ title: '문서 리뷰', description: '' }))).toBe('analyze');
  });

  it('returns unknown for unrecognizable task', () => {
    expect(detectTaskType(makeTask({ title: 'do something', description: 'unrelated work' }))).toBe(
      'unknown',
    );
  });
});

// ===== DocsAgent Integration =====

describe('DocsAgent', () => {
  let deps: AgentDependencies;
  let messageBus: IMessageBus;
  let stateStore: IStateStore;
  let gitService: IGitService;
  let mockClaude: IClaudeClient;
  let agent: DocsAgent;

  beforeEach(() => {
    messageBus = createMockMessageBus();
    stateStore = createMockStateStore();
    gitService = createMockGitService();
    deps = { messageBus, stateStore, gitService };
    mockClaude = createMockClaude(MOCK_README_GENERATED);
    agent = new DocsAgent(deps, { workDir: '/tmp/test-docs', claudeClient: mockClaude });
  });

  // ===== Basic Structure =====

  it('has correct id, domain, and level', () => {
    expect(agent.id).toBe('docs');
    expect(agent.domain).toBe('docs');
    expect(agent.config.level).toBe(2);
  });

  // ===== README Generation Flow =====

  it('generates README, writes files, saves artifacts, and creates commit request', async () => {
    const task = makeTask();
    const result = await callExecuteTask(agent, task);

    expect(result.success).toBe(true);
    expect(result.artifacts).toEqual(['README.md']);
    expect(result.data?.generatedFiles).toEqual(['README.md']);

    // Claude called with docs-specific system prompt
    expect(mockClaude.chatJSON).toHaveBeenCalledWith(
      expect.stringContaining('documentation generator'),
      expect.stringContaining('Generate README.md'),
    );

    // Artifacts saved to DB
    expect(stateStore.saveArtifact).toHaveBeenCalledTimes(1);
    expect(stateStore.saveArtifact).toHaveBeenCalledWith(
      expect.objectContaining({
        taskId: 'task-1',
        filePath: 'README.md',
        createdBy: 'docs',
      }),
    );

    // Git commit follow-up issue created with docs: prefix
    expect(gitService.createIssue).toHaveBeenCalledWith(
      expect.objectContaining({
        title: expect.stringContaining('[GIT] Commit:'),
        labels: expect.arrayContaining(['agent:git', 'type:commit', 'epic:epic-1']),
        dependencies: [70],
      }),
    );
  });

  // ===== API Docs Generation =====

  it('generates API docs with multiple files', async () => {
    mockClaude = createMockClaude(MOCK_API_DOCS_GENERATED);
    agent = new DocsAgent(deps, { workDir: '/tmp/test-docs', claudeClient: mockClaude });

    const task = makeTask({
      title: 'Generate API documentation',
      labels: ['type:api-docs.generate'],
    });
    const result = await callExecuteTask(agent, task);

    expect(result.success).toBe(true);
    expect(result.artifacts).toEqual(['docs/api.md', 'docs/api-errors.md']);
    expect(stateStore.saveArtifact).toHaveBeenCalledTimes(2);
  });

  // ===== Changelog Update =====

  it('generates changelog with proper system prompt', async () => {
    mockClaude = createMockClaude(MOCK_CHANGELOG_GENERATED);
    agent = new DocsAgent(deps, { workDir: '/tmp/test-docs', claudeClient: mockClaude });

    const task = makeTask({ title: 'Update CHANGELOG', labels: ['type:changelog.update'] });
    const result = await callExecuteTask(agent, task);

    expect(result.success).toBe(true);
    expect(mockClaude.chatJSON).toHaveBeenCalledWith(
      expect.stringContaining('Keep a Changelog'),
      expect.any(String),
    );
  });

  // ===== Label-based Task Type =====

  it('uses label-based task type for system prompt', async () => {
    const task = makeTask({ title: 'Something vague', labels: ['type:architecture.generate'] });
    await callExecuteTask(agent, task);

    expect(mockClaude.chatJSON).toHaveBeenCalledWith(
      expect.stringContaining('architecture documentation'),
      expect.any(String),
    );
  });

  it('uses jsdoc prompt when type:jsdoc.add label', async () => {
    const task = makeTask({ title: 'Add comments', labels: ['type:jsdoc.add'] });
    await callExecuteTask(agent, task);

    expect(mockClaude.chatJSON).toHaveBeenCalledWith(
      expect.stringContaining('JSDoc/TSDoc'),
      expect.any(String),
    );
  });

  // ===== Commit Request =====

  it('creates commit request even without epicId', async () => {
    const task = makeTask({ epicId: null });
    const result = await callExecuteTask(agent, task);

    expect(result.success).toBe(true);
    expect(gitService.createIssue).toHaveBeenCalledWith(
      expect.objectContaining({
        labels: expect.arrayContaining(['agent:git', 'type:commit']),
      }),
    );
  });

  // ===== Unknown Task Type =====

  it('returns error for unknown task type', async () => {
    const task = makeTask({ title: 'do something random', description: 'unrelated work' });
    const result = await callExecuteTask(agent, task);
    expect(result.success).toBe(false);
    expect(result.error?.message).toContain('Unknown docs task type');
  });

  // ===== Analyze Task =====

  it('analyze task returns summary without writing files', async () => {
    const analyzeClaude = createMockClaude({
      files: [],
      summary: 'Documentation coverage: 40%. Missing: API docs, architecture diagram.',
    });
    agent = new DocsAgent(deps, { workDir: '/tmp/test', claudeClient: analyzeClaude });

    const task = makeTask({ title: 'Analyze documentation gaps', description: '' });
    const result = await callExecuteTask(agent, task);

    expect(result.success).toBe(true);
    expect(result.data?.analysis).toContain('Documentation coverage');
    expect(result.artifacts).toEqual([]);
    expect(stateStore.saveArtifact).not.toHaveBeenCalled();
  });

  // ===== Error Handling =====

  it('handles Claude API error gracefully', async () => {
    mockClaude = { chatJSON: vi.fn().mockRejectedValue(new Error('API rate limit exceeded')) };
    agent = new DocsAgent(deps, { workDir: '/tmp/test', claudeClient: mockClaude });

    const result = await callExecuteTask(agent, makeTask());
    expect(result.success).toBe(false);
    expect(result.error?.message).toContain('API rate limit exceeded');
  });

  it('handles empty file generation as error', async () => {
    mockClaude = createMockClaude({ files: [], summary: 'Nothing generated' });
    agent = new DocsAgent(deps, { workDir: '/tmp/test', claudeClient: mockClaude });

    const result = await callExecuteTask(agent, makeTask());
    expect(result.success).toBe(false);
    expect(result.error?.message).toContain('no files');
  });

  it('succeeds even when commit request fails', async () => {
    vi.mocked(gitService.createIssue).mockRejectedValueOnce(new Error('GitHub API down'));

    const result = await callExecuteTask(agent, makeTask());
    expect(result.success).toBe(true);
    expect(result.artifacts.length).toBe(1);
  });

  // ===== Context in Claude prompt =====

  it('includes epicId and existing artifacts in Claude prompt', async () => {
    const task = makeTask({ epicId: 'epic-42', artifacts: ['docs/old-readme.md'] });
    await callExecuteTask(agent, task);

    expect(mockClaude.chatJSON).toHaveBeenCalledWith(
      expect.any(String),
      expect.stringContaining('Epic ID: epic-42'),
    );
    expect(mockClaude.chatJSON).toHaveBeenCalledWith(
      expect.any(String),
      expect.stringContaining('docs/old-readme.md'),
    );
  });

  // ===== Korean Title Detection =====

  it('detects Korean changelog task correctly', async () => {
    mockClaude = createMockClaude(MOCK_CHANGELOG_GENERATED);
    agent = new DocsAgent(deps, { workDir: '/tmp/test', claudeClient: mockClaude });

    const task = makeTask({ title: '변경 이력 업데이트', description: '최근 커밋 반영' });
    const result = await callExecuteTask(agent, task);

    expect(result.success).toBe(true);
    expect(mockClaude.chatJSON).toHaveBeenCalledWith(
      expect.stringContaining('Keep a Changelog'),
      expect.any(String),
    );
  });
});

// ===== Helper =====

function callExecuteTask(agent: DocsAgent, task: Task) {
  return (
    agent as unknown as { executeTask: (t: Task) => Promise<import('@agent/core').TaskResult> }
  ).executeTask(task);
}
