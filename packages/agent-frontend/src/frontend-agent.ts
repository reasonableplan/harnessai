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

export interface FrontendAgentConfig {
  workDir: string;
  claudeApiKey?: string;
  claudeClient?: IClaudeClient;
  claudeModel?: string;
}

export class FrontendAgent extends BaseWorkerAgent {
  constructor(deps: AgentDependencies, frontendConfig: FrontendAgentConfig) {
    const config: AgentConfig = {
      id: 'frontend',
      domain: 'frontend',
      level: 2,
      claudeModel: frontendConfig.claudeModel ?? DEFAULT_CLAUDE_MODEL,
      maxTokens: 16384,
      temperature: 0.2,
      tokenBudget: 100_000,
      taskTimeoutMs: 10 * 60 * 1000,
      pollIntervalMs: 10_000,
    };

    if (!frontendConfig.claudeClient && !frontendConfig.claudeApiKey) {
      throw new Error('FrontendAgent requires either claudeClient or claudeApiKey');
    }
    const claude =
      frontendConfig.claudeClient ??
      new ClaudeClient(
        { model: config.claudeModel, maxTokens: config.maxTokens, temperature: config.temperature },
        frontendConfig.claudeApiKey!,
      );

    super(config, deps, {
      generator: new CodeGenerator(claude, frontendConfig.workDir),
      commitPrefix: 'feat(frontend):',
      workDir: frontendConfig.workDir,
      createFollowUps: (task, summary, files) =>
        FollowUpCreator.frontendFollowUps(task, summary, files),
    });
  }

  protected detectTaskType(task: Task): string {
    return detectTaskType(task);
  }
}
