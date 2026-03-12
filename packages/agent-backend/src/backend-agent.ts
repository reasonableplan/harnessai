import {
  BaseAgent,
  FileWriter,
  FollowUpCreator,
  ClaudeClient,
  CommitRequester,
  type AgentDependencies,
  type AgentConfig,
  type Task,
  type TaskResult,
  type IClaudeClient,
} from '@agent/core';
import { CodeGenerator } from './code-generator.js';
import { detectTaskType, type BackendTaskType } from './task-router.js';

export interface BackendAgentConfig {
  workDir: string;
  claudeApiKey?: string;
  claudeClient?: IClaudeClient;
}

export class BackendAgent extends BaseAgent {
  private codeGenerator: CodeGenerator;
  private commitRequester: CommitRequester;
  private followUpCreator: FollowUpCreator;
  private fileWriter: FileWriter;

  constructor(deps: AgentDependencies, backendConfig: BackendAgentConfig) {
    const config: AgentConfig = {
      id: 'backend',
      domain: 'backend',
      level: 2,
      claudeModel: 'claude-sonnet-4-20250514',
      maxTokens: 16384,
      temperature: 0.2,
      tokenBudget: 100_000,
      taskTimeoutMs: 10 * 60 * 1000, // 10분 (코드 생성은 시간이 걸림)
    };
    super(config, deps);

    if (!backendConfig.claudeClient && !backendConfig.claudeApiKey) {
      throw new Error('BackendAgent requires either claudeClient or claudeApiKey');
    }
    const claude =
      backendConfig.claudeClient ??
      new ClaudeClient(
        { model: config.claudeModel, maxTokens: config.maxTokens, temperature: config.temperature },
        backendConfig.claudeApiKey!,
      );

    this.codeGenerator = new CodeGenerator(claude, backendConfig.workDir);
    this.commitRequester = new CommitRequester(deps.gitService, 'feat(backend):');
    this.followUpCreator = new FollowUpCreator(deps.gitService);
    this.fileWriter = new FileWriter(backendConfig.workDir);
  }

  protected async executeTask(task: Task): Promise<TaskResult> {
    const taskType = detectTaskType(task);
    this.log.info({ taskType, title: task.title }, 'Executing task');

    if (taskType === 'unknown') {
      return {
        success: false,
        error: { message: `Unknown backend task type for: ${task.title}` },
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

  private async handleCodeTask(task: Task, taskType: BackendTaskType): Promise<TaskResult> {
    // 1. Claude로 코드 생성
    const generated = await this.codeGenerator.generate(task, taskType);
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

    // 6. 도메인 간 후속 이슈 생성 (non-fatal): [FE] API 연동, [DOCS] API 문서
    try {
      const followUps = FollowUpCreator.backendFollowUps(task, generated.summary, writtenFiles);
      if (followUps.length > 0) {
        await this.followUpCreator.createFollowUps(task, followUps);
      }
    } catch (error) {
      this.log.warn(
        { err: error instanceof Error ? error.message : error },
        'Failed to create follow-up issues',
      );
    }

    return {
      success: true,
      data: { generatedFiles: writtenFiles, summary: generated.summary },
      artifacts: writtenFiles,
    };
  }
}
