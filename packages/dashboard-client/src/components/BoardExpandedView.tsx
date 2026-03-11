import { motion, AnimatePresence } from 'framer-motion';
import { useOfficeStore } from '@/stores/office-store';

const COLUMNS = [
  { key: 'Backlog', color: '#888888', headerBg: '#555555' },
  { key: 'Ready', color: '#4A90D9', headerBg: '#3A70B9' },
  { key: 'In Progress', color: '#F5A623', headerBg: '#D59013' },
  { key: 'Review', color: '#9B59B6', headerBg: '#7B3996' },
  { key: 'Failed', color: '#E74C3C', headerBg: '#C7342C' },
  { key: 'Done', color: '#2ECC71', headerBg: '#1EAC51' },
];

const AGENT_COLORS: Record<string, string> = {
  director: '#FFD700',
  git: '#F05032',
  frontend: '#61DAFB',
  backend: '#68A063',
  docs: '#F7DF1E',
};

export default function BoardExpandedView() {
  const boardExpanded = useOfficeStore((s) => s.boardExpanded);
  const toggleBoard = useOfficeStore((s) => s.toggleBoard);
  const tasks = useOfficeStore((s) => s.tasks);

  const tasksByColumn: Record<string, (typeof tasks)[string][]> = {};
  for (const col of COLUMNS) {
    tasksByColumn[col.key] = [];
  }
  for (const task of Object.values(tasks)) {
    const col = task.boardColumn || 'Backlog';
    if (tasksByColumn[col]) {
      tasksByColumn[col].push(task);
    } else {
      tasksByColumn[col] = [task];
    }
  }

  return (
    <AnimatePresence>
      {boardExpanded && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
          onClick={toggleBoard}
        >
          <motion.div
            initial={{ scale: 0.9, y: 20 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.9, y: 20 }}
            transition={{ type: 'spring', stiffness: 300, damping: 25 }}
            className="bg-[#1a1a2e] pixel-border p-4 w-[90vw] max-w-[1100px] h-[80vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between mb-3">
              <span className="font-pixel text-[10px] text-cyan-300 pixel-text-shadow">
                KANBAN BOARD
              </span>
              <button
                onClick={toggleBoard}
                className="pixel-btn text-[8px]"
              >
                CLOSE [X]
              </button>
            </div>

            {/* Board columns */}
            <div className="flex-1 flex gap-2 overflow-x-auto overflow-y-hidden min-h-0">
              {COLUMNS.map((col) => {
                const colTasks = tasksByColumn[col.key] ?? [];
                return (
                  <div
                    key={col.key}
                    className="flex-1 min-w-[140px] flex flex-col bg-[#16213e] border border-[#0f3460]"
                  >
                    {/* Column header */}
                    <div
                      className="px-2 py-1.5 flex items-center justify-between"
                      style={{ backgroundColor: col.headerBg }}
                    >
                      <span className="font-pixel text-[7px] text-white">
                        {col.key.toUpperCase()}
                      </span>
                      <span className="font-pixel text-[6px] text-white/70">
                        {colTasks.length}
                      </span>
                    </div>

                    {/* Cards */}
                    <div className="flex-1 overflow-y-auto p-1.5 space-y-1.5">
                      {colTasks.map((task) => {
                        const agentColor =
                          AGENT_COLORS[task.assignedAgent ?? ''] ?? '#666666';
                        return (
                          <div
                            key={task.id}
                            className="bg-[#1a1a3e] border border-[#333] p-1.5 hover:border-gray-500 transition-colors"
                          >
                            <div className="flex items-start gap-1">
                              <div
                                className="w-2 h-2 mt-0.5 flex-shrink-0"
                                style={{ backgroundColor: agentColor }}
                              />
                              <span className="font-pixel text-[5px] text-gray-200 leading-relaxed break-all">
                                {task.title || task.id}
                              </span>
                            </div>
                            {task.assignedAgent && (
                              <div className="mt-1 flex items-center gap-1">
                                <span
                                  className="font-pixel text-[4px] px-1 py-0.5"
                                  style={{
                                    backgroundColor: agentColor + '33',
                                    color: agentColor,
                                  }}
                                >
                                  {task.assignedAgent.toUpperCase()}
                                </span>
                              </div>
                            )}
                          </div>
                        );
                      })}
                      {colTasks.length === 0 && (
                        <div className="text-center py-4">
                          <span className="font-pixel text-[5px] text-gray-600">
                            Empty
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
