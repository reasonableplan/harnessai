import { useEffect, useRef, useCallback } from 'react';
import { useOfficeStore } from '@/stores/office-store';
import {
  agentStatusSchema,
  agentBubbleSchema,
  taskUpdateSchema,
  epicProgressSchema,
  messageSchema,
  tokenUsageSchema,
  agentConfigSchema,
  toastSchema,
  defaultFallbackSchema,
  initPayloadSchema,
} from './ws-event-schemas';

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
      case 'init': {
        setInitialState(mapInitPayload(payload));
        break;
      }

      case 'agent.status': {
        const result = agentStatusSchema.safeParse(payload);
        if (!result.success) {
          if (import.meta.env.DEV) console.warn('[WS] agent.status parse failed', result.error);
          break;
        }
        updateAgent(result.data.agentId, {
          status: result.data.status,
          ...(result.data.task != null ? { currentTask: result.data.task } : {}),
        });
        break;
      }

      case 'agent.bubble': {
        const result = agentBubbleSchema.safeParse(payload);
        if (!result.success) {
          if (import.meta.env.DEV) console.warn('[WS] agent.bubble parse failed', result.error);
          break;
        }
        updateAgent(result.data.agentId, { bubble: result.data.bubble });
        break;
      }

      case 'task.update': {
        const result = taskUpdateSchema.safeParse(payload);
        if (!result.success) {
          if (import.meta.env.DEV) console.warn('[WS] task.update parse failed', result.error);
          break;
        }
        const { taskId, status, boardColumn, assignedAgent, title, epicId } = result.data;
        updateTask(taskId, {
          ...(status != null && { status }),
          ...(boardColumn != null && { boardColumn }),
          ...(assignedAgent !== undefined && { assignedAgent }),
          ...(title != null && { title }),
          ...(epicId !== undefined && { epicId }),
        });
        break;
      }

      case 'epic.progress': {
        const result = epicProgressSchema.safeParse(payload);
        if (!result.success) {
          if (import.meta.env.DEV) console.warn('[WS] epic.progress parse failed', result.error);
          break;
        }
        const { epicId, title, progress } = result.data;
        updateEpic(epicId, {
          ...(title != null && { title }),
          ...(progress != null && { progress }),
        });
        break;
      }

      case 'message': {
        const result = messageSchema.safeParse(payload);
        if (!result.success) {
          if (import.meta.env.DEV) console.warn('[WS] message parse failed', result.error);
          break;
        }
        addMessage({
          id: result.data.id ?? `msg-${Date.now()}`,
          type: result.data.type ?? 'info',
          from: result.data.from ?? 'system',
          content: result.data.content ?? '',
          timestamp: result.data.timestamp ?? new Date().toISOString(),
        });
        break;
      }

      case 'token.usage': {
        const result = tokenUsageSchema.safeParse(payload);
        if (!result.success) {
          if (import.meta.env.DEV) console.warn('[WS] token.usage parse failed', result.error);
          break;
        }
        const { updateTokenUsage } = useOfficeStore.getState();
        updateTokenUsage(result.data.agentId, result.data.inputTokens, result.data.outputTokens);
        break;
      }

      case 'agent.config': {
        const result = agentConfigSchema.safeParse(payload);
        if (!result.success) {
          if (import.meta.env.DEV) console.warn('[WS] agent.config parse failed', result.error);
          break;
        }
        const { setAgentConfig } = useOfficeStore.getState();
        setAgentConfig(
          result.data.agentId,
          result.data.config as Parameters<typeof setAgentConfig>[1],
        );
        break;
      }

      case 'toast': {
        const result = toastSchema.safeParse(payload);
        if (!result.success) {
          if (import.meta.env.DEV) console.warn('[WS] toast parse failed', result.error);
          break;
        }
        addToast({
          id: `toast-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          type: result.data.type,
          title: result.data.title,
          message: result.data.message,
        });
        break;
      }

      default: {
        const result = defaultFallbackSchema.safeParse(payload);
        addMessage({
          id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          type,
          from: result.success ? (result.data.from ?? 'system') : 'system',
          content: JSON.stringify(payload),
          timestamp: new Date().toISOString(),
        });
      }
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
    let wsUrl = import.meta.env.VITE_WS_URL ?? `${protocol}//${window.location.host}/ws`;

    // Append auth token as query parameter if configured
    const authToken = import.meta.env.VITE_DASHBOARD_AUTH_TOKEN;
    if (authToken) {
      const separator = wsUrl.includes('?') ? '&' : '?';
      wsUrl = `${wsUrl}${separator}token=${encodeURIComponent(authToken)}`;
    }

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
        try { data = JSON.parse(event.data); } catch {
          if (import.meta.env.DEV) console.warn('[WS] Failed to parse server message');
          return;
        }
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
    } catch (err) {
      if (import.meta.env.DEV) console.warn('[WS] Connection failed:', err);
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

  const parsed = initPayloadSchema.safeParse(payload);
  if (!parsed.success) {
    if (import.meta.env.DEV) console.warn('[WS] init payload parse failed', parsed.error);
    return result;
  }

  if (parsed.data.agents) {
    const agents: Record<string, Record<string, unknown>> = {};
    for (const a of parsed.data.agents) {
      agents[a.id] = {
        id: a.id,
        status: a.status,
        currentTask: null,
        bubble: null,
        domain: a.domain ?? a.id,
        // slot is omitted — auto-assigned by setInitialState
      };
    }
    result.agents = agents;
  }

  if (parsed.data.tasks) {
    const tasks: Record<string, Record<string, unknown>> = {};
    for (const t of parsed.data.tasks) {
      tasks[t.id] = {
        id: t.id,
        title: t.title,
        status: t.status,
        boardColumn: t.boardColumn,
        assignedAgent: t.assignedAgent,
        epicId: t.epicId,
      };
    }
    result.tasks = tasks;
  }

  if (parsed.data.epics) {
    const epics: Record<string, Record<string, unknown>> = {};
    for (const e of parsed.data.epics) {
      epics[e.id] = {
        id: e.id,
        title: e.title,
        progress: e.progress,
      };
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
