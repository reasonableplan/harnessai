import { useOfficeStore } from '@/stores/office-store';

const DOMAIN_COLORS: Record<string, string> = {
  director: '#FFD700',
  git: '#F05032',
  frontend: '#61DAFB',
  backend: '#68A063',
  docs: '#F7DF1E',
};

const DOMAIN_LABELS: Record<string, string> = {
  director: 'Director',
  git: 'Git',
  frontend: 'Frontend',
  backend: 'Backend',
  docs: 'Docs',
};

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export default function TokenUsagePanel() {
  const tokenUsage = useOfficeStore((s) => s.tokenUsage);
  const tokenBudget = useOfficeStore((s) => s.tokenBudget);

  const totalUsed = Object.values(tokenUsage).reduce((sum, t) => sum + t.totalTokens, 0);
  const totalInput = Object.values(tokenUsage).reduce((sum, t) => sum + t.inputTokens, 0);
  const totalOutput = Object.values(tokenUsage).reduce((sum, t) => sum + t.outputTokens, 0);
  const remaining = Math.max(0, tokenBudget - totalUsed);
  const usedPercent = tokenBudget > 0 ? (totalUsed / tokenBudget) * 100 : 0;
  const remainPercent = 100 - usedPercent;

  const budgetColor = usedPercent > 90 ? '#FF4444' : usedPercent > 70 ? '#FFAA33' : '#44DD66';

  return (
    <div className="flex flex-col h-full bg-[#16213e] border-l-2 border-[#0f3460]">
      {/* Header */}
      <div className="px-3 py-2 border-b border-[#0f3460]">
        <span className="font-pixel text-[8px] text-cyan-300 pixel-text-shadow">
          TOKEN USAGE
        </span>
      </div>

      {/* Total Budget Bar */}
      <div className="px-3 py-3 border-b border-[#0f3460]/50">
        <div className="flex items-center justify-between mb-1">
          <span className="font-pixel text-[6px] text-gray-400">BUDGET</span>
          <span className="font-pixel text-[6px]" style={{ color: budgetColor }}>
            {usedPercent.toFixed(1)}% USED
          </span>
        </div>
        <div className="w-full h-3 bg-gray-800 pixel-border-light overflow-hidden">
          <div
            className="h-full transition-all duration-500"
            style={{
              width: `${Math.min(usedPercent, 100)}%`,
              background: `linear-gradient(90deg, #44DD66, ${budgetColor})`,
            }}
          />
        </div>
        <div className="flex items-center justify-between mt-1.5">
          <div>
            <span className="font-pixel text-[5px] text-gray-500">USED: </span>
            <span className="font-pixel text-[6px] text-gray-200">{formatTokens(totalUsed)}</span>
          </div>
          <div>
            <span className="font-pixel text-[5px] text-gray-500">LEFT: </span>
            <span className="font-pixel text-[6px]" style={{ color: budgetColor }}>
              {formatTokens(remaining)}
            </span>
          </div>
        </div>
        <div className="flex items-center justify-between mt-1">
          <div>
            <span className="font-pixel text-[5px] text-gray-500">TOTAL: </span>
            <span className="font-pixel text-[5px] text-gray-400">{formatTokens(tokenBudget)}</span>
          </div>
          <div>
            <span className="font-pixel text-[5px] text-gray-500">REMAIN: </span>
            <span className="font-pixel text-[5px]" style={{ color: budgetColor }}>
              {remainPercent.toFixed(1)}%
            </span>
          </div>
        </div>
      </div>

      {/* I/O Summary */}
      <div className="px-3 py-2 border-b border-[#0f3460]/50">
        <div className="flex items-center gap-3">
          <div>
            <span className="font-pixel text-[5px] text-blue-400">IN: </span>
            <span className="font-pixel text-[6px] text-gray-200">{formatTokens(totalInput)}</span>
          </div>
          <div>
            <span className="font-pixel text-[5px] text-orange-400">OUT: </span>
            <span className="font-pixel text-[6px] text-gray-200">{formatTokens(totalOutput)}</span>
          </div>
        </div>
      </div>

      {/* Per-Agent Usage */}
      <div className="flex-1 px-3 py-2 overflow-y-auto space-y-2">
        <span className="font-pixel text-[6px] text-gray-400">PER AGENT</span>

        {Object.entries(tokenUsage)
          .sort(([, a], [, b]) => b.totalTokens - a.totalTokens)
          .map(([agentId, usage]) => {
            const color = DOMAIN_COLORS[agentId] ?? '#888';
            const label = DOMAIN_LABELS[agentId] ?? agentId;
            const agentPercent = totalUsed > 0 ? (usage.totalTokens / totalUsed) * 100 : 0;
            const budgetShare = tokenBudget > 0 ? (usage.totalTokens / tokenBudget) * 100 : 0;

            return (
              <div key={agentId} className="bg-[#1a1a3e] p-2 border border-[#0f3460]/30">
                {/* Agent header */}
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-1.5">
                    <div className="w-2 h-2" style={{ backgroundColor: color }} />
                    <span className="font-pixel text-[6px] text-gray-200">{label}</span>
                  </div>
                  <span className="font-pixel text-[6px]" style={{ color }}>
                    {agentPercent.toFixed(1)}%
                  </span>
                </div>

                {/* Usage bar (relative to total) */}
                <div className="w-full h-2 bg-gray-800 overflow-hidden mb-1">
                  <div
                    className="h-full transition-all duration-300"
                    style={{
                      width: `${Math.min(agentPercent, 100)}%`,
                      backgroundColor: color,
                      opacity: 0.8,
                    }}
                  />
                </div>

                {/* Details */}
                <div className="flex items-center justify-between">
                  <span className="font-pixel text-[5px] text-gray-400">
                    {formatTokens(usage.totalTokens)}
                  </span>
                  <span className="font-pixel text-[4px] text-gray-500">
                    IN:{formatTokens(usage.inputTokens)} OUT:{formatTokens(usage.outputTokens)}
                  </span>
                </div>
                <div className="flex items-center justify-between mt-0.5">
                  <span className="font-pixel text-[4px] text-gray-500">
                    {usage.callCount} calls
                  </span>
                  <span className="font-pixel text-[4px] text-gray-500">
                    {budgetShare.toFixed(2)}% of budget
                  </span>
                </div>
              </div>
            );
          })}
      </div>

      {/* Legend */}
      <div className="px-3 py-2 border-t border-[#0f3460]">
        <div className="flex flex-wrap gap-2">
          {Object.entries(DOMAIN_COLORS).map(([id, color]) => (
            <div key={id} className="flex items-center gap-1">
              <div className="w-1.5 h-1.5" style={{ backgroundColor: color }} />
              <span className="font-pixel text-[4px] text-gray-500">
                {DOMAIN_LABELS[id] ?? id}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
