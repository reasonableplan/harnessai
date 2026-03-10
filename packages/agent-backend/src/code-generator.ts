import { createLogger, type GeneratedCode, type Task } from '@agent/core';
import type { BackendTaskType } from './task-router.js';

const log = createLogger('CodeGenerator');

/**
 * Claude API 인터페이스. 테스트에서 mock 주입 가능.
 */
export interface IClaudeClient {
  chatJSON<T>(systemPrompt: string, userMessage: string): Promise<{
    data: T;
    usage: { inputTokens: number; outputTokens: number };
  }>;
}

/**
 * Claude API를 사용하여 백엔드 코드를 생성하는 엔진.
 * 각 task type에 맞는 시스템 프롬프트를 제공한다.
 */
export class CodeGenerator {
  constructor(private claude: IClaudeClient) {}

  async generate(task: Task, taskType: BackendTaskType): Promise<GeneratedCode> {
    const systemPrompt = this.buildSystemPrompt(taskType);
    const userMessage = this.buildUserMessage(task);

    const { data, usage } = await this.claude.chatJSON<GeneratedCode>(
      systemPrompt,
      userMessage,
    );
    log.info({ inputTokens: usage.inputTokens, outputTokens: usage.outputTokens }, 'Claude usage');

    if (!data || !Array.isArray(data.files) || typeof data.summary !== 'string') {
      throw new Error('Invalid Claude response shape: missing "files" array or "summary" string');
    }

    return data;
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

      'analyze': `\n\nAnalyze the described code and respond with:
- files: [] (empty — analysis produces no files)
- summary: detailed analysis results as a string`,
    };

    return base + (typeSpecific[taskType] ?? '');
  }

  private buildUserMessage(task: Task): string {
    const lines = [
      `Task: ${task.title}`,
      `Description: ${task.description}`,
    ];

    if (task.epicId) {
      lines.push(`Epic ID: ${task.epicId}`);
    }

    if (task.artifacts.length > 0) {
      lines.push(`Existing files: ${task.artifacts.join(', ')}`);
    }

    return lines.join('\n');
  }
}
