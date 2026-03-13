import { describe, it, expect, vi, beforeEach } from 'vitest';
import { boardThenDb } from './board-then-db.js';

describe('boardThenDb', () => {
  const mockMoveToColumn = vi.fn();
  const mockUpdateDb = vi.fn();

  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('executes Board move then DB update in order', async () => {
    const order: string[] = [];
    mockMoveToColumn.mockImplementation(async () => { order.push('board'); });
    mockUpdateDb.mockImplementation(async () => { order.push('db'); });

    await boardThenDb({
      issueNumber: 10,
      targetColumn: 'Ready',
      fromColumn: 'Backlog',
      moveToColumn: mockMoveToColumn,
      updateDb: mockUpdateDb,
    });

    expect(order).toEqual(['board', 'db']);
    expect(mockMoveToColumn).toHaveBeenCalledWith(10, 'Ready');
  });

  it('skips Board move when issueNumber is null', async () => {
    await boardThenDb({
      issueNumber: null,
      targetColumn: 'Ready',
      fromColumn: 'Backlog',
      moveToColumn: mockMoveToColumn,
      updateDb: mockUpdateDb,
    });

    expect(mockMoveToColumn).not.toHaveBeenCalled();
    expect(mockUpdateDb).toHaveBeenCalled();
  });

  it('does not call DB when Board move fails', async () => {
    mockMoveToColumn.mockRejectedValue(new Error('GitHub API down'));

    await expect(boardThenDb({
      issueNumber: 10,
      targetColumn: 'Ready',
      fromColumn: 'Backlog',
      moveToColumn: mockMoveToColumn,
      updateDb: mockUpdateDb,
    })).rejects.toThrow('GitHub API down');

    expect(mockUpdateDb).not.toHaveBeenCalled();
  });

  it('rolls back Board when DB update fails', async () => {
    mockMoveToColumn.mockResolvedValue(undefined);
    mockUpdateDb.mockRejectedValue(new Error('DB constraint violation'));

    await expect(boardThenDb({
      issueNumber: 10,
      targetColumn: 'Done',
      fromColumn: 'Review',
      moveToColumn: mockMoveToColumn,
      updateDb: mockUpdateDb,
    })).rejects.toThrow('DB constraint violation');

    // Board should be rolled back to fromColumn
    expect(mockMoveToColumn).toHaveBeenCalledTimes(2);
    expect(mockMoveToColumn).toHaveBeenNthCalledWith(1, 10, 'Done');
    expect(mockMoveToColumn).toHaveBeenNthCalledWith(2, 10, 'Review');
  });

  it('throws original DB error even when rollback also fails', async () => {
    mockMoveToColumn
      .mockResolvedValueOnce(undefined)          // forward move succeeds
      .mockRejectedValueOnce(new Error('rollback failed')); // rollback fails
    mockUpdateDb.mockRejectedValue(new Error('DB error'));

    await expect(boardThenDb({
      issueNumber: 10,
      targetColumn: 'Ready',
      fromColumn: 'Backlog',
      moveToColumn: mockMoveToColumn,
      updateDb: mockUpdateDb,
    })).rejects.toThrow('DB error');

    // Rollback was attempted
    expect(mockMoveToColumn).toHaveBeenCalledTimes(2);
  });

  it('does not attempt rollback when issueNumber is null and DB fails', async () => {
    mockUpdateDb.mockRejectedValue(new Error('DB error'));

    await expect(boardThenDb({
      issueNumber: null,
      targetColumn: 'Ready',
      fromColumn: 'Backlog',
      moveToColumn: mockMoveToColumn,
      updateDb: mockUpdateDb,
    })).rejects.toThrow('DB error');

    // No rollback attempt since there was no Board move
    expect(mockMoveToColumn).not.toHaveBeenCalled();
  });
});
