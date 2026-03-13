import { readFile } from 'node:fs/promises';
import { resolve, sep } from 'node:path';
import { createLogger } from '../logging/logger.js';
import type { IClaudeClient } from './claude-client.js';
import type { GeneratedCode, Task } from '../types/index.js';

export interface CodeGeneratorConfig {
  maxFileReadChars: number;
  maxTotalReadChars: number;
  /** taskType가 이 조건을 만족하면 기존 파일을 읽어 프롬프트에 포함 */
  isModifyType: (taskType: string) => boolean;
}

const DEFAULT_CONFIG: CodeGeneratorConfig = {
  maxFileReadChars: 50_000,
  maxTotalReadChars: 200_000,
  isModifyType: (t) => t.includes('modify') || t.includes('update'),
};

export abstract class BaseCodeGenerator<TTaskType extends string = string> {
  protected log;
  protected config: CodeGeneratorConfig;

  constructor(
    protected claude: IClaudeClient,
    protected workDir?: string,
    loggerName?: string,
    config?: Partial<CodeGeneratorConfig>,
  ) {
    this.log = createLogger(loggerName ?? 'CodeGenerator');
    this.config = { ...DEFAULT_CONFIG, ...config };
  }

  async generate(
    task: Task,
    taskType: TTaskType,
  ): Promise<GeneratedCode & { usage: { inputTokens: number; outputTokens: number } }> {
    const systemPrompt = this.buildSystemPrompt(taskType);
    const userMessage = await this.buildUserMessage(task, taskType);
    const { data, usage } = await this.claude.chatJSON<GeneratedCode>(systemPrompt, userMessage);
    this.log.info({ inputTokens: usage.inputTokens, outputTokens: usage.outputTokens }, 'Claude usage');

    if (!data || !Array.isArray(data.files) || typeof data.summary !== 'string') {
      throw new Error('Invalid Claude response shape: missing "files" array or "summary" string');
    }
    if (
      !data.files.every(
        (f: unknown) =>
          typeof (f as Record<string, unknown>).path === 'string' &&
          typeof (f as Record<string, unknown>).content === 'string',
      )
    ) {
      throw new Error('Invalid Claude response: file entry missing path or content');
    }

    return { ...data, usage };
  }

  protected abstract buildSystemPrompt(taskType: TTaskType): string;

  protected async buildUserMessage(task: Task, taskType: TTaskType): Promise<string> {
    const lines = [
      `<task>\n<title>${task.title}</title>\n<description>${task.description ?? ''}</description>\n</task>`,
    ];

    if (task.reviewNote) {
      lines.push(
        '',
        '<review_feedback>',
        task.reviewNote,
        '</review_feedback>',
        `Attempt: ${(task.retryCount ?? 0) + 1}/3`,
      );
    }

    if (task.epicId) {
      lines.push(`Epic ID: ${task.epicId}`);
    }

    if (task.artifacts.length > 0) {
      lines.push(`Existing files: ${task.artifacts.join(', ')}`);
    }

    if (this.config.isModifyType(taskType) && this.workDir && task.artifacts.length > 0) {
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
          content.length > this.config.maxFileReadChars
            ? content.slice(0, this.config.maxFileReadChars) + '\n... (truncated)'
            : content;

        if (totalChars + truncated.length > this.config.maxTotalReadChars) break;
        totalChars += truncated.length;

        results.push({ path: filePath, content: truncated });
      } catch (err) {
        this.log.warn(
          { path: filePath, err: err instanceof Error ? err.message : err },
          'Failed to read existing file, skipping',
        );
      }
    }

    return results;
  }
}
