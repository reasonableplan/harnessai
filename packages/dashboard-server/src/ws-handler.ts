import { WebSocketServer, WebSocket } from 'ws';
import type { IncomingMessage } from 'http';
import type { Server } from 'http';
import { createLogger, MESSAGE_TYPES } from '@agent/core';
import type { DashboardEvent, DashboardCommand, DashboardDependencies, DashboardStateStore } from './types.js';
import { EventMapper } from './event-mapper.js';

const log = createLogger('WSHandler');

const HEARTBEAT_INTERVAL_MS = 30_000;

interface ExtendedWebSocket extends WebSocket {
  isAlive: boolean;
}

export class WSHandler {
  private wss: WebSocketServer;
  private clients = new Set<ExtendedWebSocket>();
  private eventMapper: EventMapper;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private deps: DashboardDependencies;

  constructor(server: Server, deps: DashboardDependencies) {
    this.deps = deps;
    this.eventMapper = new EventMapper(deps.stateStore);

    this.wss = new WebSocketServer({ server });

    this.wss.on('connection', (ws: WebSocket, req: IncomingMessage) => {
      this.handleConnection(ws as ExtendedWebSocket, req);
    });

    // Subscribe to all MessageBus events and broadcast as DashboardEvents
    deps.messageBus.subscribeAll(async (message) => {
      try {
        const events = await this.eventMapper.map(message);
        for (const event of events) {
          this.broadcast(event);
        }
      } catch (err) {
        log.error({ err }, 'Error mapping message to dashboard event');
      }
    });

    // Start heartbeat ping/pong
    this.startHeartbeat();

    log.info('WebSocket server initialized');
  }

  /**
   * Broadcast a DashboardEvent to all connected clients.
   */
  broadcast(event: DashboardEvent): void {
    const data = JSON.stringify(event);
    for (const client of this.clients) {
      if (client.readyState === WebSocket.OPEN) {
        client.send(data);
      }
    }
  }

  /**
   * Get the number of connected clients.
   */
  get clientCount(): number {
    return this.clients.size;
  }

  /**
   * Shut down the WebSocket server and clean up.
   */
  close(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
    for (const client of this.clients) {
      client.close(1001, 'Server shutting down');
    }
    this.clients.clear();
    this.wss.close();
    log.info('WebSocket server closed');
  }

  private async handleConnection(ws: ExtendedWebSocket, req: IncomingMessage): Promise<void> {
    ws.isAlive = true;
    this.clients.add(ws);

    const clientIp = req.socket.remoteAddress ?? 'unknown';
    log.info({ clientIp, clients: this.clients.size }, 'Client connected');

    // Respond to pongs
    ws.on('pong', () => {
      ws.isAlive = true;
    });

    // Send initial state snapshot
    await this.sendInitialState(ws);

    // Handle incoming messages
    ws.on('message', (data: Buffer) => {
      this.handleMessage(ws, data);
    });

    ws.on('close', () => {
      this.clients.delete(ws);
      log.info({ clients: this.clients.size }, 'Client disconnected');
    });

    ws.on('error', (err) => {
      log.error({ err }, 'WebSocket client error');
      this.clients.delete(ws);
    });
  }

  private async sendInitialState(ws: ExtendedWebSocket): Promise<void> {
    try {
      const [agents, tasks, epics] = await Promise.all([
        this.deps.stateStore.getAllAgents(),
        this.deps.stateStore.getAllTasks(),
        this.deps.stateStore.getAllEpics(),
      ]);

      const event: DashboardEvent = {
        type: 'initial-state',
        payload: { agents, tasks, epics },
      };

      ws.send(JSON.stringify(event));
    } catch (err) {
      log.error({ err }, 'Failed to send initial state');
    }
  }

