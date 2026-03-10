import type { IGitService, IStateStore, IMessageBus, BoardIssue, Message } from './types/index.js';

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
    console.log(`[BoardWatcher] Started (interval: ${this.pollIntervalMs}ms)`);
  }

  stop(): void {
    this.running = false;
    console.log('[BoardWatcher] Stopped');
  }

  private async pollLoop(): Promise<void> {
    while (this.running) {
      try {
        await this.sync();
      } catch (error) {
        console.error('[BoardWatcher] Sync error:', error);
      }
      await new Promise((r) => setTimeout(r, this.pollIntervalMs));
    }
  }

  /**
   * Single GraphQL call → detect changes → sync DB.
   */
  async sync(): Promise<void> {
    const allItems = await this.gitService.getAllProjectItems();
    const currentColumns = new Map<number, string>();

    for (const issue of allItems) {
      currentColumns.set(issue.issueNumber, issue.column);

      // Detect column change
      const prevColumn = this.previousColumns.get(issue.issueNumber);
      if (prevColumn && prevColumn !== issue.column) {
        await this.onColumnChange(issue, prevColumn, issue.column);
      }

      // Sync to DB
      await this.syncTaskFromIssue(issue);
    }

    this.previousColumns = currentColumns;
  }

  private async onColumnChange(
    issue: BoardIssue,
    fromColumn: string,
    toColumn: string,
  ): Promise<void> {
    console.log(
      `[BoardWatcher] Issue #${issue.issueNumber} moved: ${fromColumn} → ${toColumn}`,
    );

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

  private async syncTaskFromIssue(issue: BoardIssue): Promise<void> {
    const taskId = `task-gh-${issue.issueNumber}`;
    const existing = await this.stateStore.getTask(taskId);

    // Extract target agent from agent:X label
    const agentLabel = issue.labels.find((l) => l.startsWith('agent:'));
    const targetAgent = agentLabel?.replace('agent:', '') ?? null;

    if (existing) {
      await this.stateStore.updateTask(taskId, {
        boardColumn: issue.column,
        status: COLUMN_TO_STATUS[issue.column] ?? 'backlog',
        assignedAgent: targetAgent,
      });
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
        retryCount: 0,
      });
    }
  }
}
