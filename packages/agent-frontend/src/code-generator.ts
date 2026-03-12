import { readFile } from 'node:fs/promises';
import { resolve, sep } from 'node:path';
import { createLogger, type IClaudeClient, type GeneratedCode, type Task } from '@agent/core';
import type { FrontendTaskType } from './task-router.js';

export type { IClaudeClient } from '@agent/core';

const log = createLogger('FrontendCodeGen');

/** 파일 읽기 제한 (문자 수 기준) */
const MAX_FILE_READ_CHARS = 50_000; // 파일당 최대 ~50K 문자
const MAX_TOTAL_READ_CHARS = 200_000; // 전체 최대 ~200K 문자

/**
 * Claude API를 사용하여 프론트엔드 코드를 생성하는 엔진.
 * 각 task type에 맞는 시스템 프롬프트를 제공한다.
 */
export class CodeGenerator {
  constructor(
    private claude: IClaudeClient,
    private workDir?: string,
  ) {}

  async generate(task: Task, taskType: FrontendTaskType): Promise<GeneratedCode & { usage: { inputTokens: number; outputTokens: number } }> {
    const systemPrompt = this.buildSystemPrompt(taskType);
    const userMessage = await this.buildUserMessage(task, taskType);

    const { data, usage } = await this.claude.chatJSON<GeneratedCode>(systemPrompt, userMessage);
    log.info({ inputTokens: usage.inputTokens, outputTokens: usage.outputTokens }, 'Claude usage');

    if (!data || !Array.isArray(data.files) || typeof data.summary !== 'string') {
      throw new Error('Invalid Claude response shape: missing "files" array or "summary" string');
    }

    return { ...data, usage };
  }

  private buildSystemPrompt(taskType: FrontendTaskType): string {
    const base = `You are a frontend code generator for a React/TypeScript project.
Generate production-quality code following these conventions:
- React 18+ with functional components and hooks
- TypeScript strict mode
- Tailwind CSS for styling
- Zustand for state management
- Named exports (not default exports)
- Props interface defined above component
- File naming: PascalCase for components, camelCase for hooks/utils
- Vitest + Testing Library for tests

IMPORTANT: Respond with valid JSON only. No markdown, no explanation.
{
  "files": [
    {
      "path": "src/components/Example.tsx",
      "content": "// full file content here",
      "action": "create",
      "language": "typescriptreact"
    }
  ],
  "summary": "Brief description of what was generated"
}`;

    const typeSpecific: Record<string, string> = {
      'component.create': `\n\nGenerate a React component with:
- Component file (src/components/<Name>/<Name>.tsx) with props interface
- Test file (src/components/<Name>/<Name>.test.tsx) with Vitest + Testing Library
- Index file (src/components/<Name>/index.ts) for re-export`,

      'component.modify': `\n\nModify an existing React component. Update only the files that need changes.
Use action "update" for modified files.`,

      'page.create': `\n\nGenerate a page component with:
- Page file (src/pages/<Name>.tsx) with route-specific logic
- Route registration update (src/router.tsx, action: "update")
- Any required hooks for API integration`,

      'page.modify': `\n\nModify an existing page. Update only the affected files.`,

      'hook.create': `\n\nGenerate a custom React hook with:
- Hook file (src/hooks/use<Name>.ts) following React hooks conventions
- Test file (src/hooks/use<Name>.test.ts)
- Proper TypeScript typing for parameters and return values`,

      'store.create': `\n\nGenerate a Zustand store with:
- Store file (src/stores/use<Name>Store.ts) with typed state and actions
- Test file (src/stores/use<Name>Store.test.ts)
- Selectors for computed values if applicable`,

      'style.generate': `\n\nGenerate styling with Tailwind CSS:
- Utility classes directly in components
- Custom CSS only when Tailwind classes are insufficient`,

      'test.create': `\n\nGenerate test files with:
- Test file (src/__tests__/<target>.test.tsx) using Vitest + Testing Library
- Mock setup for external dependencies (API calls, stores)
- Cover happy path + error cases + edge cases`,

      analyze: `\n\nAnalyze the described frontend code and respond with:
- files: [] (empty — analysis produces no files)
- summary: detailed analysis results as a string`,
    };

    return base + (typeSpecific[taskType] ?? '');
  }

  private async buildUserMessage(task: Task, taskType: FrontendTaskType): Promise<string> {
    const lines = [`Task: ${task.title}`, `Description: ${task.description}`];

    if (task.reviewNote) {
      lines.push(
        '',
        '⚠️ PREVIOUS REVIEW FEEDBACK (address these issues):',
        task.reviewNote,
        `Attempt: ${task.retryCount + 1}/3`,
      );
    }

    if (task.epicId) {
      lines.push(`Epic ID: ${task.epicId}`);
    }

    if (task.artifacts.length > 0) {
      lines.push(`Existing files: ${task.artifacts.join(', ')}`);
    }

    // modify 작업 시 기존 파일 내용을 프롬프트에 포함
    const isModify = taskType === 'component.modify' || taskType === 'page.modify';
    if (isModify && this.workDir && task.artifacts.length > 0) {
      const fileContents = await this.readExistingFiles(task.artifacts);
      if (fileContents.length > 0) {
        lines.push('', '### Existing File Contents');
        for (const fc of fileContents) {
          lines.push(`\n**${fc.path}**\n\`\`\`\n${fc.content}\n\`\`\``);
        }
      }
    }

    return lines.join('\n');
  }

  /**
   * 기존 파일 내용을 읽는다.
   * - workDir 밖 경로(path traversal) 차단
   * - 파일당/총 크기 상한 적용
   */
  private async readExistingFiles(
    paths: string[],
  ): Promise<Array<{ path: string; content: string }>> {
    if (!this.workDir) return [];
    const resolvedWorkDir = resolve(this.workDir);
    const results: Array<{ path: string; content: string }> = [];
    let totalChars = 0;

    for (const filePath of paths) {
      const absPath = resolve(resolvedWorkDir, filePath);

      // Sandbox: workDir 밖 경로 차단
      if (!absPath.startsWith(resolvedWorkDir + sep)) continue;

      try {
        const content = await readFile(absPath, 'utf-8');

        // 파일당 문자 수 초과 시 truncate
        const truncated =
          content.length > MAX_FILE_READ_CHARS
            ? content.slice(0, MAX_FILE_READ_CHARS) + '\n... (truncated)'
            : content;

        if (totalChars + truncated.length > MAX_TOTAL_READ_CHARS) break;
        totalChars += truncated.length;
        results.push({ path: filePath, content: truncated });
      } catch (err) {
        log.warn({ path: filePath, err: err instanceof Error ? err.message : err }, 'Failed to read existing file, skipping');
      }
    }

    return results;
  }
}
