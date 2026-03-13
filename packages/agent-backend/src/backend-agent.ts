import {
  BaseWorkerAgent,
  ClaudeClient,
  FollowUpCreator,
  DEFAULT_CLAUDE_MODEL,
  type AgentDependencies,
  type AgentConfig,
  type Task,
  type IClaudeClient,
} from '@agent/core';
import { CodeGenerator } from './code-generator.js';
import { detectTaskType } from './task-router.js';

export interface BackendAgentConfig {
  workDir: string;
  claudeApiKey?: string;
  claudeClient?: IClaudeClient;
  claudeModel?: string;
}

export class BackendAgent extends BaseWorkerAgent {
  constructor(deps: AgentDependencies, backendConfig: BackendAgentConfig) {
    const config: AgentConfig = {
      id: 'backend',
      domain: 'backend',
      level: 2,
      claudeModel: backendConfig.claudeModel ?? DEFAULT_CLAUDE_MODEL,
      maxTokens: 16384,
      temperature: 0.2,
      tokenBudget: 100_000,
      taskTimeoutMs: 10 * 60 * 1000,
      pollIntervalMs: 10_000,
    };

    if (!backendConfig.claudeClient && !backendConfig.claudeApiKey) {
      throw new Error('BackendAgent requires either claudeClient or claudeApiKey');
    }
    const claude =
      backendConfig.claudeClient ??
      new ClaudeClient(
        { model: config.claudeModel, maxTokens: config.maxTokens, temperature: config.temperature },
        backendConfig.claudeApiKey!,
      );

    super(config, deps, {
      generator: new CodeGenerator(claude, backendConfig.workDir),
      commitPrefix: 'feat(backend):',
      workDir: backendConfig.workDir,
      createFollowUps: (task, summary, files) =>
        FollowUpCreator.backendFollowUps(task, summary, files),
    });
  }

  protected detectTaskType(task: Task): string {
    return detectTaskType(task);
  }
}
