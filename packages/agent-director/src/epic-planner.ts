import type { IStateStore, IGitService, IMessageBus } from '@agent/core';
import { MESSAGE_TYPES, createLogger } from '@agent/core';

const log = createLogger('EpicPlanner');
import type { CreateEpicAction } from './action-types.js';

export class EpicPlanner {
  constructor(
    private agentId: string,
    private stateStore: IStateStore,
    private gitService: IGitService,
    private messageBus: IMessageBus,
  ) {}

  async createEpic(action: CreateEpicAction): Promise<string> {
    const taskCount = action.tasks.length;
    log.info({ title: action.title, taskCount }, 'Planning epic');

    // Epic을 DB에 저장
    const epicId = crypto.randomUUID();
    await this.stateStore.createEpic({
      id: epicId,
      title: action.title,
      description: action.description,
      status: 'planning',
    });

    // Task id → GitHub issue number 매핑 (named id 기반 의존성 해석)
    const idToIssue = new Map<string, number>();
    const issueNumbers: number[] = [];

    // Task를 Board에 Issue로 생성 + DB에 저장
    for (const taskSpec of action.tasks) {
      // 의존성 검증: 아직 생성되지 않은 task id 참조 감지
      for (const depId of taskSpec.dependencies) {
        if (!idToIssue.has(depId)) {
          log.warn({ taskTitle: taskSpec.title, depId }, 'Unknown dependency reference — skipped');
        }
      }

      const depIssues = taskSpec.dependencies
        .map((depId) => idToIssue.get(depId))
        .filter((n): n is number => n != null);

      // 컨텍스트 공유: Epic 정보 + 선행 Task 결과물을 body에 포함
      const contextLines = [
        taskSpec.description,
        '',
        `**Epic:** ${action.title}`,
        `**Epic Description:** ${action.description}`,
      ];
      if (depIssues.length > 0) {
        contextLines.push(`**Depends on:** ${depIssues.map((n) => `#${n}`).join(', ')}`);
      }

      const issueNumber = await this.gitService.createIssue({
        title: taskSpec.title,
        body: contextLines.join('\n'),
        labels: [`agent:${taskSpec.agent}`, `epic:${epicId}`],
        dependencies: depIssues,
      });

      idToIssue.set(taskSpec.id, issueNumber);
      issueNumbers.push(issueNumber);

      const taskId = `task-gh-${issueNumber}`;
      await this.stateStore.createTask({
        id: taskId,
        epicId,
        title: taskSpec.title,
        description: taskSpec.description,
        assignedAgent: taskSpec.agent,
        status: 'backlog',
        githubIssueNumber: issueNumber,
        boardColumn: 'Backlog',
        priority: 3,
        complexity: 'medium',
        dependencies: depIssues.map((n) => `task-gh-${n}`),
        retryCount: 0,
      });

      log.info({ issueNumber, title: taskSpec.title, agent: taskSpec.agent }, 'Created issue');
    }

    // 의존성 없는 Task를 Ready로 이동
    let readyCount = 0;
    for (let i = 0; i < action.tasks.length; i++) {
      if (action.tasks[i].dependencies.length === 0) {
        await this.gitService.moveIssueToColumn(issueNumbers[i], 'Ready');
        await this.stateStore.updateTask(`task-gh-${issueNumbers[i]}`, {
          status: 'ready',
          boardColumn: 'Ready',
        });
        readyCount++;
      }
    }

    // Epic 상태 업데이트
    await this.stateStore.updateEpic(epicId, { status: 'active' });

    // Epic 진행률 브로드캐스트
    await this.messageBus.publish({
      id: crypto.randomUUID(),
      type: MESSAGE_TYPES.EPIC_PROGRESS,
      from: this.agentId,
      to: null,
      payload: { epicId, title: action.title, total: action.tasks.length, done: 0, ready: readyCount },
      traceId: crypto.randomUUID(),
      timestamp: new Date(),
    });

    return `Epic "${action.title}" created with ${action.tasks.length} tasks (${readyCount} ready).`;
  }
}
