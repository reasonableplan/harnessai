import {
  BaseAgent,
  FileWriter,
  type AgentDependencies,
  type AgentConfig,
  type Task,
  type TaskResult,
} from '@agent/core';
import { ClaudeClient } from './claude-client.js';
import { CodeGenerator, type IClaudeClient } from './code-generator.js';
import { CommitRequester } from './commit-requester.js';
import { detectTaskType, type FrontendTaskType } from './task-router.js';

export interface FrontendAgentConfig {
  workDir: string;
  claudeApiKey?: string;
  claudeClient?: IClaudeClient;
}

export class FrontendAgent extends BaseAgent {
  private codeGenerator: CodeGenerator;
  private commitRequester: CommitRequester;
  private fileWriter: FileWriter;

  constructor(deps: AgentDependencies, frontendConfig: FrontendAgentConfig) {
    const config: AgentConfig = {
      id: 'frontend',
      domain: 'frontend',
      level: 2,
      claudeModel: 'claude-sonnet-4-20250514',
      maxTokens: 16384,
      temperature: 0.2,
      tokenBudget: 100_000,
      taskTimeoutMs: 10 * 60 * 1000, // 10분 (코드 생성은 시간이 걸림)
    };
    super(config, deps);

    const claude = frontendConfig.claudeClient ?? new ClaudeClient(
      { model: config.claudeModel, maxTokens: config.maxTokens, temperature: config.temperature },
      frontendConfig.claudeApiKey,
    );

    this.codeGenerator = new CodeGenerator(claude, frontendConfig.workDir);
    this.commitRequester = new CommitRequester(deps.gitService);
    this.fileWriter = new FileWriter(frontendConfig.workDir);
  }

  protected async executeTask(task: Task): Promise<TaskResult> {
    const taskType = detectTaskType(task);
    this.log.info({ taskType, title: task.title }, 'Executing task');

    if (taskType === 'unknown') {
      return {
        success: false,
        error: { message: `Unknown frontend task type for: ${task.title}` },
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

  private async handleCodeTask(task: Task, taskType: FrontendTaskType): Promise<TaskResult> {
    // 1. Claude로 코드 생성
    const generated = await this.codeGenerator.generate(task, taskType);
    this.log.info({ fileCount: generated.files.length, summary: generated.summary }, 'Code generated');

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
      this.log.warn({ err: error instanceof Error ? error.message : error }, 'Failed to create commit request');
      // commit 요청 실패가 task 자체를 실패시키지는 않음
    }

    return {
      success: true,
      data: { generatedFiles: writtenFiles, summary: generated.summary },
      artifacts: writtenFiles,
    };
  }
}
