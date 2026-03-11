import { createServer, type Server } from 'http';
import express from 'express';
import cors from 'cors';
import { createLogger } from '@agent/core';
import type { Message, AgentRow, TaskRow, EpicRow } from '@agent/core';
import { createRoutes } from './routes.js';
import { WSHandler } from './ws-handler.js';
import type { DashboardDependencies, DashboardStateStore, DashboardMessageBus, AgentRegistry } from './types.js';

export type { DashboardDependencies, DashboardStateStore, DashboardMessageBus, AgentRegistry } from './types.js';
export type { DashboardEvent, DashboardCommand } from './types.js';

const log = createLogger('DashboardServer');

export interface DashboardServer {
  /** The underlying HTTP server */
  httpServer: Server;
  /** The WebSocket handler for broadcasting events */
  wsHandler: WSHandler;
  /** Start listening on the given port */
  listen(port: number): Promise<void>;
  /** Shut down the server gracefully */
  close(): Promise<void>;
}

/**
 * Factory function to create a DashboardServer with injected dependencies.
 * Used in production when integrating with the bootstrap system.
 */
export function createDashboardServer(deps: DashboardDependencies): DashboardServer {
  const app = express();

  // Middleware
  app.use(cors());
  app.use(express.json());

  // REST routes
  const router = createRoutes({
    stateStore: deps.stateStore,
    messageBus: deps.messageBus,
  });
  app.use(router);

  // Health check
  app.get('/health', (_req, res) => {
    res.json({ status: 'ok', uptime: process.uptime() });
  });

  // Create HTTP server
  const httpServer = createServer(app);

  // Attach WebSocket handler
  const wsHandler = new WSHandler(httpServer, deps);

  return {
    httpServer,
    wsHandler,
    listen(port: number): Promise<void> {
      return new Promise((resolve) => {
        httpServer.listen(port, () => {
          log.info({ port }, 'Dashboard server listening');
          resolve();
        });
      });
    },
    close(): Promise<void> {
      return new Promise((resolve, reject) => {
        wsHandler.close();
        httpServer.close((err) => {
          if (err) {
            log.error({ err }, 'Error closing HTTP server');
            reject(err);
          } else {
            log.info('Dashboard server closed');
            resolve();
          }
        });
      });
    },
  };
}

// ===== In-Memory Mock Store for standalone dev mode =====

class InMemoryStateStore implements DashboardStateStore {
  private agents: AgentRow[] = [
    {
      id: 'director',
      domain: 'orchestration',
      level: 0,
      status: 'idle',
      parentId: null,
      createdAt: new Date(),
      lastHeartbeat: new Date(),
    },
    {
      id: 'backend',
      domain: 'backend',
      level: 2,
      status: 'idle',
      parentId: 'director',
      createdAt: new Date(),
      lastHeartbeat: new Date(),
    },
    {
      id: 'frontend',
      domain: 'frontend',
      level: 2,
      status: 'idle',
      parentId: 'director',
      createdAt: new Date(),
      lastHeartbeat: new Date(),
    },
    {
      id: 'docs',
      domain: 'docs',
      level: 2,
      status: 'idle',
      parentId: 'director',
      createdAt: new Date(),
      lastHeartbeat: new Date(),
    },
    {
      id: 'git',
      domain: 'git',
      level: 2,
      status: 'idle',
      parentId: 'director',
      createdAt: new Date(),
      lastHeartbeat: new Date(),
    },
  ];

