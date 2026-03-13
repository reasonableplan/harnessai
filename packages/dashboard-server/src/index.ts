import { createServer, type Server } from 'http';
import { existsSync, realpathSync } from 'fs';
import { resolve } from 'path';
import express from 'express';
import cors from 'cors';
import { createLogger } from '@agent/core';
import type { Message, AgentRow, TaskRow, EpicRow, AgentStats, TaskHistoryEntry, AgentConfigRow, HookRow } from '@agent/core';
import { createAuthMiddleware } from './auth-middleware.js';
import { createRoutes } from './routes.js';
import { WSHandler } from './ws-handler.js';
import type { DashboardDependencies, DashboardStateStore, DashboardMessageBus } from './types.js';

export type {
  DashboardDependencies,
  DashboardStateStore,
  DashboardMessageBus,
  AgentRegistry,
} from './types.js';
export type { DashboardEvent, DashboardCommand } from './types.js';
export { EventMapper } from './event-mapper.js';
export { createAuthMiddleware, validateWsToken } from './auth-middleware.js';

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
export interface DashboardServerOptions {
  corsOrigins?: string[];
  /** Path to built dashboard-client dist folder. If provided, serves static files + SPA fallback. */
  staticDir?: string;
  /** Bearer token for REST + WS auth. If empty/undefined, auth is skipped (dev mode). */
  authToken?: string;
}

