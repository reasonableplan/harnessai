import { createLogger, type IClaudeClient, type GeneratedCode, type Task } from '@agent/core';
import { readFile } from 'node:fs/promises';
import { resolve, sep } from 'node:path';
import type { DocsTaskType } from './task-router.js';

export type { IClaudeClient } from '@agent/core';

const log = createLogger('DocGenerator');

/** 파일 읽기 제한 */
const MAX_FILE_READ_CHARS = 50_000;
const MAX_TOTAL_READ_CHARS = 200_000;

const BASE_SYSTEM_PROMPT = `You are a technical documentation generator for a TypeScript project.
Generate production-quality documentation following these conventions:
- Markdown formatting with proper headers, tables, and code blocks
- Clear, concise, and scannable content
- Korean or English as appropriate (match the request language)
- Practical examples with code snippets
- Keep a Changelog format for changelogs
- Tables for structured data (API params, env vars, error codes)

IMPORTANT: Respond with valid JSON only. No markdown wrapping, no explanation.
{
  "files": [
    {
      "path": "docs/example.md",
      "content": "# full markdown content here",
      "action": "create",
      "language": "markdown"
    }
  ],
  "summary": "Brief description of what was generated"
}`;

const TYPE_SPECIFIC_PROMPTS: Readonly<Record<string, string>> = {
  'readme.generate': `\n\nGenerate a comprehensive README.md with:
- Project title and badges
- Overview/description
- Features list
- Tech stack
- Installation guide
- Quick start / usage examples
- Project structure (directory tree)
- NPM scripts table
- Contributing link
- License`,

  'readme.update': `\n\nUpdate an existing README.md. Only modify the sections that need changes.
Use action "update" for the README file.
Preserve existing content structure and style.`,

  'api-docs.generate': `\n\nGenerate API documentation with:
- docs/api.md with all endpoints grouped by resource
- For each endpoint: method, path, description, request/response examples
- Error codes table
- Authentication requirements
- curl examples`,

  'api-docs.update': `\n\nUpdate existing API documentation. Add/modify only the changed endpoints.
Use action "update" for modified files.`,

  'changelog.update': `\n\nUpdate CHANGELOG.md following Keep a Changelog format:
- Group by: Added, Changed, Deprecated, Removed, Fixed, Security
- Include date in [version] - YYYY-MM-DD format
- Link to relevant issues/PRs where applicable`,

  'architecture.generate': `\n\nGenerate architecture documentation with:
- docs/architecture.md with system overview
- Component diagram (ASCII art or mermaid)
- Data flow description
- Directory structure with descriptions
- Technology stack details
- Design decisions and trade-offs`,

  'jsdoc.add': `\n\nAdd JSDoc/TSDoc comments to source files:
- Document all exported functions, classes, and interfaces
- Include @param, @returns, @throws, @example tags
- Use action "update" for modified source files
- Do not modify code logic, only add/update comments`,

  'contributing.generate': `\n\nGenerate CONTRIBUTING.md with:
- How to set up the development environment
- Code style and conventions
- Branch naming and commit message format
- PR process
- Issue reporting guidelines`,

  'env-example.update': `\n\nUpdate .env.example with:
- All required environment variables
- Description comments for each variable
- Default values where appropriate
- Group by category (Database, API, Auth, etc.)`,

  'activity-log.generate': `\n\nGenerate an activity log document:
- docs/activity-log.md summarizing recent agent activities
- Timeline of tasks completed
- Which agent handled what
- Current project status`,

  'report.daily': `\n\nGenerate a daily progress report:
- docs/reports/daily-YYYY-MM-DD.md
- Summary of completed tasks
- Active/blocked tasks
- Key metrics (files generated, issues closed)
- Next steps`,

  'report.epic': `\n\nGenerate an epic progress report:
- Overall completion percentage
- Task breakdown by status
- Agent contribution summary
- Remaining work estimate`,

  analyze: `\n\nAnalyze the described documentation needs and respond with:
- files: [] (empty — analysis produces no files)
- summary: detailed analysis results as a string`,
};

/**
 * Claude API를 사용하여 문서를 생성하는 엔진.
 * 각 task type에 맞는 시스템 프롬프트를 제공한다.
 */
export class DocGenerator {
  constructor(
    private claude: IClaudeClient,
    private workDir?: string,
  ) {}

  async generate(task: Task, taskType: DocsTaskType): Promise<GeneratedCode & { usage: { inputTokens: number; outputTokens: number } }> {
    const systemPrompt = this.buildSystemPrompt(taskType);
    const userMessage = await this.buildUserMessage(task, taskType);

    const { data, usage } = await this.claude.chatJSON<GeneratedCode>(systemPrompt, userMessage);
    log.info({ inputTokens: usage.inputTokens, outputTokens: usage.outputTokens }, 'Claude usage');

    if (!data || !Array.isArray(data.files) || typeof data.summary !== 'string') {
      throw new Error(`Invalid Claude response shape: missing "files" array or "summary" string`);
    }

    return { ...data, usage };
  }

  private buildSystemPrompt(taskType: DocsTaskType): string {
    return BASE_SYSTEM_PROMPT + (TYPE_SPECIFIC_PROMPTS[taskType] ?? '');
  }

  private async buildUserMessage(task: Task, taskType: DocsTaskType): Promise<string> {
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

    // update 작업 시 기존 파일 내용을 프롬프트에 포함
    const isUpdate = taskType.includes('update') || taskType === 'jsdoc.add';
    if (isUpdate && this.workDir && task.artifacts.length > 0) {
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
      if (!absPath.startsWith(resolvedWorkDir + sep)) continue;

      try {
        const content = await readFile(absPath, 'utf-8');
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
