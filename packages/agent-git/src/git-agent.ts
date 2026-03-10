import * as fs from 'fs/promises';
import * as path from 'path';
import { execFile } from 'child_process';
import { promisify } from 'util';
import {
  BaseAgent,
  type AgentDependencies,
  type AgentConfig,
  type Task,
  type TaskResult,
} from '@agent/core';

const execFileAsync = promisify(execFile);

export interface GitAgentConfig {
  workDir: string; // base workspace directory
  githubToken?: string; // for git push authentication
}

export class GitAgent extends BaseAgent {
  private workDir: string;
  private githubToken: string | undefined;

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
    this.githubToken = gitAgentConfig.githubToken;
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

    try {
      await this.gitService.createBranch(branchName);
      console.log(`[GitAgent] Branch created: ${branchName}`);
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      // Branch already exists → treat as success
      if (msg.includes('Reference already exists') || msg.includes('already exists')) {
        console.log(`[GitAgent] Branch already exists: ${branchName}`);
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

  private async handleCommitTask(task: Task): Promise<TaskResult> {
    const epicId = task.epicId ?? 'unknown';
    const workDir = await this.getEpicWorkDir(epicId);
    const message = task.description || task.title;

    // git add → commit → push
    await this.git(workDir, 'add', '-A');
    const { stdout: statusOut } = await this.git(workDir, 'status', '--porcelain');
    if (!statusOut.trim()) {
      console.log(`[GitAgent] Nothing to commit for: ${task.title}`);
      return { success: true, data: { committed: false, reason: 'nothing-to-commit' }, artifacts: [] };
    }

    await this.git(workDir, 'commit', '-m', message);
    const branchName = `epic/${epicId}`;
    await this.git(workDir, 'push', 'origin', branchName);
    console.log(`[GitAgent] Committed and pushed: ${message}`);

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

  private async handlePRTask(task: Task): Promise<TaskResult> {
    const epicId = task.epicId ?? 'unknown';
    const branchName = `epic/${epicId}`;

    try {
      const prNumber = await this.gitService.createPR(
        task.title.replace('[GIT] ', ''),
        task.description,
        branchName,
        'main',
      );

      console.log(`[GitAgent] PR #${prNumber} created for ${epicId}`);
      return { success: true, data: { prNumber }, artifacts: [] };
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      // PR already exists for this branch → treat as non-fatal
      if (msg.includes('A pull request already exists')) {
        console.log(`[GitAgent] PR already exists for ${branchName}`);
        return { success: true, data: { alreadyExisted: true, branch: branchName }, artifacts: [] };
      }
      throw error;
    }
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

  // ========== Git CLI ==========

  private async git(cwd: string, ...args: string[]): Promise<{ stdout: string; stderr: string }> {
    const env = { ...process.env };

    // GITHUB_TOKEN 기반 HTTPS 인증 — git push 시 패스워드 프롬프트 방지
    if (this.githubToken) {
      env.GIT_ASKPASS = 'echo';
      env.GIT_TERMINAL_PROMPT = '0';
      // credential helper 대신 header로 토큰 주입
      return execFileAsync(
        'git',
        ['-c', `http.extraHeader=Authorization: Bearer ${this.githubToken}`, ...args],
        { cwd, env },
      );
    }

    return execFileAsync('git', args, { cwd, env });
  }
}
