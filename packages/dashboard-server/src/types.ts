import type { AgentRow, TaskRow, EpicRow, Message } from '@agent/core';

// ===== Client → Server =====

export type DashboardCommand =
  | { type: 'user-input'; payload: { text: string } }
  | { type: 'agent-pause'; payload: { agentId: string } }
  | { type: 'agent-resume'; payload: { agentId: string } }
  | { type: 'task-move'; payload: { taskId: string; toColumn: string } }
  | { type: 'task-retry'; payload: { taskId: string } }
  | { type: 'system-pause'; payload: Record<string, never> }
  | { type: 'system-resume'; payload: Record<string, never> };

// ===== Server → Client =====

export type DashboardEvent =
  | { type: 'initial-state'; payload: { agents: AgentRow[]; tasks: TaskRow[]; epics: EpicRow[] } }
  | { type: 'agent-state'; payload: { agentId: string; status: string; task?: string } }
  | { type: 'board-update'; payload: { taskId: string; column: string; task: TaskRow } }
  | { type: 'bubble-update'; payload: { agentId: string; content: string | null; type?: string } }
  | { type: 'epic-update'; payload: { epicId: string; title: string; progress: number } }
  | { type: 'toast'; payload: { type: 'success' | 'error' | 'info'; title: string; message: string } }
  | { type: 'message-log'; payload: { message: Message } };

// ===== Server Dependencies =====

export interface DashboardDependencies {
  stateStore: DashboardStateStore;
  messageBus: DashboardMessageBus;
  /** Optional: agent registry for pause/resume commands */
  agentRegistry?: AgentRegistry;
}

/**
 * Subset of IStateStore that the dashboard needs.
 * In production, the real StateStore is injected.
 * In standalone dev mode, an in-memory mock is used.
 */
export interface DashboardStateStore {
  getAgent(id: string): Promise<AgentRow | null>;
  getTask(id: string): Promise<TaskRow | null>;
  updateTask(id: string, updates: Partial<TaskRow>): Promise<void>;
  getTasksByColumn(column: string): Promise<TaskRow[]>;
  // Extended methods the dashboard adds
  getAllAgents(): Promise<AgentRow[]>;
  getAllTasks(): Promise<TaskRow[]>;
  getAllEpics(): Promise<EpicRow[]>;
  getRecentMessages(limit: number): Promise<Message[]>;
}

/**
 * Subset of IMessageBus the dashboard needs.
 */
export interface DashboardMessageBus {
  publish(message: Message): Promise<void>;
  subscribeAll(handler: (message: Message) => void | Promise<void>): void;
}

/**
 * Agent registry for pause/resume commands.
 */
export interface AgentRegistry {
  pause(agentId: string): Promise<void>;
  resume(agentId: string): Promise<void>;
  pauseAll(): Promise<void>;
  resumeAll(): Promise<void>;
}
