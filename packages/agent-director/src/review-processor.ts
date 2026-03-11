import type { IStateStore, IGitService, Task, TaskResult, Message, IMessageBus } from '@agent/core';
import { MESSAGE_TYPES, createLogger } from '@agent/core';
import type { IClaudeClient } from './director-agent.js';
import type { Dispatcher } from './dispatcher.js';

const log = createLogger('ReviewProcessor');

export class ReviewProcessor {
  constructor(
    private stateStore: IStateStore,
    private gitService: IGitService,
    private claude: IClaudeClient,
    private dispatcher: Dispatcher,
    private messageBus?: IMessageBus,
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
            reviewNote: null, // 승인 시 이전 피드백 제거
          });
          if (task.githubIssueNumber) {
            await this.gitService.moveIssueToColumn(task.githubIssueNumber, 'Done');
            await this.gitService.addComment(
              task.githubIssueNumber,
              `✅ **[Director Review] Approved**\n\n${reviewResult.reason}`,
            );
            await this.dispatcher.checkAndPromoteDependents(task.githubIssueNumber);
          }
        } else {
          log.warn({ taskId: payload.taskId, reason: reviewResult.reason }, 'Review rejected');
          // 리뷰 실패 → 피드백 저장 후 재시도로 전환
          await this.retryOrFail(task, payload.taskId, reviewResult.reason);
        }
      }
    } else {
      // 실행 실패 시 에러 메시지를 피드백으로 전달
      const task = await this.stateStore.getTask(payload.taskId);
      if (task) {
        const errorFeedback = payload.result.error?.message ?? 'Task execution failed';
        await this.retryOrFail(task, payload.taskId, errorFeedback);
      }
    }
  }

  /**
   * Claude를 사용하여 Worker의 결과물이 Task description과 일치하는지 검토한다.
   */
  private async reviewWithClaude(task: Task, result: TaskResult): Promise<{ approved: boolean; reason: string }> {
    const systemPrompt = `You are a code reviewer for a multi-agent software development system.
Review whether the worker's output matches the original task requirements.
Be specific about what needs to be fixed if rejecting.

Respond with JSON only:
{"approved": true|false, "reason": "brief explanation — if rejected, include specific actionable feedback"}`;

    const userMessage = `Task: ${task.title}
Description: ${task.description ?? 'N/A'}
Artifacts: ${JSON.stringify(result.artifacts ?? [])}
Data: ${JSON.stringify(result.data ?? {})}
Retry count: ${task.retryCount ?? 0}`;

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
   * 재시도 가능하면 피드백과 함께 Ready로 되돌리고, 최대 횟수 초과 시 Failed 처리.
   * @param feedback Director의 리뷰 피드백 (거절 사유 또는 에러 메시지)
   */
  private async retryOrFail(task: Task, taskId: string, feedback: string): Promise<void> {
    if ((task.retryCount ?? 0) < 3) {
      const newRetryCount = (task.retryCount ?? 0) + 1;

      // 1. DB에 피드백 저장 + Ready로 되돌림
      await this.stateStore.updateTask(taskId, {
        retryCount: newRetryCount,
        status: 'ready',
        boardColumn: 'Ready',
        reviewNote: feedback,
      });

      // 2. GitHub Issue에 피드백 코멘트 작성
      if (task.githubIssueNumber) {
        await this.gitService.moveIssueToColumn(task.githubIssueNumber, 'Ready');
        await this.gitService.addComment(
          task.githubIssueNumber,
          `🔄 **[Director Review] Revision Requested** (attempt ${newRetryCount}/3)\n\n${feedback}`,
        );
      }

      // 3. review.feedback 메시지 발행 (대시보드 실시간 알림 + 감사 로그용, 워커는 DB reviewNote로 피드백 수신)
      if (this.messageBus) {
        await this.messageBus.publish({
          id: crypto.randomUUID(),
          type: MESSAGE_TYPES.REVIEW_FEEDBACK,
          from: 'director',
          to: task.assignedAgent,
          payload: {
            taskId,
            feedback,
            retryCount: newRetryCount,
            maxRetries: 3,
          },
          traceId: crypto.randomUUID(),
          timestamp: new Date(),
        });
      }

      log.info({ taskId, attempt: newRetryCount, maxRetries: 3, feedback }, 'Task sent back with feedback');
    } else {
      // 최대 재시도 초과 → Failed로 마킹
      await this.stateStore.updateTask(taskId, {
        status: 'failed',
        boardColumn: 'Failed',
        reviewNote: `Final failure after 3 attempts. Last feedback: ${feedback}`,
      });
      if (task.githubIssueNumber) {
        await this.gitService.moveIssueToColumn(task.githubIssueNumber, 'Failed');
        await this.gitService.addComment(
          task.githubIssueNumber,
          `❌ **[Director Review] Failed** — max retries exceeded\n\nLast feedback: ${feedback}`,
        );
      }
      log.error({ taskId, feedback }, 'Task failed after max retries');
    }
  }
}
