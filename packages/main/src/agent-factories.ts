import type { AgentFactory } from '@agent/core';
import { DirectorAgent } from '@agent/director';
import { GitAgent } from '@agent/git';
import { BackendAgent } from '@agent/backend';
import { FrontendAgent } from '@agent/frontend';
import { DocsAgent } from '@agent/docs';

/**
 * 모든 에이전트의 factory 함수를 정의한다.
 * bootstrap()에 주입하여 패키지 간 의존성을 core에서 분리한다.
 *
 * 환경 변수:
 * - ANTHROPIC_API_KEY: Claude API 키 (Director, Backend, Frontend, Docs)
 * - GIT_WORK_DIR: 워크스페이스 디렉토리 (Git, Backend, Frontend, Docs)
 * - GITHUB_TOKEN: GitHub 인증 토큰 (Git)
 */
export function createAgentFactories(): Record<string, AgentFactory> {
  const claudeApiKey = process.env.ANTHROPIC_API_KEY;
  const workDir = process.env.GIT_WORK_DIR ?? './workspace';
  const githubToken = process.env.GITHUB_TOKEN;

  return {
    director: (deps) =>
      new DirectorAgent(deps, { claudeApiKey }),

    git: (deps) =>
      new GitAgent(deps, { workDir, githubToken }),

    backend: (deps) =>
      new BackendAgent(deps, { workDir, claudeApiKey }),

    frontend: (deps) =>
      new FrontendAgent(deps, { workDir, claudeApiKey }),

    docs: (deps) =>
      new DocsAgent(deps, { workDir, claudeApiKey }),
  };
}
