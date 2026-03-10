import {
  BaseAgent,
  type AgentDependencies,
  type AgentConfig,
  type Task,
  type TaskResult,
} from '@agent/core';
import { GitCli } from './git-cli.js';
import { WorkspaceManager } from './workspace-manager.js';
import { TaskHandlers, detectTaskType } from './task-handlers.js';

export interface GitAgentConfig {
  workDir: string; // base workspace directory
  githubToken?: string; // for git push authentication
}

export class GitAgent extends BaseAgent {
  private taskHandlers: TaskHandlers;
  private workspaceManager: WorkspaceManager;

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

    const gitCli = new GitCli(gitAgentConfig.githubToken);
    this.workspaceManager = new WorkspaceManager(gitAgentConfig.workDir, gitCli);
    this.taskHandlers = new TaskHandlers(deps.gitService, gitCli, this.workspaceManager);
  }

  // ========== Task Execution ==========

  protected async executeTask(task: Task): Promise<TaskResult> {
    const taskType = detectTaskType(task);
    this.log.info({ taskType, title: task.title }, 'Executing task');

    try {
      switch (taskType) {
        case 'branch':
          return await this.taskHandlers.handleBranchTask(task);
        case 'commit':
          return await this.taskHandlers.handleCommitTask(task);
        case 'pr':
          return await this.taskHandlers.handlePRTask(task);
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

  // ========== Post-Completion ==========

  protected override async onTaskComplete(
    task: Task,
    result: TaskResult,
  ): Promise<void> {
    // GitAgent은 Done/Failed로 직접 이동 (BaseAgent 기본은 Review/Failed)
    const column = result.success ? 'Done' : 'Failed';
    const status = result.success ? 'done' : 'failed';

    await this.stateStore.updateTask(task.id, {
      status,
      boardColumn: column,
    });

    if (task.githubIssueNumber) {
      await this.gitService.moveIssueToColumn(task.githubIssueNumber, column);
    }

    // review.request 발행 (BaseAgent.onTaskComplete의 DB/Board 중복 방지를 위해 직접 발행)
    await this.messageBus.publish({
      id: crypto.randomUUID(),
      type: 'review.request',
      from: this.id,
      to: null,
      payload: { taskId: task.id, result },
      traceId: crypto.randomUUID(),
      timestamp: new Date(),
    });
  }

  // ========== Delegated Methods (public API + test compatibility) ==========

  async getEpicWorkDir(epicId: string): Promise<string> {
    return this.workspaceManager.getEpicWorkDir(epicId);
  }

  async cleanupEpicWorkDir(epicId: string): Promise<void> {
    return this.workspaceManager.cleanupEpicWorkDir(epicId);
  }

  // Private helpers delegated to TaskHandlers (accessible via `(agent as any)` in tests)
  private extractBranchName(task: Task): string {
    return this.taskHandlers.extractBranchName(task);
  }

  private async checkAndTriggerPR(epicId: string): Promise<void> {
    return this.taskHandlers.checkAndTriggerPR(epicId);
  }
}
