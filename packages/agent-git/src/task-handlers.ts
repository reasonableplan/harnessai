import type { Task, TaskResult, IGitService } from '@agent/core';
import { createLogger } from '@agent/core';

const log = createLogger('GitTaskHandlers');
import type { GitCli } from './git-cli.js';
import type { WorkspaceManager } from './workspace-manager.js';

export type GitTaskType = 'branch' | 'commit' | 'pr' | 'unknown';

/**
 * Task 타입을 판별한다.
 * 1순위: GitHub Issue labels (type:branch, type:commit, type:pr)
 * 2순위: title 문자열 매칭 (fallback)
 */
export function detectTaskType(task: Task): GitTaskType {
  // Labels 기반 (DirectorAgent가 붙이는 type:* labels)
  if (task.githubIssueNumber) {
    const labels = (task as { labels?: string[] }).labels;
    if (labels) {
      if (labels.some((l) => l === 'type:pr')) return 'pr';
      if (labels.some((l) => l === 'type:branch')) return 'branch';
      if (labels.some((l) => l === 'type:commit')) return 'commit';
    }
  }

  // Title 기반 (fallback)
  const title = task.title.toLowerCase();
  if (title.includes('pr') || title.includes('pull request')) return 'pr';
  if (title.includes('branch') || title.includes('브랜치')) return 'branch';
  if (title.includes('commit') || title.includes('커밋')) return 'commit';
  return 'unknown';
}

export class TaskHandlers {
  constructor(
    private gitService: IGitService,
    private gitCli: GitCli,
    private workspaceManager: WorkspaceManager,
  ) {}

  // ========== Branch Task ==========

  async handleBranchTask(task: Task): Promise<TaskResult> {
    if (task.reviewNote) {
      log.info({ reviewNote: task.reviewNote, attempt: task.retryCount + 1 }, 'Retrying with Director feedback');
    }

    const branchName = this.extractBranchName(task);

    try {
      await this.gitService.createBranch(branchName);
      log.info({ branchName }, 'Branch created');
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      // Branch already exists → treat as success
      if (msg.includes('Reference already exists') || msg.includes('already exists')) {
        log.info({ branchName }, 'Branch already exists');
        return { success: true, data: { branchName, alreadyExisted: true }, artifacts: [] };
      }
      throw error;
    }

    return {
      success: true,
      data: { branchName },
      artifacts: [],
    };
  }

  // ========== Commit Task ==========

  async handleCommitTask(task: Task): Promise<TaskResult> {
    if (task.reviewNote) {
      log.info({ reviewNote: task.reviewNote, attempt: task.retryCount + 1 }, 'Retrying with Director feedback');
    }

    const epicId = task.epicId ?? 'unknown';
    const workDir = await this.workspaceManager.getEpicWorkDir(epicId);
    const message = task.description || task.title;

    // artifacts가 지정되어 있으면 해당 파일만, 아니면 전체 add
    if (task.artifacts.length > 0) {
      for (const filePath of task.artifacts) {
        await this.gitCli.exec(workDir, 'add', filePath);
      }
    } else {
      await this.gitCli.exec(workDir, 'add', '-A');
    }
    const { stdout: statusOut } = await this.gitCli.exec(workDir, 'status', '--porcelain');
    if (!statusOut.trim()) {
      log.info({ title: task.title }, 'Nothing to commit');
      return { success: true, data: { committed: false, reason: 'nothing-to-commit' }, artifacts: [] };
    }

    await this.gitCli.exec(workDir, 'commit', '-m', message);
    const branchName = `epic/${epicId}`;
    await this.gitCli.exec(workDir, 'push', 'origin', branchName);
    log.info({ message }, 'Committed and pushed');

    // After commit, check if all commits for this epic are done → trigger PR
    if (task.epicId) {
      await this.checkAndTriggerPR(task.epicId);
    }

    return {
      success: true,
      data: { committed: true, branch: branchName },
      artifacts: [],
    };
  }

  // ========== PR Task ==========

  async handlePRTask(task: Task): Promise<TaskResult> {
    if (task.reviewNote) {
      log.info({ reviewNote: task.reviewNote, attempt: task.retryCount + 1 }, 'Retrying with Director feedback');
    }

    const epicId = task.epicId ?? 'unknown';
    const branchName = `epic/${epicId}`;

    // Director 피드백이 있으면 PR 설명에 반영
    const description = task.reviewNote
      ? `${task.description}\n\n---\n_Revised based on Director feedback: ${task.reviewNote}_`
      : task.description;

    try {
      const prNumber = await this.gitService.createPR(
        task.title.replace('[GIT] ', ''),
        description,
        branchName,
        'main',
      );

      log.info({ prNumber, epicId }, 'PR created');
      return { success: true, data: { prNumber }, artifacts: [] };
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      // PR already exists for this branch → treat as non-fatal
      if (msg.includes('A pull request already exists')) {
        log.info({ branchName }, 'PR already exists');
        return { success: true, data: { alreadyExisted: true, branch: branchName }, artifacts: [] };
      }
      throw error;
    }
  }

  // ========== PR Auto-Trigger ==========

  async checkAndTriggerPR(epicId: string): Promise<void> {
    const epicIssues = await this.gitService.getEpicIssues(epicId);

    const codeIssues = epicIssues.filter(
      (i) => !i.labels.some((l) => l.startsWith('type:commit') || l.startsWith('type:pr')),
    );
    const commitIssues = epicIssues.filter((i) =>
      i.labels.some((l) => l === 'type:commit'),
    );

    const allCodeDone = codeIssues.length > 0 && codeIssues.every((i) => i.column === 'Done');
    const allCommitsDone = commitIssues.length > 0 && commitIssues.every((i) => i.column === 'Done');
    const noPRExists = !epicIssues.some((i) =>
      i.labels.some((l) => l === 'type:pr'),
    );

    if (allCodeDone && allCommitsDone && noPRExists) {
      log.info({ epicId }, 'All commits done, triggering PR');

      await this.gitService.createIssue({
        title: `[GIT] Epic ${epicId} PR 생성`,
        body: `Epic ${epicId}의 모든 코드 작업이 완료되었습니다.\n\n자동 생성된 PR 요청입니다.`,
        labels: ['agent:git', 'type:pr', `epic:${epicId}`],
        dependencies: [],
      });
    }
  }

  // ========== Helpers ==========

  extractBranchName(task: Task): string {
    const epicId = task.epicId ?? 'feature';
    return `epic/${epicId}`;
  }
}
