import { readFile } from 'node:fs/promises';
import { resolve, sep } from 'node:path';
import { createLogger, type IClaudeClient, type GeneratedCode, type Task } from '@agent/core';
import type { BackendTaskType } from './task-router.js';

export type { IClaudeClient } from '@agent/core';

const log = createLogger('CodeGenerator');

const MAX_FILE_READ_CHARS = 8000;
const MAX_TOTAL_CHARS = 30000;

/**
 * Claude API를 사용하여 백엔드 코드를 생성하는 엔진.
 * 각 task type에 맞는 시스템 프롬프트를 제공한다.
 */
export class CodeGenerator {
  constructor(
    private claude: IClaudeClient,
    private workDir?: string,
  ) {}

  async generate(task: Task, taskType: BackendTaskType): Promise<GeneratedCode & { usage: { inputTokens: number; outputTokens: number } }> {
    const systemPrompt = this.buildSystemPrompt(taskType);
    const userMessage = await this.buildUserMessage(task, taskType);

    const { data, usage } = await this.claude.chatJSON<GeneratedCode>(systemPrompt, userMessage);
    log.info({ inputTokens: usage.inputTokens, outputTokens: usage.outputTokens }, 'Claude usage');

    if (!data || !Array.isArray(data.files) || typeof data.summary !== 'string') {
      throw new Error('Invalid Claude response shape: missing "files" array or "summary" string');
    }

    return { ...data, usage };
  }

  private buildSystemPrompt(taskType: BackendTaskType): string {
    const base = `You are a backend code generator for a Node.js/Express/TypeScript project.
Generate production-quality code following these conventions:
- Express with TypeScript
- Zod for request/response validation
- Drizzle ORM for database access
- Error handling with typed error classes
- ESM imports (.js extensions in import paths)

IMPORTANT: Respond with valid JSON only. No markdown, no explanation.
{
  "files": [
    {
      "path": "src/routes/example.ts",
      "content": "// full file content here",
      "action": "create",
      "language": "typescript"
    }
  ],
  "summary": "Brief description of what was generated"
}`;

    const typeSpecific: Record<string, string> = {
      'api.create': `\n\nGenerate a complete API endpoint with:
- Route file (src/routes/<resource>.ts) with Express Router
- Controller file (src/controllers/<resource>.controller.ts) with business logic
- Zod schema file (src/schemas/<resource>.schema.ts) for validation
- Route registration in src/routes/index.ts (action: "update")`,

      'api.modify': `\n\nModify an existing API endpoint. Update only the files that need changes.
Use action "update" for modified files.`,

      'model.create': `\n\nGenerate a database model with:
- Drizzle schema file (src/models/<name>.ts) with table definition
- Type exports for the model
- Migration file if needed`,

      'model.modify': `\n\nModify an existing database model. Update only the affected files.`,

      'middleware.create': `\n\nGenerate Express middleware with:
- Middleware file (src/middleware/<name>.ts)
- Proper TypeScript typing for Request/Response`,

      'test.create': `\n\nGenerate test files with:
- Test file (src/__tests__/<target>.test.ts) using vitest
- Mock setup for external dependencies
- Cover happy path + error cases`,

      analyze: `\n\nAnalyze the described code and respond with:
- files: [] (empty — analysis produces no files)
- summary: detailed analysis results as a string`,
    };

    return base + (typeSpecific[taskType] ?? '');
  }

  private async buildUserMessage(task: Task, taskType: BackendTaskType): Promise<string> {
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
    const isModify = taskType === 'api.modify' || taskType === 'model.modify';
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

        const truncated =
          content.length > MAX_FILE_READ_CHARS
            ? content.slice(0, MAX_FILE_READ_CHARS) + '\n... (truncated)'
            : content;

        if (totalChars + truncated.length > MAX_TOTAL_CHARS) break;
        totalChars += truncated.length;

        results.push({ path: filePath, content: truncated });
      } catch (err) {
        log.warn({ path: filePath, err: err instanceof Error ? err.message : err }, 'Failed to read existing file, skipping');
      }
    }

    return results;
  }
}
