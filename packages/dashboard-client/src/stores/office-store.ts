import { create } from 'zustand';

export interface AgentState {
  id: string;
  status: string;
  currentTask: string | null;
  bubble: { content: string; type: 'task' | 'thinking' | 'info' | 'error' } | null;
  domain: string;
}

export interface TaskState {
  id: string;
  title: string;
  status: string;
  boardColumn: string;
  assignedAgent: string | null;
  epicId: string | null;
}

export interface EpicState {
  id: string;
  title: string;
  progress: number;
}

export interface MessageState {
  id: string;
  type: string;
  from: string;
  content: string;
  timestamp: string;
}

export interface ToastState {
  id: string;
  type: 'success' | 'error' | 'info' | 'warning';
  title: string;
  message: string;
}

export interface TokenUsageState {
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  callCount: number;
}

export interface OfficeStore {
  agents: Record<string, AgentState>;
  tasks: Record<string, TaskState>;
  epics: Record<string, EpicState>;
  messages: MessageState[];
  toasts: ToastState[];
  selectedAgent: string | null;
  boardExpanded: boolean;
  isPaused: boolean;
  elapsedTime: number;
  tokenUsage: Record<string, TokenUsageState>;
  tokenBudget: number;

  setInitialState(data: {
    agents?: Record<string, AgentState>;
    tasks?: Record<string, TaskState>;
    epics?: Record<string, EpicState>;
    tokenUsage?: Record<string, TokenUsageState>;
    tokenBudget?: number;
  }): void;
  updateAgent(id: string, updates: Partial<AgentState>): void;
  updateTask(id: string, updates: Partial<TaskState>): void;
  updateEpic(id: string, updates: Partial<EpicState>): void;
  addMessage(msg: MessageState): void;
  addToast(toast: ToastState): void;
  removeToast(id: string): void;
  selectAgent(id: string | null): void;
  toggleBoard(): void;
  togglePause(): void;
  incrementTime(): void;
  updateTokenUsage(agentId: string, input: number, output: number): void;
  setTokenBudget(budget: number): void;
}

const DEFAULT_AGENTS: Record<string, AgentState> = {
  director: {
    id: 'director',
    status: 'idle',
    currentTask: null,
    bubble: null,
    domain: 'director',
  },
  git: {
    id: 'git',
    status: 'idle',
    currentTask: null,
    bubble: null,
    domain: 'git',
  },
  frontend: {
    id: 'frontend',
    status: 'idle',
    currentTask: null,
    bubble: null,
    domain: 'frontend',
  },
  backend: {
    id: 'backend',
    status: 'idle',
    currentTask: null,
    bubble: null,
    domain: 'backend',
  },
  docs: {
    id: 'docs',
    status: 'idle',
    currentTask: null,
    bubble: null,
    domain: 'docs',
  },
};

const DEFAULT_TOKEN_USAGE: Record<string, TokenUsageState> = {
  director: { inputTokens: 0, outputTokens: 0, totalTokens: 0, callCount: 0 },
  git: { inputTokens: 0, outputTokens: 0, totalTokens: 0, callCount: 0 },
  frontend: { inputTokens: 0, outputTokens: 0, totalTokens: 0, callCount: 0 },
  backend: { inputTokens: 0, outputTokens: 0, totalTokens: 0, callCount: 0 },
  docs: { inputTokens: 0, outputTokens: 0, totalTokens: 0, callCount: 0 },
};

export const useOfficeStore = create<OfficeStore>((set) => ({
  agents: { ...DEFAULT_AGENTS },
  tasks: {},
  epics: {},
  messages: [],
  toasts: [],
  selectedAgent: null,
  boardExpanded: false,
  isPaused: false,
  elapsedTime: 0,
  tokenUsage: { ...DEFAULT_TOKEN_USAGE },
  tokenBudget: 10_000_000,

  setInitialState: (data) =>
    set((state) => ({
      agents: data.agents ?? state.agents,
      tasks: data.tasks ?? state.tasks,
      epics: data.epics ?? state.epics,
      tokenUsage: data.tokenUsage ?? state.tokenUsage,
      tokenBudget: data.tokenBudget ?? state.tokenBudget,
    })),

  updateAgent: (id, updates) =>
    set((state) => ({
      agents: {
        ...state.agents,
        [id]: { ...state.agents[id], ...updates },
      },
    })),

  updateTask: (id, updates) =>
    set((state) => ({
      tasks: {
        ...state.tasks,
        [id]: state.tasks[id]
          ? { ...state.tasks[id], ...updates }
          : { id, title: '', status: '', boardColumn: '', assignedAgent: null, epicId: null, ...updates },
      },
    })),

  updateEpic: (id, updates) =>
    set((state) => ({
      epics: {
        ...state.epics,
        [id]: state.epics[id]
          ? { ...state.epics[id], ...updates }
          : { id, title: '', progress: 0, ...updates },
      },
    })),

  addMessage: (msg) =>
    set((state) => ({
      messages: [msg, ...state.messages].slice(0, 200),
    })),

  addToast: (toast) =>
    set((state) => ({
      toasts: [...state.toasts, toast].slice(-5),
    })),

  removeToast: (id) =>
    set((state) => ({
      toasts: state.toasts.filter((t) => t.id !== id),
    })),

  selectAgent: (id) => set({ selectedAgent: id }),

  toggleBoard: () => set((state) => ({ boardExpanded: !state.boardExpanded })),

  togglePause: () => set((state) => ({ isPaused: !state.isPaused })),

  incrementTime: () => set((state) => ({ elapsedTime: state.elapsedTime + 1 })),

  updateTokenUsage: (agentId, input, output) =>
    set((state) => {
      const prev = state.tokenUsage[agentId] ?? { inputTokens: 0, outputTokens: 0, totalTokens: 0, callCount: 0 };
      return {
        tokenUsage: {
          ...state.tokenUsage,
          [agentId]: {
            inputTokens: prev.inputTokens + input,
            outputTokens: prev.outputTokens + output,
            totalTokens: prev.totalTokens + input + output,
            callCount: prev.callCount + 1,
          },
        },
      };
    }),

  setTokenBudget: (budget) => set({ tokenBudget: budget }),
}));
