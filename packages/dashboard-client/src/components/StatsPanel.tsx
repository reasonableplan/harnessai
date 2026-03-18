import { useEffect, useState } from 'react';
import { useOfficeStore } from '@/stores/office-store';
import { formatDuration, DOMAIN_COLORS } from '@/utils/format';
import { apiGet } from '@/utils/api';
import HooksPanel from './HooksPanel';

interface SystemSummary {
  totalTasks: number;
  doneTasks: number;
  failedTasks: number;
  completionRate: number;
  agentStats: Array<{
    agentId: string;
    totalTasks: number;
    completedTasks: number;
    failedTasks: number;
    completionRate: number;
    avgDurationMs: number | null;
    totalRetries: number;
  }>;
}

export default function StatsPanel() {
  const agents = useOfficeStore((s) => s.agents);
  const [summary, setSummary] = useState<SystemSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchStats() {
      setLoading(true);
      try {
        const res = await apiGet('/api/stats/summary');
        if (!res.ok) {
          if (!cancelled) setError('Failed to load stats');
        } else if (!cancelled) {
          const data = await res.json();
          setSummary(data);
          setError(null);
        }
      } catch {
        if (!cancelled) setError('Failed to load stats');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchStats();
    const interval = setInterval(fetchStats, 30_000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  return (
    <div className="h-full overflow-y-auto bg-[#3A2410] p-2 space-y-3">
      <span className="font-pixel text-[7px] text-amber-300">SYSTEM STATS</span>

      {loading && !summary && (
        <span className="font-pixel text-[6px] text-gray-500">Loading...</span>
      )}

      {error && !loading && (
        <span className="font-pixel text-[6px] text-red-400">{error}</span>
      )}

      {summary && (
        <>
          {/* Overall */}
          <div className="bg-[#2D1B0E] p-2 border border-[#5C3A1A]">
            <span className="font-pixel text-[6px] text-gray-400">OVERVIEW</span>
            <div className="mt-1 grid grid-cols-3 gap-1">
              <div className="text-center">
                <div className="font-pixel text-[8px] text-green-400">{summary.doneTasks}</div>
                <div className="font-pixel text-[5px] text-gray-500">DONE</div>
              </div>
              <div className="text-center">
                <div className="font-pixel text-[8px] text-red-400">{summary.failedTasks}</div>
                <div className="font-pixel text-[5px] text-gray-500">FAILED</div>
              </div>
              <div className="text-center">
                <div className="font-pixel text-[8px] text-gray-300">{summary.totalTasks}</div>
                <div className="font-pixel text-[5px] text-gray-500">TOTAL</div>
              </div>
            </div>
            <div className="mt-2">
              <div className="flex justify-between">
                <span className="font-pixel text-[5px] text-gray-500">COMPLETION</span>
                <span className="font-pixel text-[5px] text-gray-300">
                  {(summary.completionRate * 100).toFixed(1)}%
                </span>
              </div>
              <div className="w-full h-2 bg-[#3A2410] mt-0.5">
                <div
                  className="h-full bg-green-500 transition-all duration-300"
                  style={{ width: `${Math.min(summary.completionRate * 100, 100)}%` }}
                />
              </div>
            </div>
          </div>

          {/* Per-agent stats */}
          <div>
            <span className="font-pixel text-[6px] text-gray-400">AGENT PERFORMANCE</span>
            <div className="mt-1 space-y-1.5">
              {summary.agentStats.map((stat) => {
                const color = DOMAIN_COLORS[agents[stat.agentId]?.domain ?? stat.agentId] ?? '#888';
                return (
                  <div key={stat.agentId} className="bg-[#2D1B0E] p-1.5 border border-[#5C3A1A]">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1">
                        <div className="w-2 h-2" style={{ backgroundColor: color }} />
                        <span className="font-pixel text-[6px] text-gray-200">{stat.agentId}</span>
                      </div>
                      <span className="font-pixel text-[5px] text-gray-400">
                        {stat.completedTasks}/{stat.totalTasks}
                      </span>
                    </div>
                    <div className="w-full h-1.5 bg-[#3A2410] mt-1">
                      <div
                        className="h-full transition-all duration-300"
                        style={{
                          width: `${Math.min(stat.completionRate * 100, 100)}%`,
                          backgroundColor: color,
                          opacity: 0.8,
                        }}
                      />
                    </div>
                    <div className="flex justify-between mt-0.5">
                      <span className="font-pixel text-[4px] text-gray-500">
                        avg: {formatDuration(stat.avgDurationMs)}
                      </span>
                      <span className="font-pixel text-[4px] text-gray-500">
                        retries: {stat.totalRetries}
                      </span>
                      {stat.failedTasks > 0 && (
                        <span className="font-pixel text-[4px] text-red-400">
                          {stat.failedTasks} failed
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}

      {/* Hooks section */}
      <HooksPanel />
    </div>
  );
}
