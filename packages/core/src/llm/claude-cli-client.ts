import { spawn } from 'node:child_process';
import { createLogger } from '../logging/logger.js';
import { TokenBudgetError } from '../errors.js';
import { withRetry } from '../resilience/api-retry.js';
import { parseJSONResponse } from './json-extract.js';
import type { IClaudeClient, ClaudeResponse } from './claude-client.js';

const log = createLogger('ClaudeCliClient');

/** stdout/stderr 최대 버퍼 크기 (10MB). 초과 시 프로세스를 강제 종료한다. */
const MAX_OUTPUT_BYTES = 10 * 1024 * 1024;

export interface ClaudeCliClientConfig {
  model: string;
  maxTokens: number;
  temperature?: number;
  /** Token budget. 0 = unlimited. */
  tokenBudget?: number;
}

interface CliJsonResult {
  type: string;
  result: string;
  is_error: boolean;
  duration_ms: number;
  usage: {
    input_tokens: number;
    output_tokens: number;
    cache_creation_input_tokens?: number;
    cache_read_input_tokens?: number;
  };
  total_cost_usd: number;
}

/**
 * Claude Code CLI를 subprocess로 호출하는 클라이언트.
 * Claude Max 구독 사용자가 API 크레딧 없이 에이전트를 운영할 수 있다.
 *
 * `claude -p --output-format json` 으로 비대화형 호출.
 */
export class ClaudeCliClient implements IClaudeClient {
  private config: ClaudeCliClientConfig;
  private totalTokensUsed = 0;

  constructor(config: ClaudeCliClientConfig) {
    this.config = config;
  }

  get tokensUsed(): number {
    return this.totalTokensUsed;
  }

  async chat(systemPrompt: string, userMessage: string): Promise<ClaudeResponse> {
    const budget = this.config.tokenBudget ?? 0;
    if (budget > 0 && this.totalTokensUsed >= budget) {
      throw new TokenBudgetError(this.totalTokensUsed, budget);
    }

    const result = await withRetry(
      () => this.execCli(systemPrompt, userMessage),
      { maxRetries: 3, baseDelayMs: 2000, maxDelayMs: 30_000 },
      'Claude CLI',
    );

    const usage = {
      inputTokens: result.usage.input_tokens,
      outputTokens: result.usage.output_tokens,
    };
    this.totalTokensUsed += usage.inputTokens + usage.outputTokens;

    log.info(
      { inputTokens: usage.inputTokens, outputTokens: usage.outputTokens, totalUsed: this.totalTokensUsed, costUsd: result.total_cost_usd },
      'Claude CLI usage',
    );

    return { content: result.result, usage };
  }

  async chatJSON<T>(
    systemPrompt: string,
    userMessage: string,
  ): Promise<{ data: T; usage: ClaudeResponse['usage'] }> {
    const response = await this.chat(
      systemPrompt + '\n\nIMPORTANT: Respond with valid JSON only. No markdown, no explanation.',
      userMessage,
    );

    const data = parseJSONResponse<T>(response.content, 'Claude CLI');
    return { data, usage: response.usage };
  }

  private execCli(systemPrompt: string, userMessage: string): Promise<CliJsonResult> {
    return new Promise((resolve, reject) => {
      const args = [
        '-p',
        '--output-format', 'json',
        '--model', this.config.model,
        '--max-turns', '1',
        '--system-prompt', systemPrompt,
        '--no-session-persistence',
        '--tools', '',
      ];

      // temperature 지원 (Claude CLI --temperature 플래그)
      if (this.config.temperature != null) {
        args.push('--temperature', String(this.config.temperature));
      }

      // '--' 이후 인수는 positional로 강제 — argument injection 방어
      // (userMessage가 '--dangerously-skip-permissions' 등으로 시작해도 플래그로 해석 안 됨)
      args.push('--', userMessage);

      // shell: false (기본값) — 커맨드 인젝션 방지.
      // stdin: 'ignore' — 사용하지 않는 파이프를 열지 않음.
      const proc = spawn('claude', args, {
        stdio: ['ignore', 'pipe', 'pipe'],
        timeout: 5 * 60 * 1000,
      });

      let stdout = '';
      let stderr = '';
      let killed = false;

      const killProc = (reason: string): void => {
        if (killed) return;
        killed = true;
        // Windows에서는 SIGKILL 미지원 — 인수 없이 kill() 호출
        if (process.platform === 'win32') {
          proc.kill();
        } else {
          proc.kill('SIGKILL');
        }
        reject(new Error(reason));
      };

      proc.stdout.on('data', (chunk: Buffer) => {
        stdout += chunk.toString();
        if (stdout.length > MAX_OUTPUT_BYTES) {
          killProc(`Claude CLI stdout exceeded ${MAX_OUTPUT_BYTES} bytes — process killed`);
        }
      });

      proc.stderr.on('data', (chunk: Buffer) => {
        stderr += chunk.toString();
        if (stderr.length > MAX_OUTPUT_BYTES) {
          killProc(`Claude CLI stderr exceeded ${MAX_OUTPUT_BYTES} bytes — process killed`);
        }
      });

      proc.on('error', (err) => {
        if (killed) return;
        reject(new Error(`Claude CLI spawn error: ${err.message}`));
      });

      proc.on('close', (code, signal) => {
        if (killed) return;

        if (signal === 'SIGTERM') {
          reject(new Error('Claude CLI timed out after 5 minutes'));
          return;
        }

        if (code !== 0) {
          reject(new Error(`Claude CLI exited with code ${code}: ${stderr || stdout}`));
          return;
        }

        try {
          const parsed = JSON.parse(stdout) as CliJsonResult;
          if (parsed.is_error) {
            reject(new Error(`Claude CLI returned error: ${parsed.result}`));
            return;
          }
          resolve(parsed);
        } catch (err) {
          const preview = stdout.length > 300 ? stdout.slice(0, 300) + '...' : stdout;
          reject(new Error(`Failed to parse Claude CLI output: ${(err as Error).message}\nOutput: ${preview}`));
        }
      });
    });
  }
}
