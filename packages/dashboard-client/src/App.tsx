import { useEffect, useCallback, useState } from 'react';
import { useWebSocket } from '@/hooks/use-websocket';
import { useOfficeStore } from '@/stores/office-store';
import SystemStatusBar from '@/components/SystemStatusBar';
import OfficeScene from '@/components/OfficeScene';
import ActivityLog from '@/components/ActivityLog';
import TokenUsagePanel from '@/components/TokenUsagePanel';
import CommandBar from '@/components/CommandBar';
import AgentDetailPanel from '@/components/AgentDetailPanel';
import BoardExpandedView from '@/components/BoardExpandedView';
import ToastContainer from '@/components/ToastContainer';

type SidePanel = 'activity' | 'tokens';

export default function App() {
  const { sendCommand } = useWebSocket();
  const updateAgent = useOfficeStore((s) => s.updateAgent);
  const addMessage = useOfficeStore((s) => s.addMessage);
  const updateTokenUsage = useOfficeStore((s) => s.updateTokenUsage);
  const [sidePanel, setSidePanel] = useState<SidePanel>('activity');

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
      { content: 'Koffee?', type: 'info' },
      { content: 'Refactoring', type: 'task' },
    ];

    const interval = setInterval(() => {
      const domain = domains[Math.floor(Math.random() * domains.length)];
      const status = statuses[Math.floor(Math.random() * statuses.length)];

      const showBubble = Math.random() > 0.35;
      const bubble = showBubble
        ? bubbles[Math.floor(Math.random() * bubbles.length)]
        : null;

      updateAgent(domain, {
        status,
        bubble,
        currentTask: status === 'working' ? `task-${Math.floor(Math.random() * 100)}` : null,
      });

      // Simulate token usage
      if (status === 'working' || status === 'thinking' || status === 'reviewing') {
        const input = 500 + Math.floor(Math.random() * 2000);
        const output = 200 + Math.floor(Math.random() * 1500);
        updateTokenUsage(domain, input, output);
      }

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
  }, [updateAgent, addMessage, updateTokenUsage]);

  useEffect(() => {
    let demoCleanup: (() => void) | null = null;

    const timeout = setTimeout(() => {
      demoCleanup = startDemo();
    }, 2000);

    return () => {
      clearTimeout(timeout);
      demoCleanup?.();
    };
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

      {/* Center area: Office + Side Panel */}
      <div className="flex-1 flex min-h-0 relative">
        {/* Main office scene */}
        <div className="flex-1 min-w-0 relative">
          <OfficeScene />
          <AgentDetailPanel />
        </div>

        {/* Right sidebar with tab switch */}
        <div className="w-64 flex-shrink-0 hidden lg:flex flex-col">
          {/* Tab buttons */}
          <div className="flex border-b-2 border-[#0f3460] bg-[#16213e]">
            <button
              onClick={() => setSidePanel('activity')}
              className={`flex-1 py-1.5 font-pixel text-[6px] transition-colors ${
                sidePanel === 'activity'
                  ? 'text-cyan-300 bg-[#1a1a3e] border-b-2 border-cyan-400'
                  : 'text-gray-500 hover:text-gray-300'
              }`}
            >
              ACTIVITY
            </button>
            <button
              onClick={() => setSidePanel('tokens')}
              className={`flex-1 py-1.5 font-pixel text-[6px] transition-colors ${
                sidePanel === 'tokens'
                  ? 'text-cyan-300 bg-[#1a1a3e] border-b-2 border-cyan-400'
                  : 'text-gray-500 hover:text-gray-300'
              }`}
            >
              TOKENS
            </button>
          </div>
          {/* Panel content */}
          <div className="flex-1 min-h-0">
            {sidePanel === 'activity' ? <ActivityLog /> : <TokenUsagePanel />}
          </div>
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
