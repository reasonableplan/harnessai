import type { AgentFactory, AppConfig } from '@agent/core';
import { DirectorAgent } from '@agent/director';
import { GitAgent } from '@agent/git';
import { BackendAgent } from '@agent/backend';
import { FrontendAgent } from '@agent/frontend';
import { DocsAgent } from '@agent/docs';

/**
 * 모든 에이전트의 factory 함수를 정의한다.
 * bootstrap()에 주입하여 패키지 간 의존성을 core에서 분리한다.
 *
 * AppConfig를 통해 환경변수를 DI로 받는다 (process.env 직접 참조 없음).
 */
export function createAgentFactories(config: AppConfig): Record<string, AgentFactory> {
  const { apiKey: claudeApiKey } = config.claude;
  const { workDir } = config.workspace;
  const { token: githubToken, owner: githubOwner, repo: githubRepo } = config.github;

  return {
    director: (deps) => new DirectorAgent(deps, { claudeApiKey }),

    git: (deps) => new GitAgent(deps, { workDir, githubToken, githubOwner, githubRepo }),

    backend: (deps) => new BackendAgent(deps, { workDir, claudeApiKey }),

    frontend: (deps) => new FrontendAgent(deps, { workDir, claudeApiKey }),

    docs: (deps) => new DocsAgent(deps, { workDir, claudeApiKey }),
  };
}