  private async handleMessage(ws: ExtendedWebSocket, data: Buffer): Promise<void> {
    let command: DashboardCommand;
    try {
      command = JSON.parse(data.toString()) as DashboardCommand;
    } catch {
      log.warn('Received invalid JSON from client');
      ws.send(JSON.stringify({ error: 'Invalid JSON' }));
      return;
    }

    log.info({ type: command.type }, 'Received command');

    try {
      switch (command.type) {
        case 'user-input':
          await this.handleUserInput(command.payload);
          break;

        case 'agent-pause':
          await this.handleAgentPause(command.payload.agentId);
          break;

        case 'agent-resume':
          await this.handleAgentResume(command.payload.agentId);
          break;

        case 'task-move':
          await this.handleTaskMove(command.payload);
          break;

        case 'task-retry':
          await this.handleTaskRetry(command.payload.taskId);
          break;

        case 'system-pause':
          await this.handleSystemPause();
          break;

        case 'system-resume':
          await this.handleSystemResume();
          break;

        default:
          log.warn({ type: (command as DashboardCommand).type }, 'Unknown command type');
      }
    } catch (err) {
      log.error({ err, type: command.type }, 'Error handling command');
      ws.send(JSON.stringify({ error: `Failed to handle command: ${command.type}` }));
    }
  }

  private async handleUserInput(payload: { text: string }): Promise<void> {
    await this.deps.messageBus.publish({
      id: crypto.randomUUID(),
      type: MESSAGE_TYPES.USER_INPUT,
      from: 'dashboard',
      to: 'director',
      payload: {
        source: 'dashboard' as const,
        content: payload.text,
        timestamp: new Date(),
      },
      traceId: crypto.randomUUID(),
      timestamp: new Date(),
    });

    this.broadcast({
      type: 'toast',
      payload: {
        type: 'info',
        title: 'Command Sent',
        message: `"${payload.text}" sent to Director`,
      },
    });
  }

  private async handleAgentPause(agentId: string): Promise<void> {
    if (this.deps.agentRegistry) {
      await this.deps.agentRegistry.pause(agentId);
    } else {
      log.warn('Agent registry not available — cannot pause agent');
    }
  }

  private async handleAgentResume(agentId: string): Promise<void> {
    if (this.deps.agentRegistry) {
      await this.deps.agentRegistry.resume(agentId);
    } else {
      log.warn('Agent registry not available — cannot resume agent');
    }
  }

  private async handleTaskMove(payload: { taskId: string; toColumn: string }): Promise<void> {
    await this.deps.stateStore.updateTask(payload.taskId, {
      boardColumn: payload.toColumn,
    });

    const task = await this.deps.stateStore.getTask(payload.taskId);
    if (task) {
      this.broadcast({
        type: 'board-update',
        payload: { taskId: payload.taskId, column: payload.toColumn, task },
      });
    }
  }

  private async handleTaskRetry(taskId: string): Promise<void> {
    const task = await this.deps.stateStore.getTask(taskId);
    if (!task) {
      log.warn({ taskId }, 'Task not found for retry');
      return;
    }

    await this.deps.stateStore.updateTask(taskId, {
      boardColumn: 'Ready',
      status: 'ready',
      retryCount: (task.retryCount ?? 0) + 1,
    });

    const updatedTask = await this.deps.stateStore.getTask(taskId);
    if (updatedTask) {
      this.broadcast({
        type: 'board-update',
        payload: { taskId, column: 'Ready', task: updatedTask },
      });
    }

    this.broadcast({
      type: 'toast',
      payload: {
        type: 'info',
        title: 'Task Retried',
        message: `"${task.title}" moved back to Ready for retry`,
      },
    });
  }

  private async handleSystemPause(): Promise<void> {
    if (this.deps.agentRegistry) {
      await this.deps.agentRegistry.pauseAll();
      this.broadcast({
        type: 'toast',
        payload: { type: 'info', title: 'System Paused', message: 'All agents have been paused' },
      });
    } else {
      log.warn('Agent registry not available — cannot pause system');
    }
  }

  private async handleSystemResume(): Promise<void> {
    if (this.deps.agentRegistry) {
      await this.deps.agentRegistry.resumeAll();
      this.broadcast({
        type: 'toast',
        payload: { type: 'info', title: 'System Resumed', message: 'All agents have been resumed' },
      });
    } else {
      log.warn('Agent registry not available — cannot resume system');
    }
  }

  private startHeartbeat(): void {
    this.heartbeatTimer = setInterval(() => {
      for (const client of this.clients) {
        if (!client.isAlive) {
          log.info('Terminating dead WebSocket connection');
          client.terminate();
          this.clients.delete(client);
          continue;
        }
        client.isAlive = false;
        client.ping();
      }
    }, HEARTBEAT_INTERVAL_MS);
  }
}
