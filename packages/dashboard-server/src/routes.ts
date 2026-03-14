import { Router, type Request, type Response, type NextFunction } from 'express';
import { createLogger, MESSAGE_TYPES, BOARD_COLUMNS } from '@agent/core';
import type { DashboardStateStore, DashboardMessageBus } from './types.js';

const log = createLogger('DashboardRoutes');

export interface RouteDependencies {
  stateStore: DashboardStateStore;
  messageBus: DashboardMessageBus;
}

export function createRoutes(deps: RouteDependencies): Router {
  const router = Router();
  const { stateStore, messageBus } = deps;

  // GET /api/agents — returns all agents with status
  router.get('/api/agents', async (_req: Request, res: Response, next: NextFunction) => {
    try {
      const agents = await stateStore.getAllAgents();
      res.json({ agents });
    } catch (err) {
      next(err);
    }
  });

  // GET /api/tasks — returns all tasks grouped by board column
  router.get('/api/tasks', async (_req: Request, res: Response, next: NextFunction) => {
    try {
      const allTasks = await stateStore.getAllTasks();

      const grouped: Record<string, typeof allTasks> = {};
      for (const col of BOARD_COLUMNS) {
        grouped[col] = [];
      }
      for (const task of allTasks) {
        const col = task.boardColumn ?? 'Backlog';
        if (!grouped[col]) {
          grouped[col] = [];
        }
        grouped[col].push(task);
      }

      res.json({ tasks: grouped });
    } catch (err) {
      next(err);
    }
  });

  // GET /api/tasks/:id — returns single task
  router.get('/api/tasks/:id', async (req: Request, res: Response, next: NextFunction) => {
    try {
      const id = req.params.id as string;
      const task = await stateStore.getTask(id);
      if (!task) {
        res.status(404).json({ error: 'Task not found' });
        return;
      }
      res.json({ task });
    } catch (err) {
      next(err);
    }
  });

  // GET /api/epics — returns all epics with progress
  router.get('/api/epics', async (_req: Request, res: Response, next: NextFunction) => {
    try {
      const epics = await stateStore.getAllEpics();
      res.json({ epics });
    } catch (err) {
      next(err);
    }
  });

  // GET /api/messages — returns recent messages (last 50)
  router.get('/api/messages', async (req: Request, res: Response, next: NextFunction) => {
    try {
      const rawLimit = Number(req.query.limit);
      const limit = Math.min(Math.max(1, isNaN(rawLimit) ? 50 : rawLimit), 200);
      const messages = await stateStore.getRecentMessages(limit);
      res.json({ messages });
    } catch (err) {
      next(err);
    }
  });

  // GET /api/system/status — returns system summary
  router.get('/api/system/status', async (_req: Request, res: Response, next: NextFunction) => {
    try {
      const [agents, tasks, epics] = await Promise.all([
        stateStore.getAllAgents(),
        stateStore.getAllTasks(),
        stateStore.getAllEpics(),
      ]);

      const tasksByColumn: Record<string, number> = {};
      for (const col of BOARD_COLUMNS) {
        tasksByColumn[col] = 0;
      }
      for (const task of tasks) {
        const col = task.boardColumn ?? 'Backlog';
        tasksByColumn[col] = (tasksByColumn[col] ?? 0) + 1;
      }

      const agentsByStatus: Record<string, number> = {};
      for (const agent of agents) {
        agentsByStatus[agent.status] = (agentsByStatus[agent.status] ?? 0) + 1;
      }

      const activeEpics = epics.filter((e) => e.status !== 'done' && e.status !== 'cancelled');

      res.json({
        system: {
          agentCount: agents.length,
          taskCount: tasks.length,
          epicCount: epics.length,
          agentsByStatus,
          tasksByColumn,
          activeEpics: activeEpics.map((e) => ({
            id: e.id,
            title: e.title,
            progress: e.progress,
            status: e.status,
          })),
          uptime: process.uptime(),
        },
      });
    } catch (err) {
      next(err);
    }
  });

  // GET /api/agents/:id/stats — returns agent task statistics
  router.get('/api/agents/:id/stats', async (req: Request, res: Response, next: NextFunction) => {
    try {
      const stats = await stateStore.getAgentStats(req.params.id as string);
      res.json({ stats });
    } catch (err) {
      next(err);
    }
  });

  // GET /api/tasks/:id/history — returns task history from messages
  router.get('/api/tasks/:id/history', async (req: Request, res: Response, next: NextFunction) => {
    try {
      const history = await stateStore.getTaskHistory(req.params.id as string);
      res.json({ history });
    } catch (err) {
      next(err);
    }
  });

  // GET /api/stats/summary — returns overall system statistics
  router.get('/api/stats/summary', async (_req: Request, res: Response, next: NextFunction) => {
    try {
      const agents = await stateStore.getAllAgents();
      const allTasks = await stateStore.getAllTasks();

      const totalTasks = allTasks.length;
      const doneTasks = allTasks.filter((t) => t.status === 'done').length;
      const failedTasks = allTasks.filter((t) => t.status === 'failed').length;
      const completionRate = totalTasks > 0 ? doneTasks / totalTasks : 0;

      const agentSummaries = await Promise.all(
        agents.map((a) => stateStore.getAgentStats(a.id)),
      );

      res.json({
        summary: {
          totalTasks,
          doneTasks,
          failedTasks,
          completionRate,
          agentStats: agentSummaries,
        },
      });
    } catch (err) {
      next(err);
    }
  });

  // GET /api/agents/:id/config — returns agent configuration
  router.get('/api/agents/:id/config', async (req: Request, res: Response, next: NextFunction) => {
    try {
      const id = req.params.id as string;
      const config = await stateStore.getAgentConfig(id);
      res.json({
        config: config ?? {
          agentId: id,
          claudeModel: 'claude-sonnet-4-20250514',
          maxTokens: 4096,
          temperature: 0.7,
          tokenBudget: 10_000_000,
          taskTimeoutMs: 300_000,
          pollIntervalMs: 10_000,
        },
      });
    } catch (err) {
      next(err);
    }
  });

  // PUT /api/agents/:id/config — update agent configuration
  router.put('/api/agents/:id/config', async (req: Request, res: Response, next: NextFunction) => {
    try {
      const agentId = req.params.id as string;
      const updates = req.body as Record<string, unknown>;

      // Validate fields — whitelist keys, then validate types and ranges
      const allowed = ['claudeModel', 'maxTokens', 'temperature', 'tokenBudget', 'taskTimeoutMs', 'pollIntervalMs'];
      const filtered: Record<string, unknown> = {};
      for (const key of allowed) {
        if (updates[key] !== undefined) filtered[key] = updates[key];
      }

      // Type and range validation
      const validationErrors: string[] = [];
      const ALLOWED_MODELS = new Set([
        'claude-sonnet-4-20250514',
        'claude-opus-4-20250514',
        'claude-haiku-4-5-20251001',
      ]);
      if (filtered.claudeModel !== undefined) {
        if (typeof filtered.claudeModel !== 'string' || !ALLOWED_MODELS.has(filtered.claudeModel)) {
          validationErrors.push(`claudeModel must be one of: ${[...ALLOWED_MODELS].join(', ')}`);
        }
      }
      if (filtered.maxTokens !== undefined) {
        if (typeof filtered.maxTokens !== 'number' || filtered.maxTokens < 1 || filtered.maxTokens > 200_000) {
          validationErrors.push('maxTokens must be a number between 1 and 200000');
        }
      }
      if (filtered.temperature !== undefined) {
        if (typeof filtered.temperature !== 'number' || filtered.temperature < 0 || filtered.temperature > 2) {
          validationErrors.push('temperature must be a number between 0 and 2');
        }
      }
      if (filtered.tokenBudget !== undefined) {
        if (typeof filtered.tokenBudget !== 'number' || filtered.tokenBudget < 1000) {
          validationErrors.push('tokenBudget must be a number >= 1000');
        }
      }
      if (filtered.taskTimeoutMs !== undefined) {
        if (typeof filtered.taskTimeoutMs !== 'number' || filtered.taskTimeoutMs < 5_000 || filtered.taskTimeoutMs > 3_600_000) {
          validationErrors.push('taskTimeoutMs must be between 5000 and 3600000');
        }
      }
      if (filtered.pollIntervalMs !== undefined) {
        if (typeof filtered.pollIntervalMs !== 'number' || filtered.pollIntervalMs < 1_000 || filtered.pollIntervalMs > 300_000) {
          validationErrors.push('pollIntervalMs must be between 1000 and 300000');
        }
      }
      if (validationErrors.length > 0) {
        res.status(400).json({ error: 'Validation failed', details: validationErrors });
        return;
      }

      await stateStore.upsertAgentConfig(agentId, filtered);

      // Publish config update event so agents can hot-reload
      await messageBus.publish({
        id: crypto.randomUUID(),
        type: MESSAGE_TYPES.AGENT_CONFIG_UPDATED,
        from: 'dashboard',
        to: agentId,
        payload: { agentId, config: filtered },
        traceId: crypto.randomUUID(),
        timestamp: new Date(),
      });

      res.json({ ok: true });
    } catch (err) {
      next(err);
    }
  });

  // GET /api/hooks — returns registered hooks
  router.get('/api/hooks', async (_req: Request, res: Response, next: NextFunction) => {
    try {
      const allHooks = await stateStore.getAllHooks();
      res.json({ hooks: allHooks });
    } catch (err) {
      next(err);
    }
  });

  // PUT /api/hooks/:id/toggle — toggle hook enabled/disabled
  router.put('/api/hooks/:id/toggle', async (req: Request, res: Response, next: NextFunction) => {
    try {
      const { enabled } = req.body as { enabled: boolean };
      if (typeof enabled !== 'boolean') {
        res.status(400).json({ error: 'Missing required field: enabled (boolean)' });
        return;
      }
      await stateStore.toggleHook(req.params.id as string, enabled);
      res.json({ ok: true });
    } catch (err) {
      next(err);
    }
  });

  // POST /api/commands — receives user commands
  router.post('/api/commands', async (req: Request, res: Response, next: NextFunction) => {
    try {
      const { text } = req.body as { text?: string };
      if (!text || typeof text !== 'string' || text.length > 2000) {
        res.status(400).json({ error: 'Missing or invalid field: text (string, max 2000 chars)' });
        return;
      }

      await messageBus.publish({
        id: crypto.randomUUID(),
        type: MESSAGE_TYPES.USER_INPUT,
        from: 'dashboard',
        to: 'director',
        payload: {
          source: 'dashboard' as const,
          content: text,
          timestamp: new Date(),
        },
        traceId: crypto.randomUUID(),
        timestamp: new Date(),
      });

      res.json({ ok: true, message: 'Command sent to Director' });
    } catch (err) {
      next(err);
    }
  });

  // Error handling middleware
  router.use((err: Error, _req: Request, res: Response, _next: NextFunction) => {
    log.error({ err }, 'Route error');
    res.status(500).json({ error: 'Internal server error' });
  });

  return router;
}
