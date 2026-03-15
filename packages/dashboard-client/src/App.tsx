import { useEffect, useCallback, useState } from 'react';
import { useWebSocket } from '@/hooks/use-websocket';
import { useOfficeStore } from '@/stores/office-store';
import SystemStatusBar from '@/components/SystemStatusBar';
import OfficeScene from '@/components/OfficeScene';
import ActivityLog from '@/components/ActivityLog';
import TokenUsagePanel from '@/components/TokenUsagePanel';
import StatsPanel from '@/components/StatsPanel';
import CommandBar from '@/components/CommandBar';
import AgentDetailPanel from '@/components/AgentDetailPanel';
import AgentSettingsModal from '@/components/AgentSettingsModal';
import CharacterSelectModal from '@/components/CharacterSelectModal';
import BoardExpandedView from '@/components/BoardExpandedView';
import ToastContainer from '@/components/ToastContainer';

type SidePanel = 'activity' | 'tokens' | 'stats';

export default function App() {
  const { sendCommand } = useWebSocket();
  const updateAgent = useOfficeStore((s) => s.updateAgent);
  const addMessage = useOfficeStore((s) => s.addMessage);
  const updateTokenUsage = useOfficeStore((s) => s.updateTokenUsage);
  const selectedAgent = useOfficeStore((s) => s.selectedAgent);
  const [sidePanel, setSidePanel] = useState<SidePanel>('activity');

  // Demo mode: simulate agent activity when there is no real server
  const startDemo = useCallback(() => {
    const domains = ['director', 'git', 'frontend', 'backend', 'docs'] as const;
    // Extra agents to demo dynamic slot assignment
    const extraAgents = [
      { id: 'frontend-2', domain: 'frontend' },
      { id: 'backend-2', domain: 'backend' },
    ];
    // Weighted toward desk statuses; includes searching/delivering for variety
    const statuses = [
      'idle',
      'working', 'working', 'working',
      'thinking', 'thinking',
      'reviewing',
      'searching',
      'delivering',
    ] as const;
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

    // Spawn extra agents after a short delay
    let extraSpawned = false;

    const interval = setInterval(() => {
      // Spawn extra agents once after a few ticks
      if (!extraSpawned) {
        extraSpawned = true;
        for (const extra of extraAgents) {
          updateAgent(extra.id, { domain: extra.domain, status: 'idle' });
        }
      }

      // Pick a random agent (base + extra)
      const allIds = [...domains, ...extraAgents.map((e) => e.id)];
      const agentId = allIds[Math.floor(Math.random() * allIds.length)];
      const domain = extraAgents.find((e) => e.id === agentId)?.domain ?? agentId;
      const status = statuses[Math.floor(Math.random() * statuses.length)];

      const showBubble = Math.random() > 0.35;
      const bubble = showBubble ? bubbles[Math.floor(Math.random() * bubbles.length)] : null;

      updateAgent(agentId, {
        domain,
        status,
        bubble,
        currentTask: status === 'working' ? `task-${Math.floor(Math.random() * 100)}` : null,
      });

      // Simulate token usage
      if (status === 'working' || status === 'thinking' || status === 'reviewing') {
        const input = 500 + Math.floor(Math.random() * 2000);
        const output = 200 + Math.floor(Math.random() * 1500);
        updateTokenUsage(agentId, input, output);
      }

      if (showBubble && bubble) {
        addMessage({
          id: `demo-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
          type: 'agent.status',
          from: agentId,
          content: `${agentId} is ${status}: ${bubble.content}`,
          timestamp: new Date().toISOString(),
        });
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [updateAgent, addMessage, updateTokenUsage]);

  // Demo mode: only runs when no real server connection within 3 seconds
  useEffect(() => {
    let demoCleanup: (() => void) | null = null;
    let cancelled = false;

    const timeout = setTimeout(() => {
      // Check if a real server sent an init event (double-check to avoid race)
      if (!cancelled && !useOfficeStore.getState().connected) {
        demoCleanup = startDemo();
      }
    }, 3000);

    // Watch for connection to cancel demo if server connects after demo started
    const unsub = useOfficeStore.subscribe((state) => {
      if (state.connected && demoCleanup) {
        cancelled = true;
        demoCleanup();
        demoCleanup = null;
      }
    });

    return () => {
      cancelled = true;
      clearTimeout(timeout);
      demoCleanup?.();
      unsub();
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
    <div className="h-screen w-screen flex flex-col overflow-hidden bg-[#2D1B0E]">
      {/* Top: Status bar */}
      <SystemStatusBar />

      {/* Center area: Office + Side Panel */}
      <div className="flex-1 flex min-h-0 relative">
        {/* Main office scene */}
        <div className="flex-1 min-w-0">
          <OfficeScene />
        </div>

        {/* Right sidebar: agent detail OR tabs */}
        <div className="w-64 flex-shrink-0 hidden lg:flex flex-col">
          {selectedAgent ? (
            <AgentDetailPanel />
          ) : (
            <>
              {/* Tab buttons */}
              <div className="flex border-b-2 border-[#5C3A1A] bg-[#3A2410]">
                <button
                  onClick={() => setSidePanel('activity')}
                  className={`flex-1 py-1.5 font-pixel text-[6px] transition-colors ${
                    sidePanel === 'activity'
                      ? 'text-amber-300 bg-[#2D1B0E] border-b-2 border-amber-400'
                      : 'text-amber-800 hover:text-amber-500'
                  }`}
                >
                  ACTIVITY
                </button>
                <button
                  onClick={() => setSidePanel('tokens')}
                  className={`flex-1 py-1.5 font-pixel text-[6px] transition-colors ${
                    sidePanel === 'tokens'
                      ? 'text-amber-300 bg-[#2D1B0E] border-b-2 border-amber-400'
                      : 'text-amber-800 hover:text-amber-500'
                  }`}
                >
                  TOKENS
                </button>
                <button
                  onClick={() => setSidePanel('stats')}
                  className={`flex-1 py-1.5 font-pixel text-[6px] transition-colors ${
                    sidePanel === 'stats'
                      ? 'text-amber-300 bg-[#2D1B0E] border-b-2 border-amber-400'
                      : 'text-amber-800 hover:text-amber-500'
                  }`}
                >
                  STATS
                </button>
              </div>
              {/* Panel content */}
              <div className="flex-1 min-h-0">
                {sidePanel === 'activity' && <ActivityLog />}
                {sidePanel === 'tokens' && <TokenUsagePanel />}
                {sidePanel === 'stats' && <StatsPanel />}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Bottom: Command bar */}
      <CommandBar onSend={handleCommand} />

      {/* Overlays */}
      <BoardExpandedView />
      <AgentSettingsModal />
      <CharacterSelectModal />
      <ToastContainer />
    </div>
  );
}
