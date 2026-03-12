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
      const id = req.params.id;
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
      const limit = Math.min(Number(req.query.limit) || 50, 200);
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

  // POST /api/commands — receives user commands
  router.post('/api/commands', async (req: Request, res: Response, next: NextFunction) => {
    try {
      const { text } = req.body as { text?: string };
      if (!text || typeof text !== 'string') {
        res.status(400).json({ error: 'Missing required field: text' });
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
