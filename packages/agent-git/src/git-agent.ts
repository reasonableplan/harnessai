import * as fs from 'fs/promises';
import * as path from 'path';
import {
  BaseAgent,
  type AgentDependencies,
  type AgentConfig,
  type Task,
  type TaskResult,
} from '@agent/core';

export interface GitAgentConfig {
  workDir: string; // base workspace directory
}

export class GitAgent extends BaseAgent {
  private workDir: string;

  constructor(deps: AgentDependencies, gitAgentConfig: GitAgentConfig) {
    const config: AgentConfig = {
      id: 'git',
      domain: 'git',
      level: 2,
      claudeModel: 'claude-sonnet-4-20250514',
      maxTokens: 8192,
      temperature: 0.2,
      tokenBudget: 50_000,
    };
    super(config, deps);
    this.workDir = gitAgentConfig.workDir;
  }

  // ========== Task Execution ==========

  protected async executeTask(task: Task): Promise<TaskResult> {
    const taskType = this.detectTaskType(task);
    console.log(`[GitAgent] Executing ${taskType} task: ${task.title}`);

    try {
      switch (taskType) {
        case 'branch':
          return await this.handleBranchTask(task);
        case 'commit':
          return await this.handleCommitTask(task);
        case 'pr':
          return await this.handlePRTask(task);
        default:
          return {
            success: false,
            error: { message: `Unknown git task type: ${taskType}` },
            artifacts: [],
          };
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return {
        success: false,
        error: { message },
        artifacts: [],
      };
    }
  }

  // ========== Task Type Detection ==========

  private detectTaskType(task: Task): 'branch' | 'commit' | 'pr' | 'unknown' {
    const title = task.title.toLowerCase();
    if (title.includes('pr') || title.includes('pull request')) return 'pr';
    if (title.includes('branch')) return 'branch';
    if (title.includes('commit') || title.includes('커밋')) return 'commit';
    return 'unknown';
  }

  // ========== Branch Task ==========

  private async handleBranchTask(task: Task): Promise<TaskResult> {
    const branchName = this.extractBranchName(task);
    await this.gitService.createBranch(branchName);
    console.log(`[GitAgent] Branch created: ${branchName}`);

    return {
      success: true,
      data: { branchName },
      artifacts: [],
    };
  }

  // ========== Commit Task ==========
  // TODO(Phase 2): Integrate git CLI (clone, add, commit, push) via child_process

  private async handleCommitTask(task: Task): Promise<TaskResult> {
    console.log(`[GitAgent] Commit task acknowledged: ${task.title}`);

    // After commit, check if all commits for this epic are done → trigger PR
    if (task.epicId) {
      await this.checkAndTriggerPR(task.epicId);
    }

    return {
      success: true,
      data: { committed: true },
      artifacts: [],
    };
  }

  // ========== PR Task ==========

  private async handlePRTask(task: Task): Promise<TaskResult> {
    const epicId = task.epicId ?? 'unknown';
    const branchName = `epic/${epicId}`;
    const prNumber = await this.gitService.createPR(
      task.title.replace('[GIT] ', ''),
      task.description,
      branchName,
      'main',
    );

    console.log(`[GitAgent] PR #${prNumber} created for ${epicId}`);

    return {
      success: true,
      data: { prNumber },
      artifacts: [],
    };
  }

  // ========== Post-Completion ==========

  protected override async onTaskComplete(
    task: Task,
    result: TaskResult,
  ): Promise<void> {
    // Move issue to Done/Failed on Board
    if (task.githubIssueNumber) {
      const column = result.success ? 'Done' : 'Failed';
      await this.gitService.moveIssueToColumn(task.githubIssueNumber, column);
    }

    // Update DB
    await this.stateStore.updateTask(task.id, {
      status: result.success ? 'done' : 'failed',
      boardColumn: result.success ? 'Done' : 'Failed',
      completedAt: result.success ? new Date() : undefined,
    });

    // Publish review.request
    await super.onTaskComplete(task, result);
  }

  // ========== PR Auto-Trigger ==========

  private async checkAndTriggerPR(epicId: string): Promise<void> {
    const epicIssues = await this.gitService.getEpicIssues(epicId);

    const codeIssues = epicIssues.filter(
      (i) => !i.labels.some((l) => l.startsWith('type:commit') || l.startsWith('type:pr')),
    );
    const commitIssues = epicIssues.filter((i) =>
      i.labels.some((l) => l === 'type:commit'),
    );

    const allCodeDone = codeIssues.every((i) => i.column === 'Done');
    const allCommitsDone = commitIssues.every((i) => i.column === 'Done');
    const noPRExists = !epicIssues.some((i) =>
      i.labels.some((l) => l === 'type:pr'),
    );

    if (allCodeDone && allCommitsDone && noPRExists) {
      console.log(`[GitAgent] All commits done for epic ${epicId}, triggering PR`);

      await this.gitService.createIssue({
        title: `[GIT] Epic ${epicId} PR 생성`,
        body: `Epic ${epicId}의 모든 코드 작업이 완료되었습니다.\n\n자동 생성된 PR 요청입니다.`,
        labels: ['agent:git', 'type:pr', `epic:${epicId}`],
        dependencies: [],
      });
    }
  }

  // ========== Helpers ==========

  private extractBranchName(task: Task): string {
    const epicId = task.epicId ?? 'feature';
    return `epic/${epicId}`;
  }

  async getEpicWorkDir(epicId: string): Promise<string> {
    const epicDir = path.resolve(this.workDir, epicId);
    try {
      await fs.access(epicDir);
    } catch {
      await fs.mkdir(epicDir, { recursive: true });
    }
    return epicDir;
  }
}
