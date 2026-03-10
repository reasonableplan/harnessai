import { describe, it, expect, vi, beforeEach } from 'vitest';
import { BaseAgent } from './base-agent.js';
import type { AgentConfig, IMessageBus, Message, Task, TaskResult } from './types/index.js';

class TestAgent extends BaseAgent {
  public findNextTaskFn = vi.fn<() => Promise<Task | null>>().mockResolvedValue(null);
  public executeTaskFn = vi
    .fn<(task: Task) => Promise<TaskResult>>()
    .mockResolvedValue({ success: true, artifacts: [] });

  protected async findNextTask(): Promise<Task | null> {
    return this.findNextTaskFn();
  }

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

const TEST_CONFIG: AgentConfig = {
  id: 'test-agent',
  domain: 'test',
  level: 2,
  claudeModel: 'claude-sonnet-4-20250514',
  maxTokens: 8192,
  temperature: 0.2,
  tokenBudget: 50_000,
};

const MOCK_TASK: Task = {
  id: 'task-001',
  epicId: 'epic-001',
  title: 'Test task',
  description: 'A test task',
  assignedAgent: 'test-agent',
  status: 'ready',
  githubIssueNumber: 1,
  boardColumn: 'Ready',
  dependencies: [],
  priority: 3,
  complexity: 'medium',
  retryCount: 0,
  artifacts: [],
};

describe('BaseAgent', () => {
  let bus: IMessageBus;
  let agent: TestAgent;

  beforeEach(() => {
    bus = createMockMessageBus();
    agent = new TestAgent(TEST_CONFIG, { messageBus: bus });
  });

  it('초기 상태는 idle이다', () => {
    expect(agent.status).toBe('idle');
  });

  it('config에서 id, domain이 설정된다', () => {
    expect(agent.id).toBe('test-agent');
    expect(agent.domain).toBe('test');
  });

  it('startPolling 후 findNextTask가 호출된다', async () => {
    agent.startPolling(50);

    await new Promise((r) => setTimeout(r, 80));
    agent.stopPolling();

    expect(agent.findNextTaskFn).toHaveBeenCalled();
  });

  it('태스크가 있으면 executeTask가 호출된다', async () => {
    agent.findNextTaskFn.mockResolvedValueOnce(MOCK_TASK);
    agent.startPolling(50);

    await new Promise((r) => setTimeout(r, 80));
    agent.stopPolling();

    expect(agent.executeTaskFn).toHaveBeenCalledWith(MOCK_TASK);
  });

  it('태스크 실행 완료 후 review.request가 발행된다', async () => {
    agent.findNextTaskFn.mockResolvedValueOnce(MOCK_TASK);
    agent.startPolling(50);

    await new Promise((r) => setTimeout(r, 80));
    agent.stopPolling();

    const publishCalls = (bus.publish as ReturnType<typeof vi.fn>).mock.calls;
    const reviewMessages = publishCalls.filter(([msg]: [Message]) => msg.type === 'review.request');
    expect(reviewMessages.length).toBeGreaterThanOrEqual(1);
  });

  it('executeTask 에러 시 status가 error가 된다', async () => {
    agent.findNextTaskFn.mockResolvedValueOnce(MOCK_TASK);
    agent.executeTaskFn.mockRejectedValueOnce(new Error('fail'));

    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    agent.startPolling(50);

    await new Promise((r) => setTimeout(r, 80));
    agent.stopPolling();
    consoleSpy.mockRestore();

    expect(agent.status).toBe('error');
  });

  it('중복 startPolling은 무시된다', () => {
    agent.startPolling(50);
    agent.startPolling(50); // 두 번째 호출은 무시
    agent.stopPolling();
  });

  it('subscribe는 messageBus.subscribe를 호출한다', () => {
    const handler = vi.fn();
    // protected method를 테스트하기 위해 any 캐스팅
    (agent as unknown as { subscribe: (type: string, handler: unknown) => void }).subscribe(
      'board.move',
      handler,
    );
    expect(bus.subscribe).toHaveBeenCalledWith('board.move', handler);
  });
});
