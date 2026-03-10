import type { IStateStore, IGitService, Task, TaskResult, Message } from '@agent/core';
import { createLogger } from '@agent/core';

const log = createLogger('ReviewProcessor');
import type { IClaudeClient } from './director-agent.js';
import type { Dispatcher } from './dispatcher.js';

export class ReviewProcessor {
  constructor(
    private stateStore: IStateStore,
    private gitService: IGitService,
    private claude: IClaudeClient,
    private dispatcher: Dispatcher,
  ) {}

  async onReviewRequest(msg: Message): Promise<void> {
    const payload = msg.payload as { taskId: string; result: TaskResult };
    log.info({ taskId: payload.taskId, success: payload.result.success }, 'Review request');

    if (payload.result.success) {
      // LLM 기반 리뷰: artifacts가 task description과 일치하는지 검토
      const task = await this.stateStore.getTask(payload.taskId);
      if (task) {
        const reviewResult = await this.reviewWithClaude(task, payload.result);
        if (reviewResult.approved) {
          log.info({ taskId: payload.taskId, reason: reviewResult.reason }, 'Task approved');
          // Done으로 이동 + 후속 의존성 체인 트리거
          await this.stateStore.updateTask(payload.taskId, {
            status: 'done',
            boardColumn: 'Done',
          });
          if (task.githubIssueNumber) {
            await this.gitService.moveIssueToColumn(task.githubIssueNumber, 'Done');
            await this.dispatcher.checkAndPromoteDependents(task.githubIssueNumber);
          }
        } else {
          log.warn({ taskId: payload.taskId, reason: reviewResult.reason }, 'Review rejected');
          // 리뷰 실패 → 재시도로 전환
          await this.retryOrFail(task, payload.taskId);
        }
      }
    } else {
      // 실패 시 재시도 횟수 체크
      const task = await this.stateStore.getTask(payload.taskId);
      if (task) {
        await this.retryOrFail(task, payload.taskId);
      }
    }
  }

  /**
   * Claude를 사용하여 Worker의 결과물이 Task description과 일치하는지 검토한다.
   */
  private async reviewWithClaude(task: Task, result: TaskResult): Promise<{ approved: boolean; reason: string }> {
    const systemPrompt = `You are a code reviewer for a multi-agent software development system.
Review whether the worker's output matches the original task requirements.

Respond with JSON only:
{"approved": true|false, "reason": "brief explanation"}`;

    const userMessage = `Task: ${task.title}
Description: ${task.description ?? 'N/A'}
Artifacts: ${JSON.stringify(result.artifacts ?? [])}
Data: ${JSON.stringify(result.data ?? {})}`;

    try {
      const { data } = await this.claude.chatJSON<{ approved: boolean; reason: string }>(systemPrompt, userMessage);
      return data;
    } catch (error) {
      // 리뷰 실패 시 자동 승인 (리뷰 불가가 작업을 차단하면 안 됨)
      log.warn({ err: error instanceof Error ? error.message : error }, 'Review Claude call failed, auto-approving');
      return { approved: true, reason: 'auto-approved (review unavailable)' };
    }
  }

  /**
   * 재시도 가능하면 Ready로 되돌리고, 최대 횟수 초과 시 에러 로그.
   */
  private async retryOrFail(task: Task, taskId: string): Promise<void> {
    if ((task.retryCount ?? 0) < 3) {
      await this.stateStore.updateTask(taskId, {
        retryCount: (task.retryCount ?? 0) + 1,
        status: 'ready',
        boardColumn: 'Ready',
      });
      if (task.githubIssueNumber) {
        await this.gitService.moveIssueToColumn(task.githubIssueNumber, 'Ready');
      }
      log.info({ taskId, attempt: (task.retryCount ?? 0) + 1, maxRetries: 3 }, 'Retrying task');
    } else {
      // 최대 재시도 초과 → Failed로 마킹
      await this.stateStore.updateTask(taskId, {
        status: 'failed',
        boardColumn: 'Failed',
      });
      if (task.githubIssueNumber) {
        await this.gitService.moveIssueToColumn(task.githubIssueNumber, 'Failed');
      }
      log.error({ taskId }, 'Task failed after max retries');
    }
  }
}
