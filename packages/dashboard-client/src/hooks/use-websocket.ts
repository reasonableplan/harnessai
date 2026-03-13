import { useEffect, useRef, useCallback } from 'react';
import { useOfficeStore } from '@/stores/office-store';

interface DashboardEvent {
  type: string;
  payload: Record<string, unknown>;
}

const MAX_RECONNECT_ATTEMPTS = 20;

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const reconnectAttemptRef = useRef(0);
  const connectRef = useRef<() => void>(null);

  const handleEvent = useCallback((event: DashboardEvent) => {
    const { type, payload } = event;
    const { setInitialState, updateAgent, updateTask, updateEpic, addMessage, addToast } =
      useOfficeStore.getState();

    switch (type) {
      case 'init':
        setInitialState(mapInitPayload(payload));
        break;

      case 'agent.status':
        if (payload.agentId && typeof payload.agentId === 'string') {
          updateAgent(payload.agentId, {
            status: payload.status as string,
            ...(payload.task ? { currentTask: payload.task as string } : {}),
          });
        }
        break;

      case 'agent.bubble':
        if (payload.agentId && typeof payload.agentId === 'string') {
          updateAgent(payload.agentId, {
            bubble: payload.bubble as {
              content: string;
              type: 'task' | 'thinking' | 'info' | 'error';
            } | null,
          });
        }
        break;

      case 'task.update':
        if (payload.taskId && typeof payload.taskId === 'string') {
          const { taskId, status, boardColumn, assignedAgent, title, epicId } = payload as Record<string, unknown>;
          updateTask(taskId as string, {
            ...(status != null && { status: status as string }),
            ...(boardColumn != null && { boardColumn: boardColumn as string }),
            ...(assignedAgent !== undefined && { assignedAgent: assignedAgent as string | null }),
            ...(title != null && { title: title as string }),
            ...(epicId !== undefined && { epicId: epicId as string | null }),
          });
        }
        break;

      case 'epic.progress':
        if (payload.epicId && typeof payload.epicId === 'string') {
          const { epicId, title, progress } = payload as Record<string, unknown>;
          updateEpic(epicId as string, {
            ...(title != null && { title: title as string }),
            ...(progress != null && { progress: progress as number }),
          });
        }
        break;

      case 'message':
        addMessage({
          id: (payload.id as string) ?? `msg-${Date.now()}`,
          type: (payload.type as string) ?? 'info',
          from: (payload.from as string) ?? 'system',
          content: (payload.content as string) ?? '',
          timestamp: (payload.timestamp as string) ?? new Date().toISOString(),
        });
        break;

      case 'token.usage':
        if (payload.agentId && typeof payload.agentId === 'string') {
          const { updateTokenUsage } = useOfficeStore.getState();
          updateTokenUsage(
            payload.agentId as string,
            (payload.inputTokens as number) ?? 0,
            (payload.outputTokens as number) ?? 0,
          );
        }
        break;

      case 'agent.config':
        if (payload.agentId && typeof payload.agentId === 'string' && payload.config) {
          const { setAgentConfig } = useOfficeStore.getState();
          setAgentConfig(payload.agentId, payload.config as Record<string, unknown> as Parameters<typeof setAgentConfig>[1]);
        }
        break;

      case 'toast':
        addToast({
          id: `toast-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          type: (payload.type as 'success' | 'error' | 'info' | 'warning') ?? 'info',
          title: (payload.title as string) ?? '',
          message: (payload.message as string) ?? '',
        });
        break;

      default:
        addMessage({
          id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          type,
          from: (payload.from as string) ?? 'system',
          content: JSON.stringify(payload),
          timestamp: new Date().toISOString(),
        });
    }
  }, []);

  const scheduleReconnect = useCallback(() => {
    const attempt = reconnectAttemptRef.current;
    if (attempt >= MAX_RECONNECT_ATTEMPTS) {
      useOfficeStore.getState().addToast({
        id: `toast-max-reconnect-${Date.now()}`,
        type: 'error',
        title: 'Connection Lost',
        message: `Failed to reconnect after ${MAX_RECONNECT_ATTEMPTS} attempts. Retrying in 30s...`,
      });
      // Instead of giving up permanently, reset counter after a long delay and retry
      reconnectTimeoutRef.current = setTimeout(() => {
        reconnectAttemptRef.current = 0;
        connectRef.current?.();
      }, 30000);
      return;
    }

    const delay = Math.min(1000 * Math.pow(2, attempt), 30000);
    reconnectAttemptRef.current = attempt + 1;

    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    reconnectTimeoutRef.current = setTimeout(() => {
      connectRef.current?.();
    }, delay);
  }, []);

  const connect = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = import.meta.env.VITE_WS_URL ?? `${protocol}//${window.location.host}/ws`;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        reconnectAttemptRef.current = 0;
        useOfficeStore.getState().addToast({
          id: `toast-connected-${Date.now()}`,
          type: 'success',
          title: 'Connected',
          message: 'WebSocket connected to server',
        });
      };

      ws.onmessage = (event) => {
        let data: DashboardEvent;
        try { data = JSON.parse(event.data); } catch { return; }
        try { handleEvent(data); } catch (err) {
          console.error('[WS] Event handling error:', err);
        }
      };

      ws.onclose = () => {
        wsRef.current = null;
        scheduleReconnect();
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch {
      scheduleReconnect();
    }
  }, [handleEvent, scheduleReconnect]);

  // Keep connectRef in sync to break circular dependency
  connectRef.current = connect;

  const sendCommand = useCallback((command: string) => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) return;

    // Parse slash commands into proper DashboardCommand format
    const msg = parseCommand(command);
    wsRef.current.send(JSON.stringify(msg));
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      wsRef.current?.close();
    };
  }, [connect]);

  return { sendCommand };
}

