import { BaseAgent, type AgentDependencies } from './base-agent.js';
import { FileWriter } from '../io/file-writer.js';
import { CommitRequester } from '../llm/commit-requester.js';
import { FollowUpCreator } from '../io/follow-up-creator.js';
import type { AgentConfig, Task, TaskResult, FollowUp } from '../types/index.js';
import type { BaseCodeGenerator } from '../llm/base-code-generator.js';

export interface WorkerAgentDeps {
  generator: BaseCodeGenerator;
  commitPrefix: string;
  workDir: string;
  /**
   * 도메인 간 follow-up 이슈 생성 함수.
   * 없으면 follow-up 생략.
   */
  createFollowUps?: (task: Task, summary: string, writtenFiles: string[]) => FollowUp[];
}

export abstract class BaseWorkerAgent extends BaseAgent {
  private generator: BaseCodeGenerator;
  private commitRequester: CommitRequester;
  private followUpCreator: FollowUpCreator;
  private fileWriter: FileWriter;
  private createFollowUpsFn?: WorkerAgentDeps['createFollowUps'];

  constructor(config: AgentConfig, deps: AgentDependencies, workerDeps: WorkerAgentDeps) {
    super(config, deps);
    this.generator = workerDeps.generator;
    this.commitRequester = new CommitRequester(deps.gitService, workerDeps.commitPrefix);
    this.followUpCreator = new FollowUpCreator(deps.gitService);
    this.fileWriter = new FileWriter(workerDeps.workDir);
    this.createFollowUpsFn = workerDeps.createFollowUps;
  }

  protected abstract detectTaskType(task: Task): string;

  protected async executeTask(task: Task): Promise<TaskResult> {
    const taskType = this.detectTaskType(task);
    this.log.info({ taskType, title: task.title }, 'Executing task');

    if (taskType === 'unknown') {
      return {
        success: false,
        error: { message: `Unknown ${this.config.domain} task type for: ${task.title}` },
        artifacts: [],
      };
    }

    try {
      return await this.handleCodeTask(task, taskType);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      this.log.error({ err: message }, 'Task failed');
      return {
        success: false,
        error: { message },
        artifacts: [],
      };
    }
  }

  private async handleCodeTask(task: Task, taskType: string): Promise<TaskResult> {
    // 1. Claude로 코드/문서 생성
    const generated = await this.generator.generate(task, taskType);
    await this.publishTokenUsage(generated.usage.inputTokens, generated.usage.outputTokens);
    this.log.info(
      { fileCount: generated.files.length, summary: generated.summary },
      'Code generated',
    );

    // 2. analyze 타입은 파일 생성 없이 결과만 반환
    if (taskType === 'analyze') {
      return {
        success: true,
        data: { analysis: generated.summary },
        artifacts: [],
      };
    }

    // 3. 파일을 디스크에 기록
    if (generated.files.length === 0) {
      return {
        success: false,
        error: { message: 'Code generation produced no files' },
        artifacts: [],
      };
    }

    const writtenFiles = await this.fileWriter.writeFiles(generated);
    this.log.info({ fileCount: writtenFiles.length }, 'Files written to disk');

    // 4. Artifact 추적 (DB에 저장)
    for (const file of generated.files) {
      await this.stateStore.saveArtifact({
        taskId: task.id,
        filePath: file.path,
        contentHash: FileWriter.contentHash(file.content),
        createdBy: this.id,
      });
    }

    // 5. Git commit follow-up issue 생성 (non-fatal)
    try {
      await this.commitRequester.requestCommit(task, writtenFiles, generated.summary);
    } catch (error) {
      this.log.warn(
        { err: error instanceof Error ? error.message : error },
        'Failed to create commit request',
      );
    }

    // 6. 도메인 간 후속 이슈 생성 (non-fatal)
    if (this.createFollowUpsFn) {
      try {
        const followUps = this.createFollowUpsFn(task, generated.summary, writtenFiles);
        if (followUps.length > 0) {
          await this.followUpCreator.createFollowUps(task, followUps);
        }
      } catch (error) {
        this.log.warn(
          { err: error instanceof Error ? error.message : error },
          'Failed to create follow-up issues',
        );
      }
    }

    return {
      success: true,
      data: { generatedFiles: writtenFiles, summary: generated.summary },
      artifacts: writtenFiles,
    };
  }
}
