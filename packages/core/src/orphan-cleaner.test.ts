import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { OrphanCleaner } from './orphan-cleaner.js';

// ===== DB Mock =====
// OrphanCleaner uses two query patterns:
//   select().from(agents).where(...)  → returns agent rows
//   select().from(tasks).where(...)   → returns task rows
//   update(table).set({...}).where(eq(...))

function createMockDb() {
  // Each from() call returns a chainable { where } that resolves the mock data
  const fromResults: unknown[][] = [];
  let fromCallIndex = 0;

  const updateResult = {
    set: vi.fn().mockReturnThis(),
    where: vi.fn().mockResolvedValue(undefined),
  };

  const db = {
    select: vi.fn().mockImplementation(() => ({
      from: vi.fn().mockImplementation(() => ({
        where: vi.fn().mockImplementation(() => {
          return Promise.resolve(fromResults[fromCallIndex++] ?? []);
        }),
      })),
    })),
    update: vi.fn().mockReturnValue(updateResult),
    _updateResult: updateResult,
    /** Queue results for sequential select().from().where() calls */
    _queueSelectResults(...results: unknown[][]) {
      fromCallIndex = 0;
      fromResults.length = 0;
      fromResults.push(...results);
    },
  };

  return db;
}

// ===== Tests =====

describe('OrphanCleaner', () => {
  let db: ReturnType<typeof createMockDb>;
  let cleaner: OrphanCleaner;

  beforeEach(() => {
    db = createMockDb();
    cleaner = new OrphanCleaner(db as never, { heartbeatTimeoutMs: 60_000, intervalMs: 30_000 });
  });

  afterEach(() => {
    cleaner.stop();
  });

  it('returns 0 when no stale agents exist', async () => {
    db._queueSelectResults(
      [{ id: 'backend', status: 'idle', lastHeartbeat: new Date() }], // agents
      [], // in-progress tasks (won't be reached)
    );

    const restored = await cleaner.cleanup();
    expect(restored).toBe(0);
  });

  it('restores orphan tasks from stale agents to Ready', async () => {
    const staleHeartbeat = new Date(Date.now() - 120_000);

    db._queueSelectResults(
      [{ id: 'backend', status: 'idle', lastHeartbeat: staleHeartbeat }],
      [
        { id: 'task-1', title: 'API endpoint', assignedAgent: 'backend', boardColumn: 'In Progress' },
        { id: 'task-2', title: 'Other task', assignedAgent: 'frontend', boardColumn: 'In Progress' },
      ],
    );

    const restored = await cleaner.cleanup();

    expect(restored).toBe(1);
    expect(db.update).toHaveBeenCalled();
    expect(db._updateResult.set).toHaveBeenCalledWith(
      expect.objectContaining({ status: 'ready', boardColumn: 'Ready' }),
    );
    expect(db._updateResult.set).toHaveBeenCalledWith({ status: 'error' });
  });

  it('treats agents with no heartbeat as stale', async () => {
    db._queueSelectResults(
      [{ id: 'git', status: 'idle', lastHeartbeat: null }],
      [{ id: 'task-3', title: 'Branch task', assignedAgent: 'git', boardColumn: 'In Progress' }],
    );

    const restored = await cleaner.cleanup();
    expect(restored).toBe(1);
  });

  it('skips tasks assigned to healthy agents', async () => {
    db._queueSelectResults(
      [{ id: 'backend', status: 'busy', lastHeartbeat: new Date() }],
      [{ id: 'task-1', title: 'API', assignedAgent: 'backend', boardColumn: 'In Progress' }],
    );

    const restored = await cleaner.cleanup();
    expect(restored).toBe(0);
  });

  it('handles multiple stale agents at once', async () => {
    const staleHeartbeat = new Date(Date.now() - 120_000);

    db._queueSelectResults(
      [
        { id: 'backend', status: 'idle', lastHeartbeat: staleHeartbeat },
        { id: 'frontend', status: 'idle', lastHeartbeat: staleHeartbeat },
      ],
      [
        { id: 'task-1', title: 'API', assignedAgent: 'backend', boardColumn: 'In Progress' },
        { id: 'task-2', title: 'UI', assignedAgent: 'frontend', boardColumn: 'In Progress' },
        { id: 'task-3', title: 'Docs', assignedAgent: 'docs', boardColumn: 'In Progress' },
      ],
    );

    const restored = await cleaner.cleanup();
    expect(restored).toBe(2);
  });

  it('start/stop manages interval timer', () => {
    vi.useFakeTimers();

    cleaner.start();
    cleaner.start(); // idempotent

    cleaner.stop();
    cleaner.stop(); // idempotent

    vi.useRealTimers();
  });

  it('skips tasks with no assignedAgent', async () => {
    const staleHeartbeat = new Date(Date.now() - 120_000);

    db._queueSelectResults(
      [{ id: 'backend', status: 'idle', lastHeartbeat: staleHeartbeat }],
      [{ id: 'task-1', title: 'Unassigned', assignedAgent: null, boardColumn: 'In Progress' }],
    );

    const restored = await cleaner.cleanup();
    expect(restored).toBe(0);
  });
});
