import type { IStateStore, IMessageBus, MessageHandler } from '@agent/core';
import type { BaseAgent } from '@agent/core';
import type {
  DashboardStateStore,
  DashboardMessageBus,
  AgentRegistry,
  DashboardDependencies,
} from '@agent/dashboard-server';

/**
 * 실제 StateStore를 DashboardStateStore 인터페이스로 감싸는 어댑터.
 * Dashboard에 필요한 메서드만 노출한다.
 */
export function createDashboardStateStore(stateStore: IStateStore): DashboardStateStore {
  return {
    getAgent: (id) => stateStore.getAgent(id),
    getTask: (id) => stateStore.getTask(id),
    updateTask: (id, updates) => stateStore.updateTask(id, updates),
    getTasksByColumn: (column) => stateStore.getTasksByColumn(column),
    getAllAgents: () => stateStore.getAllAgents(),
    getAllTasks: () => stateStore.getAllTasks(),
    getAllEpics: () => stateStore.getAllEpics(),
    getRecentMessages: (limit) => stateStore.getRecentMessages(limit),
    getAgentStats: (agentId) => stateStore.getAgentStats(agentId),
    getTaskHistory: (taskId) => stateStore.getTaskHistory(taskId),
    getAgentConfig: (agentId) => stateStore.getAgentConfig(agentId),
    upsertAgentConfig: (agentId, config) => stateStore.upsertAgentConfig(agentId, config),
    getAllHooks: () => stateStore.getAllHooks(),
    toggleHook: (id, enabled) => stateStore.toggleHook(id, enabled),
  };
}

/**
 * 실제 MessageBus를 DashboardMessageBus 인터페이스로 감싸는 어댑터.
 */
export function createDashboardMessageBus(messageBus: IMessageBus): DashboardMessageBus {
  return {
    publish: (message) => messageBus.publish(message),
    subscribeAll: (handler: MessageHandler) => messageBus.subscribeAll(handler),
  };
}

/**
 * BaseAgent 배열을 AgentRegistry 인터페이스로 감싸는 어댑터.
 * Dashboard에서 에이전트를 pause/resume할 수 있게 한다.
 */
export function createAgentRegistry(agents: BaseAgent[]): AgentRegistry {
  const agentMap = new Map(agents.map((a) => [a.id, a]));

  return {
    async pause(agentId: string): Promise<void> {
      const agent = agentMap.get(agentId);
      if (agent) await agent.pause();
    },
    async resume(agentId: string): Promise<void> {
      const agent = agentMap.get(agentId);
      if (agent) await agent.resume();
    },
    async pauseAll(): Promise<void> {
      for (const agent of agents) {
        await agent.pause();
      }
    },
    async resumeAll(): Promise<void> {
      for (const agent of agents) {
        await agent.resume();
      }
    },
  };
}

/**
 * Bootstrap SystemContext에서 DashboardDependencies를 생성한다.
 */
export function createDashboardDeps(
  stateStore: IStateStore,
  messageBus: IMessageBus,
  agents: BaseAgent[],
): DashboardDependencies {
  return {
    stateStore: createDashboardStateStore(stateStore),
    messageBus: createDashboardMessageBus(messageBus),
    agentRegistry: createAgentRegistry(agents),
  };
}