export function createDashboardServer(
  deps: DashboardDependencies,
  opts: DashboardServerOptions = {},
): DashboardServer {
  const app = express();

  // Middleware
  const defaultOrigins = process.env.CORS_ORIGINS
    ? process.env.CORS_ORIGINS.split(',').map((s) => s.trim())
    : ['http://localhost:3000', 'http://localhost:5173'];
  const allowedOrigins = opts.corsOrigins ?? defaultOrigins;
  app.use(
    cors({
      origin: allowedOrigins,
      methods: ['GET', 'POST', 'PUT'],
      credentials: true,
    }),
  );
  app.use(express.json({ limit: '64kb' }));

  // Simple in-memory rate limiter (100 req/min per IP) with periodic cleanup
  const rateLimitMap = new Map<string, { count: number; resetAt: number }>();
  const RATE_LIMIT_WINDOW_MS = 60_000;
  const RATE_LIMIT_MAX = 100;
  const RATE_LIMIT_CLEANUP_INTERVAL_MS = 5 * 60_000; // 5분마다 만료 엔트리 정리

  const rateLimitCleanupTimer = setInterval(() => {
    const now = Date.now();
    for (const [ip, entry] of rateLimitMap) {
      if (now > entry.resetAt) rateLimitMap.delete(ip);
    }
  }, RATE_LIMIT_CLEANUP_INTERVAL_MS);
  rateLimitCleanupTimer.unref(); // 프로세스 종료 차단 방지

  app.use('/api', (req, res, next) => {
    const ip = req.ip ?? 'unknown';
    const now = Date.now();
    const entry = rateLimitMap.get(ip);

    if (!entry || now > entry.resetAt) {
      rateLimitMap.set(ip, { count: 1, resetAt: now + RATE_LIMIT_WINDOW_MS });
      return next();
    }

    entry.count++;
    if (entry.count > RATE_LIMIT_MAX) {
      res.status(429).json({ error: 'Too many requests. Try again later.' });
      return;
    }

    next();
  });

  // Auth middleware (skipped if no token configured)
  app.use('/api', createAuthMiddleware(opts.authToken));

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

  // Serve built dashboard-client static files (production single-port mode)
  if (opts.staticDir && existsSync(opts.staticDir)) {
    app.use(express.static(opts.staticDir));
    // API 404 handler: /api/* 경로는 JSON 404 반환
    app.all('/api/{*path}', (_req, res) => {
      res.status(404).json({ error: 'Not found' });
    });
    // SPA fallback: any non-API route returns index.html
    app.get('{*path}', (_req, res) => {
      res.sendFile(resolve(opts.staticDir!, 'index.html'));
    });
    log.info({ staticDir: opts.staticDir }, 'Serving static dashboard files');
  }

  // Create HTTP server
  const httpServer = createServer(app);

  // Attach WebSocket handler
  const wsHandler = new WSHandler(httpServer, deps, opts.authToken);

  return {
    httpServer,
    wsHandler,
    listen(port: number): Promise<void> {
      return new Promise((resolve, reject) => {
        httpServer.once('error', reject);
        httpServer.listen(port, () => {
          httpServer.removeListener('error', reject);
          log.info({ port }, 'Dashboard server listening');
          resolve();
        });
      });
    },
    close(): Promise<void> {
      return new Promise((resolve, reject) => {
        clearInterval(rateLimitCleanupTimer);
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
    const existing = this.tasks[idx];
    if (idx >= 0 && existing !== undefined) {
      this.tasks[idx] = { ...existing, ...updates };
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

  // Stats & Config & Hooks (mock implementations for dev mode)
  async getAgentStats(agentId: string): Promise<AgentStats> {
    const agentTasks = this.tasks.filter((t) => t.assignedAgent === agentId);
    const done = agentTasks.filter((t) => t.status === 'done').length;
    const failed = agentTasks.filter((t) => t.status === 'failed').length;
    const total = agentTasks.length;
    return {
      agentId,
      totalTasks: total,
      completedTasks: done,
      failedTasks: failed,
      inProgressTasks: agentTasks.filter((t) => t.status === 'in-progress').length,
      completionRate: total > 0 ? done / total : 0,
      avgDurationMs: null,
      totalRetries: agentTasks.reduce((s, t) => s + (t.retryCount ?? 0), 0),
    };
  }

  async getTaskHistory(_taskId: string): Promise<TaskHistoryEntry[]> {
    return [];
  }

  private configs = new Map<string, AgentConfigRow>();

  async getAgentConfig(agentId: string): Promise<AgentConfigRow | null> {
    return this.configs.get(agentId) ?? null;
  }

  async upsertAgentConfig(agentId: string, config: Partial<AgentConfigRow>): Promise<void> {
    const existing = this.configs.get(agentId);
    this.configs.set(agentId, {
      agentId,
      claudeModel: config.claudeModel ?? existing?.claudeModel ?? 'claude-sonnet-4-20250514',
      maxTokens: config.maxTokens ?? existing?.maxTokens ?? 4096,
      temperature: config.temperature ?? existing?.temperature ?? 0.7,
      tokenBudget: config.tokenBudget ?? existing?.tokenBudget ?? 10_000_000,
      taskTimeoutMs: config.taskTimeoutMs ?? existing?.taskTimeoutMs ?? 300_000,
      pollIntervalMs: config.pollIntervalMs ?? existing?.pollIntervalMs ?? 10_000,
      updatedAt: new Date(),
    });
  }

  private hookList: HookRow[] = [
    { id: 'log-task-complete', event: 'hook.task.completed', name: 'Log Task Completion', description: 'Logs task completions', enabled: true, createdAt: new Date() },
    { id: 'toast-on-failure', event: 'hook.task.failed', name: 'Toast on Failure', description: 'Toast on task failure', enabled: true, createdAt: new Date() },
    { id: 'log-agent-error', event: 'hook.agent.error', name: 'Log Agent Error', description: 'Logs agent errors', enabled: true, createdAt: new Date() },
  ];

  async getAllHooks(): Promise<HookRow[]> {
    return [...this.hookList];
  }

  async toggleHook(id: string, enabled: boolean): Promise<void> {
    const hook = this.hookList.find((h) => h.id === id);
    if (hook) hook.enabled = enabled;
  }

  // Allow the mock message bus to push messages
  private static readonly MESSAGE_BUFFER_MAX = 1000;
  private static readonly MESSAGE_BUFFER_TRIM_TO = 500;

  addMessage(message: Message): void {
    this.messages.push(message);
    if (this.messages.length > InMemoryStateStore.MESSAGE_BUFFER_MAX) {
      this.messages = this.messages.slice(-InMemoryStateStore.MESSAGE_BUFFER_TRIM_TO);
    }
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
 *
 * @param devPort 포트 번호. 미지정 시 DASHBOARD_PORT 환경변수 또는 3001.
 */
export async function startStandalone(devPort?: number): Promise<DashboardServer> {
  const port = devPort ?? (Number(process.env.DASHBOARD_PORT) || 3001);

  const stateStore = new InMemoryStateStore();
  const messageBus = new InMemoryMessageBus(stateStore);

  // No-op agent registry for standalone dev mode (pause/resume log instead of acting)
  const noopRegistry = {
    async pause(agentId: string) { log.info({ agentId }, '[dev] Agent pause requested (no-op)'); },
    async resume(agentId: string) { log.info({ agentId }, '[dev] Agent resume requested (no-op)'); },
    async pauseAll() { log.info('[dev] System pause requested (no-op)'); },
    async resumeAll() { log.info('[dev] System resume requested (no-op)'); },
  };

  const server = createDashboardServer({
    stateStore,
    messageBus,
    agentRegistry: noopRegistry,
  });

  await server.listen(port);

  log.info({ port }, 'Dashboard server running in standalone dev mode');
  log.info(`  REST API: http://localhost:${port}/api`);
  log.info(`  WebSocket: ws://localhost:${port}`);
  log.info(`  Health:    http://localhost:${port}/health`);

  return server;
}

// If this file is run directly (not bundled into another package), start in standalone mode.
// Check import.meta.url against process.argv[1] to avoid false positives when
// this code is bundled into other packages (e.g., @agent/main) by tsup.
// realpathSync로 심볼릭 링크/junction 경로 정규화하여 비교 정확성 보장.
import { fileURLToPath as _fileURLToPath } from 'url';

function _isDirectRun(): boolean {
  if (!process.argv[1]) return false;
  try {
    const thisFile = realpathSync(_fileURLToPath(import.meta.url));
    const entryFile = realpathSync(resolve(process.argv[1]));
    return thisFile === entryFile;
  } catch {
    return false;
  }
}

const isDirectRun = _isDirectRun();

if (isDirectRun) {
  startStandalone().catch((err) => {
    log.error({ err }, 'Failed to start standalone dashboard server');
    process.exit(1);
  });
}
