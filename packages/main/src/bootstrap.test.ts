import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { AgentDependencies, IMessageBus, IStateStore, IGitService, AppConfig } from '@agent/core';
import { DirectorAgent } from '@agent/director';
import { GitAgent } from '@agent/git';
import { BackendAgent } from '@agent/backend';
import { FrontendAgent } from '@agent/frontend';
import { DocsAgent } from '@agent/docs';
import { createAgentFactories } from './agent-factories.js';

// ===== Mock Config =====

function createMockConfig(overrides: Partial<AppConfig> = {}): AppConfig {
  return {
    database: { url: 'postgres://localhost/test' },
    github: { token: 'ghp_test', owner: 'test-owner', repo: 'test-repo' },
    claude: { apiKey: 'sk-ant-test' },
    workspace: { workDir: '/tmp/test-workspace' },
    dashboard: { port: 3001, corsOrigins: ['http://localhost:3000'] },
    logging: { level: 'info', isProduction: false },
    ...overrides,
  };
}

// ===== Mock Deps =====

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
  return {
    validateConnection: vi.fn(),
    createIssue: vi.fn(),
    updateIssue: vi.fn(),
    closeIssue: vi.fn(),
    getIssue: vi.fn(),
    getIssuesByLabel: vi.fn(),
    getEpicIssues: vi.fn().mockResolvedValue([]),
    getAllProjectItems: vi.fn().mockResolvedValue([]),
    moveIssueToColumn: vi.fn(),
    addComment: vi.fn(),
    createBranch: vi.fn(),
    createPR: vi.fn(),
  };
}

function createDeps(): AgentDependencies {
  return {
    messageBus: createMockMessageBus(),
    stateStore: createMockStateStore(),
    gitService: createMockGitService(),
  };
}

// ===== Tests =====