  private tasks: TaskRow[] = [
    {
      id: 'task-1',
      epicId: 'epic-1',
      title: 'Set up Express server',
      description: 'Create the Express server with middleware',
      assignedAgent: 'backend',
      status: 'in-progress',
      githubIssueNumber: 10,
      boardColumn: 'In Progress',
      priority: 2,
      complexity: 'medium',
      dependencies: [],
      labels: ['agent:backend'],
      retryCount: 0,
      createdAt: new Date(),
      startedAt: new Date(),
      completedAt: null,
      reviewNote: null,
    },
    {
      id: 'task-2',
      epicId: 'epic-1',
      title: 'Create React components',
      description: 'Build the dashboard UI components',
      assignedAgent: 'frontend',
      status: 'ready',
      githubIssueNumber: 11,
      boardColumn: 'Ready',
      priority: 3,
      complexity: 'high',
      dependencies: [],
      labels: ['agent:frontend'],
      retryCount: 0,
      createdAt: new Date(),
      startedAt: null,
      completedAt: null,
      reviewNote: null,
    },
    {
      id: 'task-3',
      epicId: null,
      title: 'Write API documentation',
      description: 'Document all REST endpoints',
      assignedAgent: 'docs',
      status: 'backlog',
      githubIssueNumber: 12,
      boardColumn: 'Backlog',
      priority: 4,
      complexity: 'low',
      dependencies: [],
      labels: ['agent:docs'],
      retryCount: 0,
      createdAt: new Date(),
      startedAt: null,
      completedAt: null,
      reviewNote: null,
    },
  ];

  private epics: EpicRow[] = [
    {
      id: 'epic-1',
      title: 'Dashboard MVP',
      description: 'Build the initial dashboard',
      status: 'in-progress',
      githubMilestoneNumber: 1,
      progress: 0.33,
      createdAt: new Date(),
      completedAt: null,
    },
  ];

  private messages: Message[] = [];

  async getAgent(id: string): Promise<AgentRow | null> {
    return this.agents.find((a) => a.id === id) ?? null;
  }

  async getTask(id: string): Promise<TaskRow | null> {
    return this.tasks.find((t) => t.id === id) ?? null;
  }

  async updateTask(id: string, updates: Partial<TaskRow>): Promise<void> {
    const idx = this.tasks.findIndex((t) => t.id === id);
    if (idx >= 0) {
      this.tasks[idx] = { ...this.tasks[idx], ...updates };
    }
  }

  async getTasksByColumn(column: string): Promise<TaskRow[]> {
    return this.tasks.filter((t) => t.boardColumn === column);
  }

  async getAllAgents(): Promise<AgentRow[]> {
    return [...this.agents];
  }

  async getAllTasks(): Promise<TaskRow[]> {
    return [...this.tasks];
  }

  async getAllEpics(): Promise<EpicRow[]> {
    return [...this.epics];
  }

  async getRecentMessages(limit: number): Promise<Message[]> {
    return this.messages.slice(-limit);
  }

  // Allow the mock message bus to push messages
  addMessage(message: Message): void {
    this.messages.push(message);
  }
}

class InMemoryMessageBus implements DashboardMessageBus {
  private allHandlers: Array<(message: Message) => void | Promise<void>> = [];
  private stateStore: InMemoryStateStore;

  constructor(stateStore: InMemoryStateStore) {
    this.stateStore = stateStore;
  }

  async publish(message: Message): Promise<void> {
    this.stateStore.addMessage(message);
    for (const handler of this.allHandlers) {
      try {
        await handler(message);
      } catch (err) {
        log.error({ err }, 'Mock MessageBus handler error');
      }
    }
  }

  subscribeAll(handler: (message: Message) => void | Promise<void>): void {
    this.allHandlers.push(handler);
  }
}

/**
 * Start the dashboard server in standalone dev mode.
 * Creates its own in-memory state store and message bus — no PostgreSQL or GitHub needed.
 */
export async function startStandalone(): Promise<DashboardServer> {
  const port = Number(process.env.DASHBOARD_PORT) || 3001;

  const stateStore = new InMemoryStateStore();
  const messageBus = new InMemoryMessageBus(stateStore);

  const server = createDashboardServer({
    stateStore,
    messageBus,
  });

  await server.listen(port);

  log.info({ port }, 'Dashboard server running in standalone dev mode');
  log.info(`  REST API: http://localhost:${port}/api`);
  log.info(`  WebSocket: ws://localhost:${port}`);
  log.info(`  Health:    http://localhost:${port}/health`);

  return server;
}

// If this file is run directly, start in standalone mode
const isDirectRun = process.argv[1] && (
  process.argv[1].endsWith('index.ts') ||
  process.argv[1].endsWith('index.js')
);

if (isDirectRun) {
  startStandalone().catch((err) => {
    log.error({ err }, 'Failed to start standalone dashboard server');
    process.exit(1);
  });
}
