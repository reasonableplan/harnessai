import type { IStateStore, IGitService, Message } from '@agent/core';
import { createLogger } from '@agent/core';

const log = createLogger('Dispatcher');

export class Dispatcher {
  constructor(
    private stateStore: IStateStore,
    private gitService: IGitService,
  ) {}

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
