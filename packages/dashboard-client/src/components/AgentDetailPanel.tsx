import { motion, AnimatePresence } from 'framer-motion';
import { useOfficeStore } from '@/stores/office-store';

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
  reviewing: { label: 'REVIEWING', color: 'text-cyan-400' },
  waiting: { label: 'WAITING', color: 'text-orange-400' },
  error: { label: 'ERROR', color: 'text-red-400' },
};

export default function AgentDetailPanel() {
  const selectedAgent = useOfficeStore((s) => s.selectedAgent);
  const agents = useOfficeStore((s) => s.agents);
  const tasks = useOfficeStore((s) => s.tasks);
  const messages = useOfficeStore((s) => s.messages);
  const selectAgent = useOfficeStore((s) => s.selectAgent);

  const agent = selectedAgent ? agents[selectedAgent] : null;

  const agentTasks = agent
    ? Object.values(tasks).filter((t) => t.assignedAgent === agent.id)
    : [];

  const agentMessages = agent
    ? messages.filter((m) => m.from === agent.id).slice(0, 10)
    : [];

  const statusInfo = agent
    ? STATUS_LABELS[agent.status] ?? STATUS_LABELS.idle
    : STATUS_LABELS.idle;

  return (
    <AnimatePresence>
      {agent && (
        <motion.div
          initial={{ x: '100%' }}
          animate={{ x: 0 }}
          exit={{ x: '100%' }}
          transition={{ type: 'spring', stiffness: 300, damping: 30 }}
          className="absolute right-0 top-0 bottom-0 w-72 bg-[#16213e] border-l-2 border-[#0f3460] z-30 flex flex-col"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-3 py-3 border-b border-[#0f3460]">
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
          <div className="px-3 py-2 border-b border-[#0f3460]/50">
            <div className="flex items-center justify-between">
              <span className="font-pixel text-[6px] text-gray-500">STATUS</span>
              <span className={`font-pixel text-[7px] ${statusInfo.color}`}>
                {statusInfo.label}
              </span>
            </div>
            {agent.currentTask && (
              <div className="mt-2">
                <span className="font-pixel text-[6px] text-gray-500">CURRENT TASK</span>
                <div className="mt-1 px-2 py-1 bg-[#1a1a3e] border border-[#0f3460]">
                  <span className="font-pixel text-[6px] text-gray-300">
                    {agent.currentTask}
                  </span>
                </div>
              </div>
            )}
            {agent.bubble && (
              <div className="mt-2">
                <span className="font-pixel text-[6px] text-gray-500">BUBBLE</span>
                <div className="mt-1 px-2 py-1 bg-[#1a1a3e] border border-[#0f3460]">
                  <span className="font-pixel text-[6px] text-gray-300">
                    {agent.bubble.content}
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* Tasks */}
          <div className="px-3 py-2 border-b border-[#0f3460]/50">
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
                  <div
                    key={task.id}
                    className="flex items-center gap-1 px-1 py-0.5 bg-[#1a1a3e]"
                  >
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
                <div key={msg.id} className="px-1 py-0.5 border-b border-gray-800/30">
                  <span className="font-pixel text-[5px] text-gray-300 break-all">
                    {typeof msg.content === 'string'
                      ? msg.content.slice(0, 80)
                      : JSON.stringify(msg.content).slice(0, 80)}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Controls placeholder */}
          <div className="px-3 py-2 border-t border-[#0f3460] flex gap-2">
            <button className="pixel-btn text-[6px] flex-1">FOCUS</button>
            <button className="pixel-btn text-[6px] flex-1">RESTART</button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