/**
 * Convert server init payload (arrays) to client store format (Records keyed by id).
 * Server sends: { agents: AgentRow[], tasks: TaskRow[], epics: EpicRow[] }
 * Store expects: { agents: Record<id, AgentState>, tasks: Record<id, TaskState>, epics: Record<id, EpicState> }
 */
function mapInitPayload(payload: Record<string, unknown>) {
  const result: Record<string, unknown> = {};

  const rawAgents = payload.agents;
  if (Array.isArray(rawAgents)) {
    const agents: Record<string, Record<string, unknown>> = {};
    for (const a of rawAgents) {
      if (a && typeof a === 'object' && 'id' in a) {
        const agent = a as Record<string, unknown>;
        agents[agent.id as string] = {
          id: agent.id,
          status: agent.status ?? 'idle',
          currentTask: null,
          bubble: null,
          domain: agent.domain ?? agent.id,
          // slot is omitted — auto-assigned by setInitialState
        };
      }
    }
    result.agents = agents;
  }

  const rawTasks = payload.tasks;
  if (Array.isArray(rawTasks)) {
    const tasks: Record<string, Record<string, unknown>> = {};
    for (const t of rawTasks) {
      if (t && typeof t === 'object' && 'id' in t) {
        const task = t as Record<string, unknown>;
        tasks[task.id as string] = {
          id: task.id,
          title: task.title ?? '',
          status: task.status ?? '',
          boardColumn: task.boardColumn ?? 'Backlog',
          assignedAgent: task.assignedAgent ?? null,
          epicId: task.epicId ?? null,
        };
      }
    }
    result.tasks = tasks;
  }

  const rawEpics = payload.epics;
  if (Array.isArray(rawEpics)) {
    const epics: Record<string, Record<string, unknown>> = {};
    for (const e of rawEpics) {
      if (e && typeof e === 'object' && 'id' in e) {
        const epic = e as Record<string, unknown>;
        epics[epic.id as string] = {
          id: epic.id,
          title: epic.title ?? '',
          progress: epic.progress ?? 0,
        };
      }
    }
    result.epics = epics;
  }

  return result;
}

/**
 * Parse user input into a DashboardCommand object that the server expects.
 * Slash commands: /pause [@agent], /resume [@agent], /retry <taskId>
 * Everything else is sent as user-input text to the Director.
 */
function parseCommand(input: string): Record<string, unknown> {
  const trimmed = input.trim();
  const parts = trimmed.split(/\s+/);
  const cmd = parts[0]?.toLowerCase();

  if (cmd === '/pause') {
    const target = parts[1]?.replace('@', '');
    if (target) {
      return { type: 'agent-pause', payload: { agentId: target } };
    }
    return { type: 'system-pause', payload: {} };
  }

  if (cmd === '/resume') {
    const target = parts[1]?.replace('@', '');
    if (target) {
      return { type: 'agent-resume', payload: { agentId: target } };
    }
    return { type: 'system-resume', payload: {} };
  }

  if (cmd === '/retry' && parts[1]) {
    return { type: 'task-retry', payload: { taskId: parts[1] } };
  }

  // Default: send as user-input text
  return { type: 'user-input', payload: { text: trimmed } };
}
