import { useOfficeStore } from '@/stores/office-store';

const COLUMNS = [
  { key: 'Backlog', label: 'BKL', color: '#888888' },
  { key: 'Ready', label: 'RDY', color: '#4A90D9' },
  { key: 'In Progress', label: 'WIP', color: '#F5A623' },
  { key: 'Review', label: 'REV', color: '#9B59B6' },
  { key: 'Failed', label: 'FAL', color: '#E74C3C' },
  { key: 'Done', label: 'DON', color: '#2ECC71' },
];

const AGENT_CARD_COLORS: Record<string, string> = {
  git: '#F05032',
  frontend: '#61DAFB',
  backend: '#68A063',
  docs: '#F7DF1E',
  director: '#FFD700',
};

export default function WhiteboardMini() {
  const tasks = useOfficeStore((s) => s.tasks);
  const toggleBoard = useOfficeStore((s) => s.toggleBoard);

  const tasksByColumn: Record<string, typeof tasks[string][]> = {};
  for (const col of COLUMNS) {
    tasksByColumn[col.key] = [];
  }
  for (const task of Object.values(tasks)) {
    const col = task.boardColumn || 'Backlog';
    if (tasksByColumn[col]) {
      tasksByColumn[col].push(task);
    }
  }

  const boardX = 818;
  const boardY = 60;
  const colWidth = 22;
  const colGap = 3;

  return (
    <g
      onClick={toggleBoard}
      style={{ cursor: 'pointer' }}
    >
      {COLUMNS.map((col, ci) => {
        const cx = boardX + ci * (colWidth + colGap);
        const colTasks = tasksByColumn[col.key] ?? [];
        return (
          <g key={col.key}>
            {/* Column header */}
            <rect
              x={cx}
              y={boardY}
              width={colWidth}
              height={8}
              fill={col.color}
              opacity={0.7}
              shapeRendering="crispEdges"
            />
            <text
              x={cx + colWidth / 2}
              y={boardY + 6}
              textAnchor="middle"
              fill="#FFFFFF"
              fontSize={3}
              fontFamily="'Press Start 2P', monospace"
            >
              {col.label}
            </text>
            {/* Task cards */}
            {colTasks.slice(0, 6).map((task, ti) => (
              <rect
                key={task.id}
                x={cx + 2}
                y={boardY + 12 + ti * 8}
                width={colWidth - 4}
                height={6}
                rx={1}
                fill={AGENT_CARD_COLORS[task.assignedAgent ?? ''] ?? '#AAAAAA'}
                opacity={0.8}
                shapeRendering="crispEdges"
              />
            ))}
            {/* Overflow indicator */}
            {colTasks.length > 6 && (
              <text
                x={cx + colWidth / 2}
                y={boardY + 64}
                textAnchor="middle"
                fill="#666"
                fontSize={3}
                fontFamily="monospace"
              >
                +{colTasks.length - 6}
              </text>
            )}
          </g>
        );
      })}
    </g>
  );
}
