import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useOfficeStore } from '@/stores/office-store';
import type { AgentStatsState } from '@/stores/office-store';

const DOMAIN_COLORS: Record<string, string> = {
  director: '#FFD700',
  git: '#F05032',
  frontend: '#61DAFB',
  backend: '#68A063',
  docs: '#F7DF1E',
};

const DOMAIN_TITLES: Record<string, string> = {
  director: 'Director Agent',
  git: 'Git Agent',
  frontend: 'Frontend Agent',
  backend: 'Backend Agent',
  docs: 'Docs Agent',
};

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  idle: { label: 'IDLE', color: 'text-gray-400' },
  working: { label: 'WORKING', color: 'text-green-400' },
  thinking: { label: 'THINKING', color: 'text-yellow-400' },
  searching: { label: 'SEARCHING', color: 'text-blue-400' },
  delivering: { label: 'DELIVERING', color: 'text-purple-400' },
  reviewing: { label: 'REVIEWING', color: 'text-amber-400' },
  waiting: { label: 'WAITING', color: 'text-orange-400' },
  error: { label: 'ERROR', color: 'text-red-400' },
};

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function formatDuration(ms: number | null): string {
  if (ms == null) return '-';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60_000).toFixed(1)}m`;
}

export default function AgentDetailPanel() {
  const selectedAgent = useOfficeStore((s) => s.selectedAgent);
  const agents = useOfficeStore((s) => s.agents);
  const tasks = useOfficeStore((s) => s.tasks);
  const messages = useOfficeStore((s) => s.messages);
  const tokenUsage = useOfficeStore((s) => s.tokenUsage);
  const tokenBudget = useOfficeStore((s) => s.tokenBudget);
  const selectAgent = useOfficeStore((s) => s.selectAgent);
  const openSettingsModal = useOfficeStore((s) => s.openSettingsModal);

  const [stats, setStats] = useState<AgentStatsState | null>(null);

  useEffect(() => {
    if (!selectedAgent) {
      setStats(null);
      return;
    }
    let cancelled = false;
    const fetchStats = () => {
      const baseUrl = import.meta.env.VITE_API_URL ?? '';
      fetch(`${baseUrl}/api/agents/${selectedAgent}/stats`)
        .then((r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          return r.json();
        })
        .then((data) => {
          if (!cancelled && data.stats) setStats(data.stats);
        })
        .catch(() => { /* stats polling failure is non-critical */ });
    };
    fetchStats();
    const interval = setInterval(fetchStats, 30_000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [selectedAgent]);

  const agent = selectedAgent ? agents[selectedAgent] : null;

  const agentTasks = agent ? Object.values(tasks).filter((t) => t.assignedAgent === agent.id) : [];

  const agentMessages = agent ? messages.filter((m) => m.from === agent.id).slice(0, 10) : [];

  const statusInfo = agent
    ? (STATUS_LABELS[agent.status] ?? STATUS_LABELS.idle)
    : STATUS_LABELS.idle;

  const agentTokens = agent ? tokenUsage[agent.id] : null;
  const totalUsed = agent ? Object.values(tokenUsage).reduce((sum, t) => sum + t.totalTokens, 0) : 0;
  const agentPercent =
    agentTokens && totalUsed > 0 ? (agentTokens.totalTokens / totalUsed) * 100 : 0;
  const budgetPercent =
    agentTokens && tokenBudget > 0 ? (agentTokens.totalTokens / tokenBudget) * 100 : 0;

  return (
    <AnimatePresence>
      {agent && (
        <motion.div
          initial={{ x: '100%' }}
          animate={{ x: 0 }}
          exit={{ x: '100%' }}
          transition={{ type: 'spring', stiffness: 300, damping: 30 }}
          className="absolute right-0 top-0 bottom-0 w-72 bg-[#3A2410] border-l-2 border-[#5C3A1A] z-30 flex flex-col"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-3 py-3 border-b border-[#5C3A1A]">
            <div className="flex items-center gap-2">
              <div
                className="w-3 h-3"
                style={{ backgroundColor: DOMAIN_COLORS[agent.domain] ?? '#888' }}
              />
              <span className="font-pixel text-[8px] text-gray-100">
                {DOMAIN_TITLES[agent.domain] ?? agent.domain}
              </span>
            </div>
            <button
              onClick={() => selectAgent(null)}
              className="font-pixel text-[10px] text-gray-500 hover:text-gray-200 px-1"
            >
              X
            </button>
          </div>

          {/* Status */}
          <div className="px-3 py-2 border-b border-[#5C3A1A]/50">
            <div className="flex items-center justify-between">
              <span className="font-pixel text-[6px] text-gray-500">STATUS</span>
              <span className={`font-pixel text-[7px] ${statusInfo.color}`}>
                {statusInfo.label}
              </span>
            </div>
            {agent.currentTask && (
              <div className="mt-2">
                <span className="font-pixel text-[6px] text-gray-500">CURRENT TASK</span>
                <div className="mt-1 px-2 py-1 bg-[#2D1B0E] border border-[#5C3A1A]">
                  <span className="font-pixel text-[6px] text-gray-300">{agent.currentTask}</span>
                </div>
              </div>
            )}
            {agent.bubble && (
              <div className="mt-2">
                <span className="font-pixel text-[6px] text-gray-500">BUBBLE</span>
                <div className="mt-1 px-2 py-1 bg-[#2D1B0E] border border-[#5C3A1A]">
                  <span className="font-pixel text-[6px] text-gray-300">
                    {agent.bubble.content}
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* Token Usage */}
          {agentTokens && (
            <div className="px-3 py-2 border-b border-[#5C3A1A]/50">
              <span className="font-pixel text-[6px] text-gray-500">TOKEN USAGE</span>
              <div className="mt-1.5 space-y-1">
                {/* Total bar */}
                <div className="flex items-center justify-between">
                  <span className="font-pixel text-[5px] text-gray-400">TOTAL</span>
                  <span
                    className="font-pixel text-[6px]"
                    style={{ color: DOMAIN_COLORS[agent.domain] ?? '#888' }}
                  >
                    {formatTokens(agentTokens.totalTokens)}
                  </span>
                </div>
                <div className="w-full h-2 bg-[#3A2410] overflow-hidden">
                  <div
                    className="h-full transition-all duration-300"
                    style={{
                      width: `${Math.min(agentPercent, 100)}%`,
                      backgroundColor: DOMAIN_COLORS[agent.domain] ?? '#888',
                      opacity: 0.8,
                    }}
                  />
                </div>
                {/* I/O breakdown */}
                <div className="flex items-center gap-3">
                  <div>
                    <span className="font-pixel text-[5px] text-blue-400">IN: </span>
                    <span className="font-pixel text-[5px] text-gray-300">
                      {formatTokens(agentTokens.inputTokens)}
                    </span>
                  </div>
                  <div>
                    <span className="font-pixel text-[5px] text-orange-400">OUT: </span>
                    <span className="font-pixel text-[5px] text-gray-300">
                      {formatTokens(agentTokens.outputTokens)}
                    </span>
                  </div>
                </div>
                {/* Percentages */}
                <div className="flex items-center justify-between">
                  <span className="font-pixel text-[5px] text-gray-500">
                    {agentPercent.toFixed(1)}% of total
                  </span>
                  <span className="font-pixel text-[5px] text-gray-500">
                    {budgetPercent.toFixed(2)}% of budget
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="font-pixel text-[5px] text-gray-500">
                    {agentTokens.callCount} API calls
                  </span>
                  <span className="font-pixel text-[5px] text-gray-500">
                    ~
                    {agentTokens.callCount > 0
                      ? formatTokens(Math.round(agentTokens.totalTokens / agentTokens.callCount))
                      : '0'}
                    /call
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Agent Stats */}
          {stats && (
            <div className="px-3 py-2 border-b border-[#5C3A1A]/50">
              <span className="font-pixel text-[6px] text-gray-500">PERFORMANCE</span>
              <div className="mt-1 space-y-1">
                <div className="flex items-center justify-between">
                  <span className="font-pixel text-[5px] text-gray-400">COMPLETION</span>
                  <span className="font-pixel text-[5px] text-green-400">
                    {(stats.completionRate * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="w-full h-1.5 bg-[#3A2410]">
                  <div
                    className="h-full bg-green-500 transition-all duration-300"
                    style={{ width: `${Math.min(stats.completionRate * 100, 100)}%` }}
                  />
                </div>
                <div className="flex justify-between">
                  <span className="font-pixel text-[5px] text-gray-500">
                    {stats.completedTasks}/{stats.totalTasks} tasks
                  </span>
                  <span className="font-pixel text-[5px] text-gray-500">
                    avg: {formatDuration(stats.avgDurationMs)}
                  </span>
                </div>
                <div className="flex justify-between">
                  {stats.failedTasks > 0 && (
                    <span className="font-pixel text-[5px] text-red-400">
                      {stats.failedTasks} failed
                    </span>
                  )}
                  {stats.totalRetries > 0 && (
                    <span className="font-pixel text-[5px] text-yellow-400">
                      {stats.totalRetries} retries
                    </span>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Tasks */}
          <div className="px-3 py-2 border-b border-[#5C3A1A]/50">
            <span className="font-pixel text-[6px] text-gray-500">
              ASSIGNED TASKS ({agentTasks.length})
            </span>
            <div className="mt-1 space-y-1 max-h-32 overflow-y-auto">
              {agentTasks.length === 0 && (
                <span className="font-pixel text-[5px] text-gray-600">No tasks</span>
              )}
              {agentTasks.map((task) => {
                const colColor =
                  task.boardColumn === 'Done'
                    ? 'bg-green-600'
                    : task.boardColumn === 'In Progress'
                      ? 'bg-yellow-600'
                      : task.boardColumn === 'Failed'
                        ? 'bg-red-600'
                        : task.boardColumn === 'Review'
                          ? 'bg-purple-600'
                          : 'bg-gray-600';
                return (
                  <div key={task.id} className="flex items-center gap-1 px-1 py-0.5 bg-[#2D1B0E]">
                    <div className={`w-1.5 h-1.5 ${colColor} flex-shrink-0`} />
                    <span className="font-pixel text-[5px] text-gray-300 truncate">
                      {task.title || task.id}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Recent messages from this agent */}
          <div className="flex-1 px-3 py-2 overflow-y-auto">
            <span className="font-pixel text-[6px] text-gray-500">RECENT ACTIVITY</span>
            <div className="mt-1 space-y-1">
              {agentMessages.length === 0 && (
                <span className="font-pixel text-[5px] text-gray-600">No recent activity</span>
              )}
              {agentMessages.map((msg) => (
                <div key={msg.id} className="px-1 py-0.5 border-b border-[#3A2410]/30">
                  <span className="font-pixel text-[5px] text-gray-300 break-all">
                    {typeof msg.content === 'string'
                      ? msg.content.slice(0, 80)
                      : JSON.stringify(msg.content).slice(0, 80)}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Controls */}
          <div className="px-3 py-2 border-t border-[#5C3A1A] flex gap-2">
            <button className="pixel-btn text-[6px] flex-1">FOCUS</button>
            <button className="pixel-btn text-[6px] flex-1">RESTART</button>
            <button
              className="pixel-btn text-[6px] flex-1"
              onClick={() => agent && openSettingsModal(agent.id)}
            >
              SETTINGS
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
