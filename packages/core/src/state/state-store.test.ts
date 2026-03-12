import { describe, it, expect, vi, beforeEach } from 'vitest';
import { StateStore } from './state-store.js';

// Mock Database
function createMockDb() {
  const mockChain = {
    values: vi.fn().mockReturnThis(),
    onConflictDoUpdate: vi.fn().mockResolvedValue(undefined),
    set: vi.fn().mockReturnThis(),
    where: vi.fn().mockResolvedValue([]),
    from: vi.fn().mockReturnThis(),
  };

  return {
    insert: vi.fn().mockReturnValue(mockChain),
    select: vi.fn().mockReturnValue(mockChain),
    update: vi.fn().mockReturnValue(mockChain),
    _chain: mockChain,
  };
}

describe('StateStore', () => {
  let store: StateStore;
  let mockDb: ReturnType<typeof createMockDb>;

  beforeEach(() => {
    mockDb = createMockDb();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    store = new StateStore(mockDb as any);
  });

  describe('Agent operations', () => {
    it('registerAgent inserts agent', async () => {
      await store.registerAgent({
        id: 'git',
        domain: 'git',
        level: 2,
        status: 'idle',
      });
      expect(mockDb.insert).toHaveBeenCalled();
      expect(mockDb._chain.values).toHaveBeenCalledWith(
        expect.objectContaining({ id: 'git', domain: 'git' }),
      );
    });

    it('getAgent returns null when not found', async () => {
      mockDb._chain.where.mockResolvedValueOnce([]);
      const result = await store.getAgent('nonexistent');
      expect(result).toBeNull();
    });

    it('getAgent returns agent row when found', async () => {
      const agentRow = { id: 'git', domain: 'git', level: 2, status: 'idle' };
      mockDb._chain.where.mockResolvedValueOnce([agentRow]);
      const result = await store.getAgent('git');
      expect(result).toEqual(agentRow);
    });

    it('updateAgentStatus calls update', async () => {
      await store.updateAgentStatus('git', 'busy');
      expect(mockDb.update).toHaveBeenCalled();
      expect(mockDb._chain.set).toHaveBeenCalledWith({ status: 'busy' });
    });

    it('updateHeartbeat updates timestamp', async () => {
      await store.updateHeartbeat('git');
      expect(mockDb.update).toHaveBeenCalled();
      expect(mockDb._chain.set).toHaveBeenCalledWith(
        expect.objectContaining({ lastHeartbeat: expect.any(Date) }),
      );
    });
  });

  describe('Task operations', () => {
    it('createTask inserts task', async () => {
      await store.createTask({
        id: 'task-001',
        title: 'Test task',
        boardColumn: 'Backlog',
        priority: 3,
        retryCount: 0,
      });
      expect(mockDb.insert).toHaveBeenCalled();
    });

    it('getTask returns null when not found', async () => {
      mockDb._chain.where.mockResolvedValueOnce([]);
      const result = await store.getTask('nonexistent');
      expect(result).toBeNull();
    });

    it('updateTask calls update with partial', async () => {
      await store.updateTask('task-001', { status: 'done', boardColumn: 'Done' });
      expect(mockDb.update).toHaveBeenCalled();
      expect(mockDb._chain.set).toHaveBeenCalledWith(
        expect.objectContaining({ status: 'done', boardColumn: 'Done' }),
      );
    });

    it('getReadyTasksForAgent queries by column and agent', async () => {
      mockDb._chain.where.mockResolvedValueOnce([]);
      const result = await store.getReadyTasksForAgent('git');
      expect(result).toEqual([]);
      expect(mockDb.select).toHaveBeenCalled();
    });

    it('claimTask returns true when row was updated (rowCount > 0)', async () => {
      mockDb._chain.where.mockResolvedValueOnce({ rowCount: 1 });
      const result = await store.claimTask('task-001');
      expect(result).toBe(true);
      expect(mockDb.update).toHaveBeenCalled();
      expect(mockDb._chain.set).toHaveBeenCalledWith(
        expect.objectContaining({ boardColumn: 'In Progress', status: 'in-progress' }),
      );
    });

    it('claimTask returns false when row was not updated (rowCount 0)', async () => {
      mockDb._chain.where.mockResolvedValueOnce({ rowCount: 0 });
      const result = await store.claimTask('task-already-taken');
      expect(result).toBe(false);
    });
  });

  describe('Epic operations', () => {
    it('createEpic inserts epic', async () => {
      await store.createEpic({ id: 'epic-001', title: 'Test epic' });
      expect(mockDb.insert).toHaveBeenCalled();
    });

    it('getEpic returns null when not found', async () => {
      mockDb._chain.where.mockResolvedValueOnce([]);
      const result = await store.getEpic('nonexistent');
      expect(result).toBeNull();
    });
  });

  describe('Message operations', () => {
    it('saveMessage inserts message row', async () => {
      await store.saveMessage({
        id: 'msg-001',
        type: 'board.move',
        from: 'git',
        to: null,
        payload: { test: true },
        traceId: 'trace-001',
        timestamp: new Date(),
      });
      expect(mockDb.insert).toHaveBeenCalled();
      expect(mockDb._chain.values).toHaveBeenCalledWith(
        expect.objectContaining({
          id: 'msg-001',
          type: 'board.move',
          fromAgent: 'git',
          toAgent: null,
        }),
      );
    });
  });

  describe('Artifact operations', () => {
    it('saveArtifact inserts artifact', async () => {
      await store.saveArtifact({
        taskId: 'task-001',
        filePath: 'src/index.ts',
        contentHash: 'abc123',
        createdBy: 'git',
      });
      expect(mockDb.insert).toHaveBeenCalled();
    });
  });
});
