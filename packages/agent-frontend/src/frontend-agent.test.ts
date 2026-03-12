import { describe, it, expect, vi, beforeEach } from 'vitest';
import { FrontendAgent } from './frontend-agent.js';
import { detectTaskType } from './task-router.js';
import { parseApiSpec } from './api-spec-parser.js';
import type { IClaudeClient } from './code-generator.js';
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
  let issueCounter = 300;
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
      usage: { inputTokens: 300, outputTokens: 200 },
    }),
    chatJSON: vi.fn().mockResolvedValue({
      data: response,
      usage: { inputTokens: 300, outputTokens: 200 },
    }),
  };
}

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-1',
    epicId: 'epic-1',
    title: 'Create LoginForm component',
    description: 'Login form with email/password validation',
    assignedAgent: 'frontend',
    status: 'in-progress',
    githubIssueNumber: 60,
    boardColumn: 'In Progress',
    dependencies: [],
    priority: 3,
    complexity: 'medium',
    retryCount: 0,
    artifacts: [],
    ...overrides,
  };
}

const MOCK_GENERATED = {
  files: [
    {
      path: 'src/components/LoginForm/LoginForm.tsx',
      content: 'export function LoginForm() {}',
      action: 'create' as const,
      language: 'typescriptreact',
    },
    {
      path: 'src/components/LoginForm/LoginForm.test.tsx',
      content: 'describe("LoginForm", () => {})',
      action: 'create' as const,
      language: 'typescriptreact',
    },
    {
      path: 'src/components/LoginForm/index.ts',
      content: 'export { LoginForm } from "./LoginForm"',
      action: 'create' as const,
      language: 'typescript',
    },
  ],
  summary: 'Created LoginForm component with tests and index re-export',
};

// ===== Task Type Detection (Unit) =====

describe('detectTaskType', () => {
  it('returns label-based type when type:* label exists', () => {
    const task = makeTask({ labels: ['type:page.create'] });
    expect(detectTaskType(task)).toBe('page.create');
  });

  it('ignores invalid label values', () => {
    const task = makeTask({ title: 'Create LoginForm component', labels: ['type:invalid'] });
    expect(detectTaskType(task)).toBe('component.create');
  });

  it('detects analyze from title', () => {
    expect(detectTaskType(makeTask({ title: 'Analyze project structure', description: '' }))).toBe(
      'analyze',
    );
  });

  it('detects test.create from title', () => {
    expect(detectTaskType(makeTask({ title: 'Create tests for Button', description: '' }))).toBe(
      'test.create',
    );
  });

  it('detects hook.create from useXxx pattern', () => {
    expect(detectTaskType(makeTask({ title: 'Create useAuth hook', description: '' }))).toBe(
      'hook.create',
    );
  });

  it('detects hook.create from Korean keyword', () => {
    expect(detectTaskType(makeTask({ title: '인증 훅 생성', description: '' }))).toBe(
      'hook.create',
    );
  });

  it('does not false-positive hook from "user" or "used"', () => {
    const task = makeTask({ title: 'Create user profile component', description: '' });
    expect(detectTaskType(task)).toBe('component.create');
  });

  it('detects store.create from zustand keyword', () => {
    expect(detectTaskType(makeTask({ title: 'Create auth zustand store', description: '' }))).toBe(
      'store.create',
    );
  });

  it('does not false-positive store from "restore"', () => {
    const task = makeTask({ title: 'Restore settings page', description: '' });
    expect(detectTaskType(task)).toBe('page.create');
  });

  it('detects page.create from page keyword', () => {
    expect(detectTaskType(makeTask({ title: 'Create login page', description: '' }))).toBe(
      'page.create',
    );
  });

  it('detects page.modify from page + modify keywords', () => {
    expect(detectTaskType(makeTask({ title: 'Modify login page layout', description: '' }))).toBe(
      'page.modify',
    );
  });

  it('detects component.create from component keyword', () => {
    expect(detectTaskType(makeTask({ title: 'Create LoginForm component', description: '' }))).toBe(
      'component.create',
    );
  });

  it('detects component.modify from Korean keyword', () => {
    expect(detectTaskType(makeTask({ title: '로그인 컴포넌트 수정', description: '' }))).toBe(
      'component.modify',
    );
  });

  it('detects style.generate from tailwind keyword', () => {
    expect(
      detectTaskType(
        makeTask({ title: 'Generate tailwind styles for dashboard', description: '' }),
      ),
    ).toBe('style.generate');
  });

  it('style does not override more specific types', () => {
    // description에 tailwind가 있어도 title의 component가 우선
    const task = makeTask({
      title: 'Create LoginForm component',
      description: 'Use tailwind for styling',
    });
    expect(detectTaskType(task)).toBe('component.create');
  });

  it('detects Korean page correctly', () => {
    expect(detectTaskType(makeTask({ title: '로그인 페이지 생성', description: '' }))).toBe(
      'page.create',
    );
  });

  it('returns unknown for unrecognizable task', () => {
    expect(detectTaskType(makeTask({ title: 'do something', description: 'unrelated' }))).toBe(
      'unknown',
    );
  });
});

