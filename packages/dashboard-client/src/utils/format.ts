/** Shared formatting utilities for dashboard components */

export function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export function formatDuration(ms: number | null): string {
  if (ms == null) return '-';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60_000).toFixed(1)}m`;
}

/** Agent domain → brand color mapping */
export const DOMAIN_COLORS: Record<string, string> = {
  director: '#FFD700',
  orchestration: '#FFD700', // server sends "orchestration" for director
  git: '#F05032',
  frontend: '#61DAFB',
  backend: '#68A063',
  docs: '#F7DF1E',
};
