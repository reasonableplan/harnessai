import type { IGitService, IStateStore, IMessageBus, BoardIssue, Message } from './types/index.js';
import { createLogger } from './logger.js';

const log = createLogger('BoardWatcher');

const COLUMN_TO_STATUS: Record<string, string> = {
  Backlog: 'backlog',
  Ready: 'ready',
  'In Progress': 'in-progress',
  Review: 'review',
  Failed: 'failed',
  Done: 'done',
};

/**
 * BoardWatcher is the single source of Board → DB synchronization.
 * One GraphQL call per cycle fetches all project items.
 * Agents read tasks from DB only — never call GitHub API for polling.
 */
export class BoardWatcher {
  private running = false;
  private syncing = false; // 동시 sync 방지 lock
  private previousColumns: Map<number, string> = new Map(); // issueNumber → column

  constructor(
    private gitService: IGitService,
    private stateStore: IStateStore,
    private messageBus: IMessageBus,
    private pollIntervalMs = 15_000,
  ) {}

  start(): void {
    if (this.running) return;
    this.running = true;
    this.pollLoop();
    log.info({ intervalMs: this.pollIntervalMs }, 'Started');
  }

  stop(): void {
    this.running = false;
    log.info('Stopped');
  }

  private async pollLoop(): Promise<void> {
    while (this.running) {
      try {
        await this.sync();
      } catch (error) {
        log.error({ err: error }, 'Sync error');
      }
      await new Promise((r) => setTimeout(r, this.pollIntervalMs));
    }
  }

  /**
   * Webhook 등 외부에서 즉시 동기화를 트리거할 수 있는 public 메서드.
   * pollLoop과 독립적으로 호출 가능.
   */
  async triggerSync(): Promise<void> {
    if (this.syncing) {
      log.debug('Sync already in progress, skipping triggered sync');
      return;
    }
    try {
      await this.sync();
    } catch (error) {
      log.error({ err: error }, 'Triggered sync error');
    }
  }

  /**
   * Single GraphQL call → detect changes → sync DB.
   * Diff-based: 변경된 이슈와 새 이슈만 DB 접근하여 대규모 프로젝트 대응.
   * syncing lock으로 동시 실행을 방지한다.
   */
  async sync(): Promise<void> {
    if (this.syncing) return;
    this.syncing = true;
    try {
      await this.syncInternal();
    } finally {
      this.syncing = false;
    }
  }

  private async syncInternal(): Promise<void> {
    const allItems = await this.gitService.getAllProjectItems();
    const currentColumns = new Map<number, string>();

    for (const issue of allItems) {
      currentColumns.set(issue.issueNumber, issue.column);

      const prevColumn = this.previousColumns.get(issue.issueNumber);
      const isNew = prevColumn === undefined;
      const isChanged = prevColumn !== undefined && prevColumn !== issue.column;

      try {
        // Detect column change
        if (isChanged) {
          await this.onColumnChange(issue, prevColumn, issue.column);
        }

        // Diff-based: 새 이슈이거나 컬럼이 변경된 경우에만 DB 동기화
        if (isNew || isChanged) {
          await this.syncTaskFromIssue(issue);
        }
      } catch (error) {
        log.error({ err: error, issueNumber: issue.issueNumber }, 'Failed to sync issue');
      }
    }

    // 삭제된 이슈 감지: previousColumns에는 있지만 currentColumns에는 없는 이슈
    if (this.previousColumns.size > 0) {
      for (const [issueNumber, column] of this.previousColumns) {
        if (!currentColumns.has(issueNumber)) {
          await this.onIssueRemoved(issueNumber, column);
        }
      }
    }

    this.previousColumns = currentColumns;
  }

  private async onColumnChange(
    issue: BoardIssue,
    fromColumn: string,
    toColumn: string,
  ): Promise<void> {
    log.info({ issueNumber: issue.issueNumber, fromColumn, toColumn }, 'Issue moved');

    const message: Message = {
      id: crypto.randomUUID(),
      type: 'board.move',
      from: 'board-watcher',
      to: null,
      payload: {
        issueNumber: issue.issueNumber,
        title: issue.title,
        fromColumn,
        toColumn,
        labels: issue.labels,
      },
      traceId: crypto.randomUUID(),
      timestamp: new Date(),
    };

    await this.messageBus.publish(message);
  }

  private async onIssueRemoved(issueNumber: number, lastColumn: string): Promise<void> {
    log.info({ issueNumber, lastColumn }, 'Issue removed from board');

    await this.messageBus.publish({
      id: crypto.randomUUID(),
      type: 'board.remove',
      from: 'board-watcher',
      to: null,
      payload: { issueNumber, lastColumn },
      traceId: crypto.randomUUID(),
      timestamp: new Date(),
    });
  }

  private async syncTaskFromIssue(issue: BoardIssue): Promise<void> {
    const taskId = `task-gh-${issue.issueNumber}`;
    const existing = await this.stateStore.getTask(taskId);

    // Extract target agent from agent:X label
    const agentLabel = issue.labels.find((l) => l.startsWith('agent:'));
    const targetAgent = agentLabel?.replace('agent:', '') ?? null;

    if (existing) {
      // Agent가 claimTask로 'in-progress'로 바꾼 상태를 Board가 아직 반영하지 않았을 때
      // Board 기준 'Ready'로 되돌리는 것을 방지 — DB가 더 최신이면 스킵
      const dbStatus = existing.status as string;
      const boardStatus = COLUMN_TO_STATUS[issue.column] ?? 'backlog';
      const STATUS_PRIORITY: Record<string, number> = {
        backlog: 0, ready: 1, 'in-progress': 2, review: 3, failed: 3, done: 4,
      };
      const dbPriority = STATUS_PRIORITY[dbStatus] ?? 0;
      const boardPriority = STATUS_PRIORITY[boardStatus] ?? 0;

      // Board가 DB보다 앞선(더 진행된) 상태이거나 같은 경우에만 업데이트
      if (boardPriority >= dbPriority) {
        await this.stateStore.updateTask(taskId, {
          boardColumn: issue.column,
          status: boardStatus,
          assignedAgent: targetAgent,
          labels: issue.labels,
        });
      }
    } else {
      await this.stateStore.createTask({
        id: taskId,
        epicId: issue.epicId,
        title: issue.title,
        description: issue.body,
        assignedAgent: targetAgent,
        status: COLUMN_TO_STATUS[issue.column] ?? 'backlog',
        githubIssueNumber: issue.issueNumber,
        boardColumn: issue.column,
        priority: 3,
        complexity: 'medium',
        dependencies: issue.dependencies.map((d) => `task-gh-${d}`),
        labels: issue.labels,
        retryCount: 0,
      });
    }
  }
}
