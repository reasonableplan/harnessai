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
import { detectTaskType, type BackendTaskType } from './task-router.js';

export interface BackendAgentConfig {
  workDir: string;
  claudeApiKey?: string;
  claudeClient?: IClaudeClient;
}

export class BackendAgent extends BaseAgent {
  private codeGenerator: CodeGenerator;
  private commitRequester: CommitRequester;
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

    const claude = backendConfig.claudeClient ?? new ClaudeClient(
      { model: config.claudeModel, maxTokens: config.maxTokens, temperature: config.temperature },
      backendConfig.claudeApiKey,
    );

    this.codeGenerator = new CodeGenerator(claude);
    this.commitRequester = new CommitRequester(deps.gitService);
    this.fileWriter = new FileWriter(backendConfig.workDir);
  }

  protected async executeTask(task: Task): Promise<TaskResult> {
    const taskType = detectTaskType(task);
    console.log(`[BackendAgent] Executing ${taskType} task: ${task.title}`);

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
      console.error(`[BackendAgent] Task failed: ${message}`);
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
    console.log(`[BackendAgent] Generated ${generated.files.length} files: ${generated.summary}`);

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
    console.log(`[BackendAgent] Wrote ${writtenFiles.length} files to disk`);

    // 4. Artifact 추적 (DB에 저장)
    for (const file of generated.files) {
      await this.stateStore.saveArtifact({
        id: crypto.randomUUID(),
        taskId: task.id,
        type: 'code',
        path: file.path,
        hash: FileWriter.contentHash(file.content),
        createdAt: new Date(),
      });
    }

    // 5. Git commit follow-up issue 생성
    if (task.epicId) {
      try {
        await this.commitRequester.requestCommit(task, writtenFiles, generated.summary);
      } catch (error) {
        console.warn(`[BackendAgent] Failed to create commit request: ${error instanceof Error ? error.message : error}`);
        // commit 요청 실패가 task 자체를 실패시키지는 않음
      }
    }

    return {
      success: true,
      data: { generatedFiles: writtenFiles, summary: generated.summary },
      artifacts: writtenFiles,
    };
  }
}