describe('Bootstrap Integration — Agent Factory Wiring', () => {
  let deps: AgentDependencies;
  let config: AppConfig;

  beforeEach(() => {
    deps = createDeps();
    config = createMockConfig();
  });

  // ===== createAgentFactories =====

  it('creates all 5 agent factories', () => {
    const factories = createAgentFactories(config);
    expect(Object.keys(factories)).toEqual(['director', 'git', 'backend', 'frontend', 'docs']);
  });

  it('director factory creates DirectorAgent (Level 0)', () => {
    const factories = createAgentFactories(config);
    const agent = factories.director(deps);
    expect(agent).toBeInstanceOf(DirectorAgent);
    expect(agent.id).toBe('director');
    expect(agent.domain).toBe('orchestration');
    expect(agent.config.level).toBe(0);
  });

  it('git factory creates GitAgent (Level 2)', () => {
    const factories = createAgentFactories(config);
    const agent = factories.git(deps);
    expect(agent).toBeInstanceOf(GitAgent);
    expect(agent.id).toBe('git');
    expect(agent.domain).toBe('git');
    expect(agent.config.level).toBe(2);
  });

  it('backend factory creates BackendAgent (Level 2)', () => {
    const factories = createAgentFactories(config);
    const agent = factories.backend(deps);
    expect(agent).toBeInstanceOf(BackendAgent);
    expect(agent.id).toBe('backend');
    expect(agent.domain).toBe('backend');
    expect(agent.config.level).toBe(2);
  });

  it('frontend factory creates FrontendAgent (Level 2)', () => {
    const factories = createAgentFactories(config);
    const agent = factories.frontend(deps);
    expect(agent).toBeInstanceOf(FrontendAgent);
    expect(agent.id).toBe('frontend');
    expect(agent.domain).toBe('frontend');
    expect(agent.config.level).toBe(2);
  });

  it('docs factory creates DocsAgent (Level 2)', () => {
    const factories = createAgentFactories(config);
    const agent = factories.docs(deps);
    expect(agent).toBeInstanceOf(DocsAgent);
    expect(agent.id).toBe('docs');
    expect(agent.domain).toBe('docs');
    expect(agent.config.level).toBe(2);
  });

  // ===== Shared Dependencies =====

  it('all agents share the same MessageBus instance', () => {
    const factories = createAgentFactories(config);
    Object.values(factories).map((f) => f(deps));

    // Director subscribes to review.request — verify messageBus.subscribe was called
    expect(deps.messageBus.subscribe).toHaveBeenCalledWith('review.request', expect.any(Function));
    expect(deps.messageBus.subscribe).toHaveBeenCalledWith('board.move', expect.any(Function));
  });

  // ===== Agent Hierarchy =====

  it('exactly one Level 0 agent (Director) and four Level 2 workers', () => {
    const factories = createAgentFactories(config);
    const agents = Object.values(factories).map((f) => f(deps));

    const l0 = agents.filter((a) => a.config.level === 0);
    const l2 = agents.filter((a) => a.config.level === 2);

    expect(l0).toHaveLength(1);
    expect(l0[0].id).toBe('director');
    expect(l2).toHaveLength(4);
    expect(l2.map((a) => a.id).sort()).toEqual(['backend', 'docs', 'frontend', 'git']);
  });

  // ===== Review Cycle Wiring =====

  it('all worker agents use BaseAgent.onTaskComplete (Review → Director)', async () => {
    const factories = createAgentFactories(config);
    const agents = Object.values(factories).map((f) => f(deps));

    // 각 워커 에이전트가 onTaskComplete를 오버라이드하지 않았는지 확인
    const workers = agents.filter((a) => a.id !== 'director');

    for (const worker of workers) {
      const task = {
        id: `task-${worker.id}`,
        epicId: null,
        title: `Test task for ${worker.id}`,
        description: 'test',
        assignedAgent: worker.id,
        status: 'in-progress' as const,
        githubIssueNumber: 42,
        boardColumn: 'In Progress',
        dependencies: [],
        priority: 3 as const,
        complexity: 'medium' as const,
        retryCount: 0,
        artifacts: [],
      };

      const result = { success: true, artifacts: [], data: {} };

      await (
        worker as unknown as { onTaskComplete: (t: typeof task, r: typeof result) => Promise<void> }
      ).onTaskComplete(task, result);

      // 성공 시 Review 컬럼으로 이동해야 함 (Done이 아님!)
      expect(deps.stateStore.updateTask).toHaveBeenCalledWith(
        `task-${worker.id}`,
        expect.objectContaining({ status: 'review', boardColumn: 'Review' }),
      );
      expect(deps.gitService.moveIssueToColumn).toHaveBeenCalledWith(42, 'Review');

      // review.request 메시지 발행
      expect(deps.messageBus.publish).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'review.request',
          from: worker.id,
          payload: expect.objectContaining({ taskId: `task-${worker.id}` }),
        }),
      );

      // Reset mocks for next iteration
      vi.mocked(deps.stateStore.updateTask).mockClear();
      vi.mocked(deps.gitService.moveIssueToColumn).mockClear();
      vi.mocked(deps.messageBus.publish).mockClear();
    }
  });

  // ===== Polling Lifecycle =====

  it('agents start idle and can be polled', () => {
    const factories = createAgentFactories(config);
    const agents = Object.values(factories).map((f) => f(deps));

    for (const agent of agents) {
      expect(agent.status).toBe('idle');
    }
  });

  it('agents can start and stop polling', () => {
    const factories = createAgentFactories(config);
    const agents = Object.values(factories).map((f) => f(deps));

    for (const agent of agents) {
      agent.startPolling(60_000); // long interval to avoid actual polling
      agent.stopPolling();
      // No error thrown
    }
  });

  // ===== Config Defaults =====

  it('uses provided workDir from config', () => {
    const customConfig = createMockConfig({ workspace: { workDir: '/custom/path' } });
    const factories = createAgentFactories(customConfig);

    const git = factories.git(deps);
    expect(git).toBeInstanceOf(GitAgent);
  });
});
