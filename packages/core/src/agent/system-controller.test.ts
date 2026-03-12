import { describe, it, expect, vi, beforeEach } from 'vitest';
import { SystemController } from './system-controller.js';
import type { BaseAgent } from './base-agent.js';
import type { IStateStore, UserInput } from '../types/index.js';

function createMockAgent(id: string, domain: string): BaseAgent {
  return {
    id,
    domain,
    status: 'idle',
    config: { id, domain, level: 2, claudeModel: '', maxTokens: 0, temperature: 0, tokenBudget: 0 },
    startPolling: vi.fn(),
    stopPolling: vi.fn(),
    pause: vi.fn(),
    resume: vi.fn(),
  } as unknown as BaseAgent;
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
    getAllAgents: vi.fn().mockResolvedValue([]),
    getAllTasks: vi.fn().mockResolvedValue([]),
    getAllEpics: vi.fn().mockResolvedValue([]),
    getRecentMessages: vi.fn().mockResolvedValue([]),
    transaction: vi.fn().mockImplementation((fn) => fn({})),
  };
}

function makeInput(content: string): UserInput {
  return { source: 'cli', content, timestamp: new Date() };
}

describe('SystemController', () => {
  let agents: BaseAgent[];
  let stateStore: IStateStore;
  let controller: SystemController;

  beforeEach(() => {
    agents = [createMockAgent('git', 'git'), createMockAgent('backend', 'backend')];
    stateStore = createMockStateStore();
    controller = new SystemController(agents, stateStore);
  });

  it('isSystemCommand returns true for known commands', () => {
    expect(controller.isSystemCommand('pause')).toBe(true);
    expect(controller.isSystemCommand('resume')).toBe(true);
    expect(controller.isSystemCommand('status')).toBe(true);
    expect(controller.isSystemCommand('help')).toBe(true);
  });

  it('isSystemCommand returns false for natural language', () => {
    expect(controller.isSystemCommand('로그인 기능 만들어줘')).toBe(false);
    expect(controller.isSystemCommand('create login api')).toBe(false);
  });

  it('pause stops all agents and updates DB status to paused', async () => {
    const result = await controller.handleSystemCommand(makeInput('pause'));
    expect(result).toContain('2 agents paused');
    for (const agent of agents) {
      expect(agent.pause).toHaveBeenCalled();
    }
    expect(stateStore.updateAgentStatus).toHaveBeenCalledWith('git', 'paused');
    expect(stateStore.updateAgentStatus).toHaveBeenCalledWith('backend', 'paused');
  });

  it('resume starts all agents and updates DB status to idle', async () => {
    const result = await controller.handleSystemCommand(makeInput('resume'));
    expect(result).toContain('2 agents resumed');
    for (const agent of agents) {
      expect(agent.resume).toHaveBeenCalled();
    }
    expect(stateStore.updateAgentStatus).toHaveBeenCalledWith('git', 'idle');
    expect(stateStore.updateAgentStatus).toHaveBeenCalledWith('backend', 'idle');
  });

  it('status shows agent info', async () => {
    const result = await controller.handleSystemCommand(makeInput('status'));
    expect(result).toContain('git');
    expect(result).toContain('backend');
    expect(result).toContain('idle');
  });

  it('help shows command list', async () => {
    const result = await controller.handleSystemCommand(makeInput('help'));
    expect(result).toContain('pause');
    expect(result).toContain('resume');
    expect(result).toContain('Director');
  });

  it('commands are case-insensitive', async () => {
    expect(controller.isSystemCommand('PAUSE')).toBe(true);
    expect(controller.isSystemCommand('Status')).toBe(true);
    expect(controller.isSystemCommand('HELP')).toBe(true);

    const result = await controller.handleSystemCommand(makeInput('PAUSE'));
    expect(result).toContain('2 agents paused');
  });

  it('unknown command returns error message', async () => {
    const result = await controller.handleSystemCommand(makeInput('foobar'));
    expect(result).toContain('Unknown command');
  });
});
