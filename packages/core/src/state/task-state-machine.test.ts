import { describe, it, expect } from 'vitest';
import { isValidTransition, assertValidTransition } from './task-state-machine.js';

describe('Task State Machine', () => {
  describe('isValidTransition', () => {
    // 정상 흐름: backlog → ready → in-progress → review → done
    it('allows happy path: backlog → ready → in-progress → review → done', () => {
      expect(isValidTransition('backlog', 'ready')).toBe(true);
      expect(isValidTransition('ready', 'in-progress')).toBe(true);
      expect(isValidTransition('in-progress', 'review')).toBe(true);
      expect(isValidTransition('review', 'done')).toBe(true);
    });

    // 같은 상태는 idempotent (항상 허용)
    it('allows same-state transitions (idempotent)', () => {
      expect(isValidTransition('ready', 'ready')).toBe(true);
      expect(isValidTransition('done', 'done')).toBe(true);
      expect(isValidTransition('in-progress', 'in-progress')).toBe(true);
    });

    // 리뷰 거절 → ready (재시도)
    it('allows review → ready (retry after rejection)', () => {
      expect(isValidTransition('review', 'ready')).toBe(true);
    });

    // 실패 → ready (재시도)
    it('allows failed → ready (retry)', () => {
      expect(isValidTransition('failed', 'ready')).toBe(true);
    });

    // in-progress → failed
    it('allows in-progress → failed', () => {
      expect(isValidTransition('in-progress', 'failed')).toBe(true);
    });

    // in-progress → ready (Board sync rollback)
    it('allows in-progress → ready (claim rollback)', () => {
      expect(isValidTransition('in-progress', 'ready')).toBe(true);
    });

    // done은 terminal — 전환 불가
    it('rejects transitions from done', () => {
      expect(isValidTransition('done', 'backlog')).toBe(false);
      expect(isValidTransition('done', 'ready')).toBe(false);
      expect(isValidTransition('done', 'in-progress')).toBe(false);
    });

    // 역방향 비허용
    it('rejects backlog → in-progress (must go through ready)', () => {
      expect(isValidTransition('backlog', 'in-progress')).toBe(false);
    });

    it('rejects ready → review (must go through in-progress)', () => {
      expect(isValidTransition('ready', 'review')).toBe(false);
    });

    it('rejects ready → done (must go through review)', () => {
      expect(isValidTransition('ready', 'done')).toBe(false);
    });
  });

  describe('assertValidTransition', () => {
    it('throws on invalid transition with descriptive message', () => {
      expect(() => assertValidTransition('done', 'backlog')).toThrow(
        'Invalid task status transition: "done" → "backlog"',
      );
    });

    it('does not throw on valid transition', () => {
      expect(() => assertValidTransition('backlog', 'ready')).not.toThrow();
    });
  });
});