// ===== FrontendAgent Integration =====

describe('FrontendAgent', () => {
  let deps: AgentDependencies;
  let messageBus: IMessageBus;
  let stateStore: IStateStore;
  let gitService: IGitService;
  let mockClaude: IClaudeClient;
  let agent: FrontendAgent;

  beforeEach(() => {
    messageBus = createMockMessageBus();
    stateStore = createMockStateStore();
    gitService = createMockGitService();
    deps = { messageBus, stateStore, gitService };
    mockClaude = createMockClaude(MOCK_GENERATED);
    agent = new FrontendAgent(deps, { workDir: '/tmp/test-workspace', claudeClient: mockClaude });
  });

  // ===== Basic Structure =====

  it('has correct id, domain, and level', () => {
    expect(agent.id).toBe('frontend');
    expect(agent.domain).toBe('frontend');
    expect(agent.config.level).toBe(2);
  });

  // ===== Code Generation Flow =====

  it('generates code, writes files, saves artifacts, and creates commit request', async () => {
    const task = makeTask();
    const result = await callExecuteTask(agent, task);

    // Success
    expect(result.success).toBe(true);
    expect(result.artifacts).toEqual([
      'src/components/LoginForm/LoginForm.tsx',
      'src/components/LoginForm/LoginForm.test.tsx',
      'src/components/LoginForm/index.ts',
    ]);
    expect(result.data?.generatedFiles).toEqual(result.artifacts);

    // Claude called with frontend-specific system prompt
    expect(mockClaude.chatJSON).toHaveBeenCalledWith(
      expect.stringContaining('frontend code generator'),
      expect.stringContaining('Create LoginForm component'),
    );

    // Artifacts saved to DB
    expect(stateStore.saveArtifact).toHaveBeenCalledTimes(3);
    expect(stateStore.saveArtifact).toHaveBeenCalledWith(
      expect.objectContaining({
        taskId: 'task-1',
        filePath: 'src/components/LoginForm/LoginForm.tsx',
        createdBy: 'frontend',
      }),
    );

    // Git commit follow-up issue created
    expect(gitService.createIssue).toHaveBeenCalledWith(
      expect.objectContaining({
        title: expect.stringContaining('[GIT] Commit:'),
        labels: expect.arrayContaining(['agent:git', 'type:commit', 'epic:epic-1']),
        dependencies: [60],
      }),
    );
  });

  it('uses label-based task type for system prompt', async () => {
    const task = makeTask({ title: 'Something vague', labels: ['type:hook.create'] });
    await callExecuteTask(agent, task);

    expect(mockClaude.chatJSON).toHaveBeenCalledWith(
      expect.stringContaining('custom React hook'),
      expect.any(String),
    );
  });

  it('creates commit request even without epicId', async () => {
    const task = makeTask({ epicId: null });
    const result = await callExecuteTask(agent, task);

    expect(result.success).toBe(true);
    expect(gitService.createIssue).toHaveBeenCalledWith(
      expect.objectContaining({
        title: expect.stringContaining('[GIT] Commit:'),
        labels: expect.arrayContaining(['agent:git', 'type:commit']),
      }),
    );
  });

  it('returns error for unknown task type', async () => {
    const task = makeTask({ title: 'do something random', description: 'unrelated work' });
    const result = await callExecuteTask(agent, task);
    expect(result.success).toBe(false);
    expect(result.error?.message).toContain('Unknown frontend task type');
  });

  // ===== Analyze Task =====

  it('analyze task returns summary without writing files', async () => {
    const analyzeClaude = createMockClaude({
      files: [],
      summary: 'Found 15 components, 5 pages, 3 unused exports',
    });
    agent = new FrontendAgent(deps, { workDir: '/tmp/test', claudeClient: analyzeClaude });

    const task = makeTask({ title: 'Analyze component structure', description: '' });
    const result = await callExecuteTask(agent, task);

    expect(result.success).toBe(true);
    expect(result.data?.analysis).toContain('15 components');
    expect(result.artifacts).toEqual([]);
    expect(stateStore.saveArtifact).not.toHaveBeenCalled();
  });

  // ===== Error Handling =====

  it('handles Claude API error gracefully', async () => {
    mockClaude = { chatJSON: vi.fn().mockRejectedValue(new Error('API rate limit exceeded')) };
    agent = new FrontendAgent(deps, { workDir: '/tmp/test', claudeClient: mockClaude });

    const task = makeTask();
    const result = await callExecuteTask(agent, task);

    expect(result.success).toBe(false);
    expect(result.error?.message).toContain('API rate limit exceeded');
  });

  it('handles empty file generation as error', async () => {
    mockClaude = createMockClaude({ files: [], summary: 'Nothing generated' });
    agent = new FrontendAgent(deps, { workDir: '/tmp/test', claudeClient: mockClaude });

    const task = makeTask();
    const result = await callExecuteTask(agent, task);

    expect(result.success).toBe(false);
    expect(result.error?.message).toContain('no files');
  });

  it('succeeds even when commit request fails', async () => {
    vi.mocked(gitService.createIssue).mockRejectedValueOnce(new Error('GitHub API down'));

    const task = makeTask();
    const result = await callExecuteTask(agent, task);

    // Task itself succeeds — commit request failure is non-fatal
    expect(result.success).toBe(true);
    expect(result.artifacts.length).toBe(3);
  });

  // ===== Context in Claude prompt =====

  it('includes epicId and existing artifacts in Claude prompt', async () => {
    const task = makeTask({ epicId: 'epic-42', artifacts: ['src/components/Button.tsx'] });
    await callExecuteTask(agent, task);

    expect(mockClaude.chatJSON).toHaveBeenCalledWith(
      expect.any(String),
      expect.stringContaining('Epic ID: epic-42'),
    );
    expect(mockClaude.chatJSON).toHaveBeenCalledWith(
      expect.any(String),
      expect.stringContaining('src/components/Button.tsx'),
    );
  });
});

// ===== API Spec Parser =====

describe('parseApiSpec', () => {
  it('extracts API spec from issue body', () => {
    const body = `Some intro text

## API 스펙
\`\`\`json
{
  "method": "POST",
  "path": "/api/auth/login",
  "request": { "body": { "type": "{ email: string; password: string; }" } },
  "response": { "success": { "status": 200, "body": { "type": "{ token: string; }" } }, "errors": [] },
  "auth": "none",
  "description": "Login endpoint"
}
\`\`\`

More text after`;

    const spec = parseApiSpec(body);
    expect(spec).not.toBeNull();
    expect(spec!.method).toBe('POST');
    expect(spec!.path).toBe('/api/auth/login');
    expect(spec!.auth).toBe('none');
  });

  it('returns null for invalid body', () => {
    expect(parseApiSpec('no api spec here')).toBeNull();
  });

  it('returns null for malformed JSON', () => {
    const body = '## API 스펙\n```json\n{invalid json}\n```';
    expect(parseApiSpec(body)).toBeNull();
  });
});

// ===== Helper =====

function callExecuteTask(agent: FrontendAgent, task: Task) {
  return (
    agent as never as { executeTask: (t: Task) => Promise<import('@agent/core').TaskResult> }
  ).executeTask(task);
}
