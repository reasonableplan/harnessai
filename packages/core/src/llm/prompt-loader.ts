import { readFileSync, existsSync } from 'node:fs';
import { resolve, dirname, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createLogger } from '../logging/logger.js';

const log = createLogger('PromptLoader');

/**
 * prompts/ 디렉토리에서 에이전트별 시스템 프롬프트를 로드한다.
 * 에이전트 프롬프트 + shared/* 를 조합하여 완전한 시스템 프롬프트를 생성.
 */
export class PromptLoader {
  private promptsDir: string;
  private cache = new Map<string, string>();

  constructor(promptsDir?: string) {
    // 기본 경로: 프로젝트 루트의 prompts/
    this.promptsDir = promptsDir ?? this.findPromptsDir();
  }

  /**
   * 에이전트 이름으로 완전한 시스템 프롬프트를 로드한다.
   * shared/* + agent-specific 프롬프트를 결합.
   */
  loadAgentPrompt(agentName: string): string {
    const cacheKey = `agent:${agentName}`;
    const cached = this.cache.get(cacheKey);
    if (cached) return cached;

    const parts: string[] = [];

    // 1. Shared prompts (모든 에이전트 공통)
    const sharedFiles = [
      'shared/code-standards.md',
      'shared/quality-gates.md',
      'shared/workflow.md',
      'shared/communication.md',
    ];
    for (const file of sharedFiles) {
      const content = this.readPromptFile(file);
      if (content) parts.push(content);
    }

    // 2. Agent-specific prompt
    const agentContent = this.readPromptFile(`${agentName}.md`);
    if (agentContent) {
      parts.push(agentContent);
    } else {
      log.warn({ agentName }, 'Agent prompt file not found, using shared prompts only');
    }

    const combined = parts.join('\n\n---\n\n');
    this.cache.set(cacheKey, combined);

    log.info(
      { agentName, totalLength: combined.length, parts: parts.length },
      'Agent prompt loaded',
    );

    return combined;
  }

  /**
   * 특정 프롬프트 파일 하나만 로드한다.
   * Director의 리뷰/디스패치 등 특수 용도.
   */
  loadFile(filename: string): string {
    return this.readPromptFile(filename) ?? '';
  }

  /** prompts 디렉토리 경로를 반환한다. */
  get directory(): string {
    return this.promptsDir;
  }

  /** 캐시를 비운다. 프롬프트 파일 변경 후 핫 리로드 시 사용. */
  clearCache(): void {
    this.cache.clear();
  }

  private readPromptFile(relativePath: string): string | null {
    const fullPath = resolve(this.promptsDir, relativePath);

    // 패스 트래버설 방어: resolved 경로가 promptsDir 내부인지 검증
    const resolvedBase = resolve(this.promptsDir) + sep;
    if (!fullPath.startsWith(resolvedBase) && fullPath !== resolve(this.promptsDir)) {
      log.warn({ relativePath, fullPath }, 'Path traversal attempt blocked');
      return null;
    }

    try {
      return readFileSync(fullPath, 'utf-8');
    } catch (err: unknown) {
      // ENOENT만 삼키고 나머지는 re-throw (CLAUDE.md 규칙 7)
      if (err instanceof Error && 'code' in err && (err as NodeJS.ErrnoException).code === 'ENOENT') {
        log.debug({ path: fullPath }, 'Prompt file not found');
        return null;
      }
      throw err;
    }
  }

  private findPromptsDir(): string {
    // ESM에서 __dirname 대체
    const currentFile = fileURLToPath(import.meta.url);
    const currentDir = dirname(currentFile);
    // packages/core/src/llm/ → 프로젝트 루트 (4단계 상위)
    // 빌드 후: packages/core/dist/ → 프로젝트 루트 (3단계 상위)
    // 두 경우 모두 처리: shared/ 디렉토리 존재를 마커로 사용
    let dir = currentDir;
    for (let i = 0; i < 6; i++) {
      const candidate = resolve(dir, 'prompts');
      if (existsSync(resolve(candidate, 'shared'))) {
        return candidate;
      }
      dir = dirname(dir);
    }
    // 최후 폴백: CWD 기준
    return resolve(process.cwd(), 'prompts');
  }
}

/** 싱글톤 인스턴스 — 전역에서 동일한 캐시 사용 */
let defaultLoader: PromptLoader | null = null;

export function getPromptLoader(promptsDir?: string): PromptLoader {
  if (!defaultLoader) {
    defaultLoader = new PromptLoader(promptsDir);
  } else if (promptsDir !== undefined && resolve(promptsDir) !== resolve(defaultLoader.directory)) {
    log.warn(
      { requested: promptsDir },
      'getPromptLoader() called with different promptsDir after initialization — ignoring. Use new PromptLoader() for a separate instance.',
    );
  }
  return defaultLoader;
}

/** 테스트용: 싱글톤을 리셋한다. */
export function resetPromptLoader(): void {
  defaultLoader = null;
}
