import {
  BaseWorkerAgent,
  ClaudeClient,
  type AgentDependencies,
  type AgentConfig,
  type Task,
  type IClaudeClient,
} from '@agent/core';
import { DocGenerator } from './doc-generator.js';
import { detectTaskType } from './task-router.js';

export interface DocsAgentConfig {
  workDir: string;
  claudeApiKey?: string;
  claudeClient?: IClaudeClient;
  claudeModel?: string;
}

export class DocsAgent extends BaseWorkerAgent {
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
      pollIntervalMs: 10_000,
    };

    if (!docsConfig.claudeClient && !docsConfig.claudeApiKey) {
      throw new Error('DocsAgent requires either claudeClient or claudeApiKey');
    }
    const claude =
      docsConfig.claudeClient ??
      new ClaudeClient(
        { model: config.claudeModel, maxTokens: config.maxTokens, temperature: config.temperature },
        docsConfig.claudeApiKey!,
      );

    super(config, deps, {
      generator: new DocGenerator(claude, docsConfig.workDir),
      commitPrefix: 'docs:',
      workDir: docsConfig.workDir,
      // DocsAgent는 도메인 간 follow-up 이슈 생성 없음
    });
  }

  protected detectTaskType(task: Task): string {
    return detectTaskType(task);
  }
}
