import { createLogger } from '../logging/logger.js';

const log = createLogger('BoardThenDb');

export interface BoardThenDbOptions {
  /** GitHub issue number. If null, Board move is skipped (DB-only operation). */
  issueNumber: number | null;
  /** Target Board column (e.g. 'Ready', 'Done'). */
  targetColumn: string;
  /** Current Board column for rollback (e.g. 'Backlog', 'Review'). */
  fromColumn: string;
  /** Function to move issue on the Board. */
  moveToColumn: (issueNumber: number, column: string) => Promise<void>;
  /** Function to update the DB after Board move succeeds. */
  updateDb: () => Promise<void>;
}

/**
 * Board-first DB update with compensation.
 *
 * 1. Move issue on GitHub Board to targetColumn
 * 2. Update DB
 * 3. If DB fails, roll back Board to fromColumn
 *
 * If issueNumber is null, skips Board operations (DB-only).
 * Board failure prevents DB update (no compensation needed).
 * DB failure triggers Board rollback (best-effort compensation).
 */
export async function boardThenDb(opts: BoardThenDbOptions): Promise<void> {
  const { issueNumber, targetColumn, fromColumn, moveToColumn, updateDb } = opts;
  let boardMoved = false;

  // Step 1: Board move (if applicable)
  if (issueNumber != null && issueNumber > 0) {
    await moveToColumn(issueNumber, targetColumn);
    boardMoved = true;
  }

  // Step 2: DB update
  try {
    await updateDb();
  } catch (dbError) {
    // Step 3: Compensate — roll back Board if it was moved
    if (boardMoved && issueNumber != null) {
      try {
        await moveToColumn(issueNumber, fromColumn);
        log.info(
          { issueNumber, from: targetColumn, to: fromColumn },
          'Board rolled back after DB failure',
        );
      } catch (rollbackError) {
        log.error(
          { issueNumber, rollbackErr: rollbackError instanceof Error ? rollbackError.message : rollbackError },
          'Board rollback also failed — manual intervention may be needed',
        );
      }
    }
    throw dbError;
  }
}
