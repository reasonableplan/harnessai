import {
  BaseAgent,
  FileWriter,
  ClaudeClient,
  CommitRequester,
  type AgentDependencies,
  type AgentConfig,
  type Task,
  type TaskResult,
  type IClaudeClient,
} from '@agent/core';
import { DocGenerator } from './doc-generator.js';
import { detectTaskType, type DocsTaskType } from './task-router.js';

export interface DocsAgentConfig {
  workDir: string;
  claudeApiKey?: string;
  claudeClient?: IClaudeClient;
  claudeModel?: string;
}

export class DocsAgent extends BaseAgent {
  private docGenerator: DocGenerator;
  private commitRequester: CommitRequester;
  private fileWriter: FileWriter;

  constructor(deps: AgentDependencies, docsConfig: DocsAgentConfig) {
    const config: AgentConfig = {
      id: 'docs',
      domain: 'docs',
      level: 2,
      claudeModel: docsConfig.claudeModel ?? 'claude-sonnet-4-20250514',
      maxTokens: 16384,
      temperature: 0.3,
      tokenBudget: 100_000,
      taskTimeoutMs: 10 * 60 * 1000,
    };
    super(config, deps);

    if (!docsConfig.claudeClient && !docsConfig.claudeApiKey) {
      throw new Error('DocsAgent requires either claudeClient or claudeApiKey');
    }
    const claude =
      docsConfig.claudeClient ??
      new ClaudeClient(
        { model: config.claudeModel, maxTokens: config.maxTokens, temperature: config.temperature },
        docsConfig.claudeApiKey!,
      );

    this.docGenerator = new DocGenerator(claude, docsConfig.workDir);
    this.commitRequester = new CommitRequester(deps.gitService, 'docs:');
    this.fileWriter = new FileWriter(docsConfig.workDir);
  }

  protected async executeTask(task: Task): Promise<TaskResult> {
    const taskType = detectTaskType(task);
    this.log.info({ taskType, title: task.title }, 'Executing task');

    if (taskType === 'unknown') {
      return {
        success: false,
        error: { message: `Unknown docs task type for: ${task.title}` },
        artifacts: [],
      };
    }

    try {
      return await this.handleDocTask(task, taskType);
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

  private async handleDocTask(task: Task, taskType: DocsTaskType): Promise<TaskResult> {
    // 1. Claude로 문서 생성
    const generated = await this.docGenerator.generate(task, taskType);
    await this.publishTokenUsage(generated.usage.inputTokens, generated.usage.outputTokens);
    this.log.info(
      { fileCount: generated.files.length, summary: generated.summary },
      'Docs generated',
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
        error: { message: 'Document generation produced no files' },
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

    return {
      success: true,
      data: { generatedFiles: writtenFiles, summary: generated.summary },
      artifacts: writtenFiles,
    };
  }
}
