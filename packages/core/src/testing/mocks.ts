/**
 * Shared test mock utilities for the Agent Orchestration project.
 *
 * Usage:
 *   import { createMockMessageBus, createMockStateStore, ... } from '@agent/testing';
 */
import { vi } from 'vitest';
import type {
  IMessageBus,
  IStateStore,
  IGitService,
  Task,
  Message,
  AgentConfig,
  BoardIssue,
  HookRow,
} from '../types/index.js';

// ===== IMessageBus Mock =====

export function createMockMessageBus(
  overrides?: Partial<IMessageBus>,
): IMessageBus {
  return {
    publish: vi.fn(),
    subscribe: vi.fn(),
    subscribeAll: vi.fn(),
    unsubscribe: vi.fn(),
    unsubscribeAll: vi.fn(),
    ...overrides,
  };
}

// ===== IStateStore Mock =====

const DEFAULT_AGENT_STATS = {
  agentId: '',
  totalTasks: 0,
  completedTasks: 0,
  failedTasks: 0,
  inProgressTasks: 0,
  completionRate: 0,
  avgDurationMs: null,
  totalRetries: 0,
};

export function createMockStateStore(
  overrides?: Partial<IStateStore & { getAllHooks: () => Promise<HookRow[]>; toggleHook: (id: string, enabled: boolean) => Promise<void>; getHook: (id: string) => Promise<HookRow | null> }>,
): IStateStore & { getAllHooks: ReturnType<typeof vi.fn>; toggleHook: ReturnType<typeof vi.fn>; getHook: ReturnType<typeof vi.fn> } {
  return {
    // Agent
    registerAgent: vi.fn(),
    getAgent: vi.fn().mockResolvedValue(null),
    updateAgentStatus: vi.fn(),
    updateHeartbeat: vi.fn(),
    // Task
    createTask: vi.fn(),
    getTask: vi.fn().mockResolvedValue(null),
    updateTask: vi.fn(),
    getTasksByColumn: vi.fn().mockResolvedValue([]),
    getTasksByIds: vi.fn().mockResolvedValue([]),
    getTasksByAgent: vi.fn().mockResolvedValue([]),
    getReadyTasksForAgent: vi.fn().mockResolvedValue([]),
    claimTask: vi.fn().mockResolvedValue(false),
    // Epic
    createEpic: vi.fn(),
    getEpic: vi.fn().mockResolvedValue(null),
    updateEpic: vi.fn(),
    // Message & Artifact
    saveMessage: vi.fn(),
    saveArtifact: vi.fn(),
    // Transaction
    transaction: vi.fn().mockImplementation((fn: (tx: unknown) => Promise<unknown>) => fn({})),
    // Dashboard queries
    getAllAgents: vi.fn().mockResolvedValue([]),
    getAllTasks: vi.fn().mockResolvedValue([]),
    getAllEpics: vi.fn().mockResolvedValue([]),
    getRecentMessages: vi.fn().mockResolvedValue([]),
    // Stats & Config
    getAgentStats: vi.fn().mockResolvedValue({ ...DEFAULT_AGENT_STATS }),
    getTaskHistory: vi.fn().mockResolvedValue([]),
    getAgentConfig: vi.fn().mockResolvedValue(null),
    upsertAgentConfig: vi.fn(),
    // Hooks (used by dashboard-server)
    getAllHooks: vi.fn().mockResolvedValue([]),
    toggleHook: vi.fn(),
    getHook: vi.fn().mockResolvedValue(null),
    ...overrides,
  };
}

// ===== IGitService Mock =====

export interface MockGitServiceOptions {
  /** Starting issue number for auto-increment createIssue. Default: 200 */
  issueCounterStart?: number;
}

