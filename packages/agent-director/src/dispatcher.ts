import type { IStateStore, IGitService, Message } from '@agent/core';
import { createLogger } from '@agent/core';
import type { IClaudeClient } from './director-agent.js';

const log = createLogger('Dispatcher');

export class Dispatcher {
  private claude: IClaudeClient | null = null;

  constructor(
    private stateStore: IStateStore,
    private gitService: IGitService,
  ) {}

  /** Claude 클라이언트를 설정한다 (Backlog 이슈 검토용). */
  setClaudeClient(claude: IClaudeClient): void {
    this.claude = claude;
  }

  async onBoardMove(msg: Message): Promise<void> {
    const payload = msg.payload as {
      issueNumber: number;
      title: string;
      fromColumn: string;
      toColumn: string;
      labels: string[];
    };

    // Task가 Done으로 이동했을 때, 후속 Task의 의존성을 확인하고 Ready로 승인
    if (payload.toColumn === 'Done') {
      await this.checkAndPromoteDependents(payload.issueNumber);
    }

    // 새 이슈가 Backlog에 도착했을 때 (에이전트가 만든 후속 이슈)
    if (payload.toColumn === 'Backlog' && payload.fromColumn === '') {
      await this.reviewBacklogIssue(payload);
    }
  }

  /**
   * Backlog에 새로 도착한 이슈를 검토한다.
   * - type:commit 이슈는 자동 승인 (Git Agent로 바로 전달)
   * - 기타 이슈는 Claude로 검토하여 approve/reject
   */
  async reviewBacklogIssue(payload: {
    issueNumber: number;
    title: string;
    labels: string[];
  }): Promise<void> {
    // type:commit (Git commit 요청)은 자동 승인
    if (payload.labels.includes('type:commit')) {
      await this.approveToReady(payload.issueNumber, payload.title, 'auto-approved (commit request)');
      return;
    }

    // Claude가 없으면 자동 승인
    if (!this.claude) {
      await this.approveToReady(payload.issueNumber, payload.title, 'auto-approved (no reviewer)');
      return;
    }

    // Claude로 이슈 검토
    try {
      const issue = await this.gitService.getIssue(payload.issueNumber);
      const { data } = await this.claude.chatJSON<{ approved: boolean; reason: string }>(
        `You are reviewing a follow-up issue created by a worker agent.
Decide if this issue should be approved for execution.
Reject if: the issue is duplicate, out of scope, or poorly defined.
Respond with JSON: {"approved": true|false, "reason": "brief explanation"}`,
        `Title: ${issue.title}\nBody: ${issue.body}\nLabels: ${issue.labels.join(', ')}`,
      );

      if (data.approved) {
        await this.approveToReady(payload.issueNumber, payload.title, data.reason);
      } else {
        log.info({ issueNumber: payload.issueNumber, reason: data.reason }, 'Backlog issue rejected');
        await this.gitService.addComment(
          payload.issueNumber,
          `**[Director]** Issue rejected: ${data.reason}`,
        );
      }
    } catch (error) {
      // 검토 실패 시 자동 승인 (작업을 차단하지 않음)
      log.warn({ err: error instanceof Error ? error.message : error }, 'Backlog review failed, auto-approving');
      await this.approveToReady(payload.issueNumber, payload.title, 'auto-approved (review error)');
    }
  }

  private async approveToReady(issueNumber: number, title: string, reason: string): Promise<void> {
    const taskId = `task-gh-${issueNumber}`;
    const task = await this.stateStore.getTask(taskId);
    if (task) {
      await this.stateStore.updateTask(taskId, { status: 'ready', boardColumn: 'Ready' });
    }
    await this.gitService.moveIssueToColumn(issueNumber, 'Ready');
    log.info({ issueNumber, title, reason }, 'Backlog issue approved → Ready');
  }

  /**
   * 완료된 Task의 후속 Task 중 모든 의존성이 충족된 것을 Ready로 승인한다.
   */
  async checkAndPromoteDependents(completedIssueNumber: number): Promise<void> {
    const completedTaskId = `task-gh-${completedIssueNumber}`;

    // DB에서 Backlog 상태의 모든 Task를 조회
    const backlogTasks = await this.stateStore.getTasksByColumn('Backlog');

    for (const task of backlogTasks) {
      try {
        const deps = (task.dependencies as string[]) ?? [];
        if (!deps.includes(completedTaskId)) continue;

        // 이 Task의 모든 의존성이 Done인지 확인
        let allDepsDone = true;
        for (const depId of deps) {
          const depTask = await this.stateStore.getTask(depId);
          if (!depTask || depTask.boardColumn !== 'Done') {
            allDepsDone = false;
            break;
          }
        }

        if (allDepsDone) {
          await this.stateStore.updateTask(task.id, {
            status: 'ready',
            boardColumn: 'Ready',
          });
          if (task.githubIssueNumber) {
            await this.gitService.moveIssueToColumn(task.githubIssueNumber, 'Ready');
          }
          log.info({ taskTitle: task.title }, 'Promoted to Ready (all deps done)');
        }
      } catch (error) {
        log.error({ err: error, taskId: task.id }, 'Failed to check/promote task');
      }
    }
  }
}
