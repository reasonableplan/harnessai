import type { TaskStatus } from '../types/index.js';

/**
 * 허용된 Task 상태 전환 맵.
 * key: 현재 상태, value: 전환 가능한 상태 목록.
 *
 * 흐름: backlog → ready → in-progress → review → done
 *       ↑                    ↓           ↓
 *       └── (retry) ──── ready ←── failed
 */
const VALID_TRANSITIONS: Record<TaskStatus, readonly TaskStatus[]> = {
  backlog: ['ready'],
  ready: ['in-progress', 'backlog'],
  'in-progress': ['review', 'failed', 'ready'], // ready: Board sync rollback
  review: ['done', 'ready', 'failed'], // ready: review rejection → retry
  failed: ['ready', 'backlog'], // ready: retry, backlog: manual reset
  done: [], // terminal state — no transitions allowed
};

/**
 * 상태 전환이 유효한지 검증한다.
 */
export function isValidTransition(from: TaskStatus, to: TaskStatus): boolean {
  if (from === to) return true; // 같은 상태는 no-op (idempotent)
  const allowed = VALID_TRANSITIONS[from];
  return allowed !== undefined && allowed.includes(to);
}

/**
 * 상태 전환이 유효하지 않으면 에러를 던진다.
 */
export function assertValidTransition(from: TaskStatus, to: TaskStatus): void {
  if (!isValidTransition(from, to)) {
    throw new Error(
      `Invalid task status transition: "${from}" → "${to}". ` +
        `Allowed from "${from}": [${VALID_TRANSITIONS[from]?.join(', ') ?? 'none'}]`,
    );
  }
}
