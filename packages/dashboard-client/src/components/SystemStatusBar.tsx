import { useEffect } from 'react';
import { useOfficeStore } from '@/stores/office-store';

function formatTime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

const COLUMN_COLORS: Record<string, string> = {
  Backlog: 'bg-gray-500',
  Ready: 'bg-blue-500',
  'In Progress': 'bg-yellow-500',
  Review: 'bg-purple-500',
  Failed: 'bg-red-500',
  Done: 'bg-green-500',
};

export default function SystemStatusBar() {
  const agents = useOfficeStore((s) => s.agents);
  const tasks = useOfficeStore((s) => s.tasks);
  const epics = useOfficeStore((s) => s.epics);
  const isPaused = useOfficeStore((s) => s.isPaused);
  const elapsedTime = useOfficeStore((s) => s.elapsedTime);
  const togglePause = useOfficeStore((s) => s.togglePause);
  const incrementTime = useOfficeStore((s) => s.incrementTime);
  const tokenUsage = useOfficeStore((s) => s.tokenUsage);
  const tokenBudget = useOfficeStore((s) => s.tokenBudget);

  useEffect(() => {
    if (isPaused) return;
    const interval = setInterval(() => incrementTime(), 1000);
    return () => clearInterval(interval);
  }, [isPaused, incrementTime]);

  const agentList = Object.values(agents);
  const activeCount = agentList.filter(
    (a) => a.status === 'working' || a.status === 'reviewing' || a.status === 'delivering',
  ).length;
  const errorCount = agentList.filter((a) => a.status === 'error').length;
  const idleCount = agentList.length - activeCount - errorCount;

  const taskList = Object.values(tasks);
  const columnCounts: Record<string, number> = {};
  for (const t of taskList) {
    const col = t.boardColumn || 'Backlog';
    columnCounts[col] = (columnCounts[col] ?? 0) + 1;
  }

  const epicList = Object.values(epics);
  const currentEpic = epicList.length > 0 ? epicList[epicList.length - 1] : null;

  // Token summary
  const totalUsed = Object.values(tokenUsage).reduce((sum, t) => sum + t.totalTokens, 0);
  const usedPercent = tokenBudget > 0 ? (totalUsed / tokenBudget) * 100 : 0;
  const tokenColor = usedPercent > 90 ? 'text-red-400' : usedPercent > 70 ? 'text-yellow-400' : 'text-green-400';

  return (
    <div className="flex items-center gap-4 px-4 py-2 bg-[#16213e] border-b-2 border-[#0f3460] font-pixel text-[8px] select-none">
      {/* Epic info */}
      <div className="flex items-center gap-2 min-w-0 flex-shrink">
        <span className="text-agent-director">EPIC:</span>
        <span className="text-gray-300 truncate max-w-[160px]">
          {currentEpic ? currentEpic.title : 'No active epic'}
        </span>
        {currentEpic && (
          <div className="flex items-center gap-1">
            <div className="w-20 h-2 bg-gray-700 pixel-border-light">
              <div
                className="h-full bg-agent-director transition-all duration-500"
                style={{ width: `${Math.round(currentEpic.progress * 100)}%` }}
              />
            </div>
            <span className="text-agent-director">
              {Math.round(currentEpic.progress * 100)}%
            </span>
          </div>
        )}
      </div>

      <div className="w-px h-5 bg-gray-600" />

      {/* Agent counts */}
      <div className="flex items-center gap-3">
        <span className="text-gray-400">AGENTS:</span>
        <span className="text-green-400">{activeCount} active</span>
        <span className="text-gray-400">{idleCount} idle</span>
        {errorCount > 0 && <span className="text-red-400">{errorCount} error</span>}
      </div>

      <div className="w-px h-5 bg-gray-600" />

      {/* Board summary */}
      <div className="flex items-center gap-2">
        <span className="text-gray-400">BOARD:</span>
        {Object.entries(COLUMN_COLORS).map(([col, colorClass]) => {
          const count = columnCounts[col] ?? 0;
          if (count === 0) return null;
          return (
            <div key={col} className="flex items-center gap-0.5">
              <div className={`w-2 h-2 ${colorClass}`} />
              <span className="text-gray-300">{count}</span>
            </div>
          );
        })}
        {taskList.length === 0 && <span className="text-gray-500">empty</span>}
      </div>

      <div className="w-px h-5 bg-gray-600" />

      {/* Token usage summary */}
      <div className="flex items-center gap-2">
        <span className="text-gray-400">TOKENS:</span>
        <span className={tokenColor}>{formatTokens(totalUsed)}</span>
        <span className="text-gray-600">/</span>
        <span className="text-gray-400">{formatTokens(tokenBudget)}</span>
        <div className="w-16 h-2 bg-gray-700 overflow-hidden">
          <div
            className="h-full transition-all duration-500"
            style={{
              width: `${Math.min(usedPercent, 100)}%`,
              backgroundColor: usedPercent > 90 ? '#FF4444' : usedPercent > 70 ? '#FFAA33' : '#44DD66',
            }}
          />
        </div>
        <span className={`${tokenColor} text-[7px]`}>{usedPercent.toFixed(1)}%</span>
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Timer */}
      <div className="flex items-center gap-2">
        <span className="text-gray-400">TIME:</span>
        <span className="text-cyan-300 tabular-nums">{formatTime(elapsedTime)}</span>
      </div>

      {/* Pause/Resume */}
      <button
        onClick={togglePause}
        className="pixel-btn text-[7px] px-2 py-1"
        title={isPaused ? 'Resume' : 'Pause'}
      >
        {isPaused ? 'RESUME' : 'PAUSE'}
      </button>
    </div>
  );
}
