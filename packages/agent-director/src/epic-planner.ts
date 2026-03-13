import type { IStateStore, IGitService, IMessageBus } from '@agent/core';
import { MESSAGE_TYPES, createLogger, boardThenDb } from '@agent/core';

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
    const traceId = crypto.randomUUID();
    log.info({ title: action.title, taskCount, traceId }, 'Planning epic');

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
    // 순방향 참조 해결을 위한 pending 목록 (taskId → [depTaskId])
    const pendingDeps: Array<{ taskId: string; depId: string }> = [];

    // Task를 Board에 Issue로 생성 + DB에 저장
    for (const taskSpec of action.tasks) {
      const depIssues = taskSpec.dependencies
        .map((depId) => idToIssue.get(depId))
        .filter((n): n is number => n != null);

      // 순방향 참조 감지 — 나중에 backfill
      for (const depId of taskSpec.dependencies) {
        if (!idToIssue.has(depId)) {
          pendingDeps.push({ taskId: taskSpec.id, depId });
        }
      }

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

    // 순방향 참조 backfill: 모든 task 생성 후 누락된 의존성 보충
    for (const { taskId, depId } of pendingDeps) {
      const depIssue = idToIssue.get(depId);
      if (depIssue == null) {
        log.warn({ taskId, depId }, 'Unknown dependency reference — not in this epic');
        continue;
      }
      const taskIssue = idToIssue.get(taskId);
      if (taskIssue == null) continue;
      const dbTaskId = `task-gh-${taskIssue}`;
      const existing = await this.stateStore.getTask(dbTaskId);
      if (existing) {
        const currentDeps = (existing.dependencies as string[]) ?? [];
        const depTaskId = `task-gh-${depIssue}`;
        if (!currentDeps.includes(depTaskId)) {
          await this.stateStore.updateTask(dbTaskId, {
            dependencies: [...currentDeps, depTaskId],
          });
          log.info({ taskId: dbTaskId, addedDep: depTaskId }, 'Backfilled forward dependency');
        }
      }
    }

    // 의존성 없는 Task를 Ready로 이동 (backfill 이후 DB 기준으로 판별)
    let readyCount = 0;
    for (let i = 0; i < action.tasks.length; i++) {
      const issueNumber = issueNumbers[i];
      if (issueNumber === undefined) continue;
      const dbTaskId = `task-gh-${issueNumber}`;
      const taskRow = await this.stateStore.getTask(dbTaskId);
      const deps = (taskRow?.dependencies as string[]) ?? [];
      if (deps.length === 0) {
        await boardThenDb({
          issueNumber,
          targetColumn: 'Ready',
          fromColumn: 'Backlog',
          moveToColumn: (n, col) => this.gitService.moveIssueToColumn(n, col),
          updateDb: () => this.stateStore.updateTask(dbTaskId, {
            status: 'ready',
            boardColumn: 'Ready',
          }),
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
      payload: {
        epicId,
        title: action.title,
        total: action.tasks.length,
        done: 0,
        ready: readyCount,
      },
      traceId,
      timestamp: new Date(),
    });

    return `Epic "${action.title}" created with ${action.tasks.length} tasks (${readyCount} ready).`;
  }
}