export function createMockGitService(
  options?: MockGitServiceOptions,
  overrides?: Partial<IGitService>,
): IGitService {
  let issueCounter = options?.issueCounterStart ?? 200;
  return {
    validateConnection: vi.fn(),
    createIssue: vi.fn().mockImplementation(() => Promise.resolve(++issueCounter)),
    updateIssue: vi.fn(),
    closeIssue: vi.fn(),
    getIssue: vi.fn().mockResolvedValue(null),
    getIssuesByLabel: vi.fn().mockResolvedValue([]),
    getEpicIssues: vi.fn().mockResolvedValue([]),
    getAllProjectItems: vi.fn().mockResolvedValue([]),
    moveIssueToColumn: vi.fn(),
    addComment: vi.fn(),
    createBranch: vi.fn(),
    createPR: vi.fn().mockResolvedValue(42),
    ...overrides,
  };
}

// ===== IClaudeClient Mock =====
// 실제 인터페이스: core/llm/claude-client.ts의 IClaudeClient를 준수

export interface IClaudeClient {
  chat(systemPrompt: string, userMessage: string): Promise<{ content: string; usage: { inputTokens: number; outputTokens: number } }>;
  chatJSON<T = unknown>(systemPrompt: string, userMessage: string): Promise<{ data: T; usage: { inputTokens: number; outputTokens: number } }>;
}

export function createMockClaude(
  response: unknown,
  overrides?: Partial<IClaudeClient>,
): IClaudeClient {
  return {
    chat: vi.fn().mockResolvedValue({
      content: JSON.stringify(response),
      usage: { inputTokens: 200, outputTokens: 150 },
    }),
    chatJSON: vi.fn().mockResolvedValue({
      data: response,
      usage: { inputTokens: 200, outputTokens: 150 },
    }),
    ...overrides,
  };
}

// ===== Task Builder =====

export function createMockTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-1',
    epicId: 'epic-1',
    title: 'Test task',
    description: 'Test task description',
    assignedAgent: null,
    status: 'ready',
    githubIssueNumber: 100,
    boardColumn: 'Ready',
    dependencies: [],
    priority: 3,
    complexity: 'medium',
    retryCount: 0,
    artifacts: [],
    labels: [],
    ...overrides,
  };
}

// ===== Message Builder =====

let messageSeq = 0;

export function createMockMessage(overrides: Partial<Message> = {}): Message {
  messageSeq++;
  return {
    id: `msg-${messageSeq}`,
    type: 'test.event',
    from: 'test',
    to: null,
    payload: {},
    traceId: `trace-${messageSeq}`,
    timestamp: new Date(),
    ...overrides,
  };
}

// ===== BoardIssue Builder =====

export function createMockBoardIssue(overrides: Partial<BoardIssue> = {}): BoardIssue {
  return {
    issueNumber: 1,
    title: 'Test issue',
    body: '',
    labels: [],
    column: 'Backlog',
    dependencies: [],
    assignee: null,
    generatedBy: 'test',
    epicId: null,
    ...overrides,
  };
}

// ===== AgentConfig Builder =====

export function createMockAgentConfig(overrides: Partial<AgentConfig> = {}): AgentConfig {
  return {
    id: 'test-agent',
    domain: 'test',
    level: 2,
    claudeModel: 'claude-sonnet-4-20250514',
    maxTokens: 4096,
    temperature: 0.7,
    tokenBudget: 100000,
    taskTimeoutMs: 300000,
    pollIntervalMs: 10000,
    ...overrides,
  };
}

// ===== AgentDependencies Builder =====

export interface MockAgentDeps {
  messageBus: IMessageBus;
  stateStore: ReturnType<typeof createMockStateStore>;
  gitService: IGitService;
}

export function createMockAgentDeps(overrides?: {
  messageBus?: Partial<IMessageBus>;
  stateStore?: Partial<IStateStore>;
  gitService?: Partial<IGitService>;
}): MockAgentDeps {
  return {
    messageBus: createMockMessageBus(overrides?.messageBus),
    stateStore: createMockStateStore(overrides?.stateStore),
    gitService: createMockGitService(undefined, overrides?.gitService),
  };
}
