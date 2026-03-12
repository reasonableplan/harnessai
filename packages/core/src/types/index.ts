import type { InferSelectModel, InferInsertModel } from 'drizzle-orm';
import type {
  agents as agentsTable,
  epics as epicsTable,
  tasks as tasksTable,
  messages as messagesTable,
  artifacts as artifactsTable,
} from '../db/schema.js';

// ===== DB Row Types (Drizzle $inferSelect / $inferInsert) =====
export type AgentRow = InferSelectModel<typeof agentsTable>;
export type AgentInsert = InferInsertModel<typeof agentsTable>;
export type EpicRow = InferSelectModel<typeof epicsTable>;
export type EpicInsert = InferInsertModel<typeof epicsTable>;
export type TaskRow = InferSelectModel<typeof tasksTable>;
export type TaskInsert = InferInsertModel<typeof tasksTable>;
export type MessageRow = InferSelectModel<typeof messagesTable>;
export type MessageInsert = InferInsertModel<typeof messagesTable>;
export type ArtifactRow = InferSelectModel<typeof artifactsTable>;
export type ArtifactInsert = InferInsertModel<typeof artifactsTable>;

// ===== Domain Types =====

export type TaskStatus = 'backlog' | 'ready' | 'in-progress' | 'review' | 'failed' | 'done';
export type TaskPriority = 1 | 2 | 3 | 4 | 5;
export type TaskComplexity = 'low' | 'medium' | 'high';

export interface Task {
  id: string;
  epicId: string | null;
  title: string;
  description: string;
  assignedAgent: string | null;
  status: TaskStatus;
  githubIssueNumber: number | null;
  boardColumn: string;
  dependencies: string[];
  priority: TaskPriority;
  complexity: TaskComplexity;
  retryCount: number;
  artifacts: string[];
  labels?: string[];
  reviewNote?: string | null;
}

// ===== TaskResult =====
export interface TaskResult {
  success: boolean;
  data?: {
    generatedFiles?: string[];
    [key: string]: unknown;
  };
  error?: {
    message: string;
    code?: string;
    stack?: string;
  };
  artifacts: string[];
}

// ===== Message =====
export interface Message<T = unknown> {
  id: string;
  type: string;
  from: string;
  to: string | null;
  payload: T;
  traceId: string;
  timestamp: Date;
}

/** Well-known message types. Agents can define additional types as needed. */
export const MESSAGE_TYPES = {
  BOARD_MOVE: 'board.move',
  BOARD_REMOVE: 'board.remove',
  REVIEW_REQUEST: 'review.request',
  REVIEW_FEEDBACK: 'review.feedback',
  EPIC_PROGRESS: 'epic.progress',
  AGENT_STATUS: 'agent.status',
  TOKEN_USAGE: 'token.usage',
  USER_INPUT: 'user.input',
  SYSTEM_COMMAND: 'system.command',
} as const;

export type MessageType = (typeof MESSAGE_TYPES)[keyof typeof MESSAGE_TYPES];

// ===== BoardIssue =====
export interface BoardIssue {
  issueNumber: number;
  title: string;
  body: string;
  labels: string[];
  column: string;
  dependencies: number[];
  assignee: string | null;
  generatedBy: string;
  epicId: string | null;
}

// ===== FollowUp =====
export type FollowUpType = 'commit' | 'api-hook' | 'test' | 'docs' | 'review';

export interface FollowUp {
  title: string;
  targetAgent: string;
  type: FollowUpType;
  description: string;
  dependencies: number[];
  additionalContext?: string;
}

// ===== GeneratedCode =====
export type FileAction = 'create' | 'update' | 'delete';

export interface GeneratedFile {
  path: string;
  content: string;
  action: FileAction;
  language: string;
}

export interface GeneratedCode {
  files: GeneratedFile[];
  summary: string;
}

// ===== IssueSpec =====
export interface IssueSpec {
  title: string;
  body: string;
  labels: string[];
  milestone?: number;
  dependencies: number[];
}

// ===== AgentConfig =====
export type AgentLevel = 0 | 1 | 2;

export interface AgentConfig {
  id: string;
  domain: string;
  level: AgentLevel;
  claudeModel: string;
  maxTokens: number;
  temperature: number;
  tokenBudget: number;
  taskTimeoutMs?: number;
}

