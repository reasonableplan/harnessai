import { useEffect, useRef, useCallback } from 'react';
import { useOfficeStore } from '@/stores/office-store';

interface DashboardEvent {
  type: string;
  payload: Record<string, unknown>;
}

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const reconnectAttemptRef = useRef(0);
  const {
    updateAgent,
    updateTask,
    updateEpic,
    addMessage,
    addToast,
    setInitialState,
  } = useOfficeStore();

  const connect = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl =
      import.meta.env.VITE_WS_URL ?? `${protocol}//${window.location.host}/ws`;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        reconnectAttemptRef.current = 0;
        addToast({
          id: `toast-connected-${Date.now()}`,
          type: 'success',
          title: 'Connected',
          message: 'WebSocket connected to server',
        });
      };

      ws.onmessage = (event) => {
        try {
          const data: DashboardEvent = JSON.parse(event.data);
          handleEvent(data);
        } catch {
          // ignore malformed messages
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
  }, []);

  const scheduleReconnect = useCallback(() => {
    const attempt = reconnectAttemptRef.current;
    const delay = Math.min(1000 * Math.pow(2, attempt), 30000);
    reconnectAttemptRef.current = attempt + 1;

    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    reconnectTimeoutRef.current = setTimeout(() => {
      connect();
    }, delay);
  }, [connect]);

  const handleEvent = useCallback(
    (event: DashboardEvent) => {
      const { type, payload } = event;
      switch (type) {
        case 'init':
          setInitialState(payload as Parameters<typeof setInitialState>[0]);
          break;

        case 'agent.status':
          if (payload.agentId && typeof payload.agentId === 'string') {
            updateAgent(payload.agentId, payload as Record<string, unknown>);
          }
          break;

        case 'agent.bubble':
          if (payload.agentId && typeof payload.agentId === 'string') {
            updateAgent(payload.agentId, {
              bubble: payload.bubble as { content: string; type: 'task' | 'thinking' | 'info' | 'error' } | null,
            });
          }
          break;

        case 'task.update':
          if (payload.taskId && typeof payload.taskId === 'string') {
            updateTask(payload.taskId, payload as Record<string, unknown>);
          }
          break;

        case 'board.move':
          if (payload.taskId && typeof payload.taskId === 'string') {
            updateTask(payload.taskId, {
              boardColumn: payload.toColumn as string,
            });
          }
          break;

        case 'epic.progress':
          if (payload.epicId && typeof payload.epicId === 'string') {
            updateEpic(payload.epicId, payload as Record<string, unknown>);
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

        case 'toast':
          addToast({
            id: `toast-${Date.now()}`,
            type: (payload.type as 'success' | 'error' | 'info' | 'warning') ?? 'info',
            title: (payload.title as string) ?? '',
            message: (payload.message as string) ?? '',
          });
          break;

        default:
          // Treat unknown events as messages for the activity log
          addMessage({
            id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
            type,
            from: (payload.from as string) ?? 'system',
            content: JSON.stringify(payload),
            timestamp: new Date().toISOString(),
          });
      }
    },
    [setInitialState, updateAgent, updateTask, updateEpic, addMessage, addToast],
  );

  const sendCommand = useCallback((command: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'command', payload: { command } }));
    }
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
