import { useEffect, useCallback } from 'react';
import { useWebSocket } from '@/hooks/use-websocket';
import { useOfficeStore } from '@/stores/office-store';
import SystemStatusBar from '@/components/SystemStatusBar';
import OfficeScene from '@/components/OfficeScene';
import ActivityLog from '@/components/ActivityLog';
import CommandBar from '@/components/CommandBar';
import AgentDetailPanel from '@/components/AgentDetailPanel';
import BoardExpandedView from '@/components/BoardExpandedView';
import ToastContainer from '@/components/ToastContainer';

export default function App() {
  const { sendCommand } = useWebSocket();
  const updateAgent = useOfficeStore((s) => s.updateAgent);
  const addMessage = useOfficeStore((s) => s.addMessage);

  // Demo mode: simulate agent activity when there is no real server
  const startDemo = useCallback(() => {
    const domains = ['director', 'git', 'frontend', 'backend', 'docs'] as const;
    const statuses = ['idle', 'working', 'thinking', 'searching', 'delivering', 'reviewing'] as const;
    const bubbles: Array<{ content: string; type: 'task' | 'thinking' | 'info' }> = [
      { content: 'Code fix!', type: 'task' },
      { content: 'API done!', type: 'info' },
      { content: 'Thinking...', type: 'thinking' },
      { content: 'PR ready!', type: 'task' },
      { content: 'Tests pass!', type: 'info' },
      { content: 'Docs updated', type: 'task' },
      { content: 'Reviewing...', type: 'thinking' },
      { content: 'Bug found!', type: 'task' },
      { content: 'Deploying...', type: 'info' },
      { content: 'Sprint done!', type: 'info' },
    ];

    const interval = setInterval(() => {
      const domain = domains[Math.floor(Math.random() * domains.length)];
      const status = statuses[Math.floor(Math.random() * statuses.length)];

      const showBubble = Math.random() > 0.4;
      const bubble = showBubble
        ? bubbles[Math.floor(Math.random() * bubbles.length)]
        : null;

      updateAgent(domain, {
        status,
        bubble,
        currentTask: status === 'working' ? `task-${Math.floor(Math.random() * 100)}` : null,
      });

      if (showBubble && bubble) {
        addMessage({
          id: `demo-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          type: 'agent.status',
          from: domain,
          content: `${domain} is ${status}: ${bubble.content}`,
          timestamp: new Date().toISOString(),
        });
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [updateAgent, addMessage]);

  useEffect(() => {
    // Start demo simulation after a short delay
    // In production, the WebSocket will provide real data
    const timeout = setTimeout(() => {
      const cleanup = startDemo();
      return cleanup;
    }, 2000);

    return () => clearTimeout(timeout);
  }, [startDemo]);

  const handleCommand = useCallback(
    (command: string) => {
      sendCommand(command);
      addMessage({
        id: `cmd-${Date.now()}`,
        type: 'info',
        from: 'user',
        content: command,
        timestamp: new Date().toISOString(),
      });
    },
    [sendCommand, addMessage],
  );

  return (
    <div className="h-screen w-screen flex flex-col overflow-hidden bg-[#1a1a2e]">
      {/* Top: Status bar */}
      <SystemStatusBar />

      {/* Center area: Office + Activity Log */}
      <div className="flex-1 flex min-h-0 relative">
        {/* Main office scene */}
        <div className="flex-1 min-w-0 relative">
          <OfficeScene />
          <AgentDetailPanel />
        </div>

        {/* Right sidebar: Activity Log */}
        <div className="w-64 flex-shrink-0 hidden lg:block">
          <ActivityLog />
        </div>
      </div>

      {/* Bottom: Command bar */}
      <CommandBar onSend={handleCommand} />

      {/* Overlays */}
      <BoardExpandedView />
      <ToastContainer />
    </div>
  );
}