// ===== ApiSpec =====
export interface TypeDefinition {
  type: string;
  example?: unknown;
}

export interface ApiSpec {
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  path: string;
  request: {
    headers?: Record<string, string>;
    params?: Record<string, string>;
    query?: Record<string, string>;
    body?: TypeDefinition;
  };
  response: {
    success: {
      status: number;
      body: TypeDefinition;
    };
    errors: Array<{
      status: number;
      body: TypeDefinition;
      description: string;
    }>;
  };
  auth: 'none' | 'bearer' | 'api-key';
  description: string;
}

// ===== Board Columns =====
export const BOARD_COLUMNS = [
  'Backlog',
  'Ready',
  'In Progress',
  'Review',
  'Failed',
  'Done',
] as const;
export type BoardColumn = (typeof BOARD_COLUMNS)[number];

// ===== IStateStore =====
export interface IStateStore {
  // Agent
  registerAgent(agent: AgentInsert): Promise<void>;
  getAgent(id: string): Promise<AgentRow | null>;
  updateAgentStatus(id: string, status: string): Promise<void>;
  updateHeartbeat(id: string): Promise<void>;
  // Task
  createTask(task: TaskInsert): Promise<void>;
  getTask(id: string): Promise<TaskRow | null>;
  updateTask(id: string, updates: Partial<TaskRow>): Promise<void>;
  getTasksByColumn(column: string): Promise<TaskRow[]>;
  getTasksByAgent(agentId: string): Promise<TaskRow[]>;
  getReadyTasksForAgent(agentId: string): Promise<TaskRow[]>;
  /** Atomically claim a Ready task → In Progress. Returns true if this agent won the claim. */
  claimTask(taskId: string): Promise<boolean>;
  // Epic
  createEpic(epic: EpicInsert): Promise<void>;
  getEpic(id: string): Promise<EpicRow | null>;
  updateEpic(id: string, updates: Partial<EpicRow>): Promise<void>;
  // Message
  saveMessage(message: Message): Promise<void>;
  // Artifact
  saveArtifact(artifact: ArtifactInsert): Promise<void>;
  // Transaction
  /** 여러 DB 작업을 하나의 트랜잭션으로 묶는다. 에러 시 자동 rollback. */
  transaction<T>(fn: (tx: unknown) => Promise<T>): Promise<T>;
  // Dashboard queries
  getAllAgents(): Promise<AgentRow[]>;
  getAllTasks(): Promise<TaskRow[]>;
  getAllEpics(): Promise<EpicRow[]>;
  getRecentMessages(limit: number): Promise<Message[]>;
}

// ===== IGitService =====
export interface IGitService {
  validateConnection(): Promise<void>;
  // Issues
  createIssue(spec: IssueSpec): Promise<number>;
  updateIssue(issueNumber: number, updates: Partial<IssueSpec>): Promise<void>;
  closeIssue(issueNumber: number): Promise<void>;
  getIssue(issueNumber: number): Promise<BoardIssue>;
  getIssuesByLabel(label: string): Promise<BoardIssue[]>;
  getEpicIssues(epicId: string): Promise<BoardIssue[]>;
  // Issue comments
  addComment(issueNumber: number, body: string): Promise<void>;
  // Board — single query for all items
  getAllProjectItems(): Promise<BoardIssue[]>;
  moveIssueToColumn(issueNumber: number, column: string): Promise<void>;
  // Git operations
  createBranch(branchName: string, baseBranch?: string): Promise<void>;
  createPR(title: string, body: string, head: string, base?: string, linkedIssues?: number[]): Promise<number>;
}

// ===== UserInput =====
export interface UserInput {
  source: 'cli' | 'dashboard';
  content: string;
  timestamp: Date;
}

// ===== MessageHandler =====
export type MessageHandler = (message: Message) => void | Promise<void>;

// ===== IMessageBus =====
export interface IMessageBus {
  publish(message: Message): Promise<void>;
  subscribe(type: string, handler: MessageHandler): void;
  subscribeAll(handler: MessageHandler): void;
  unsubscribe(type: string, handler: MessageHandler): void;
}
