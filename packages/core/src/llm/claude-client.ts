import Anthropic from '@anthropic-ai/sdk';
import { createLogger } from '../logging/logger.js';
import { TokenBudgetError, RateLimitError, AuthError, NetworkError } from '../errors.js';
import { parseJSONResponse } from './json-extract.js';

const log = createLogger('ClaudeClient');

export interface ClaudeResponse {
  content: string;
  usage: { inputTokens: number; outputTokens: number };
}

/**
 * Claude API 클라이언트 인터페이스. 테스트에서 mock 주입 가능.
 */
export interface IClaudeClient {
  /** 현재까지 사용한 총 토큰 수 */
  readonly tokensUsed: number;

  chatJSON<T>(
    systemPrompt: string,
    userMessage: string,
  ): Promise<{
    data: T;
    usage: ClaudeResponse['usage'];
  }>;

  chat(
    systemPrompt: string,
    userMessage: string,
  ): Promise<ClaudeResponse>;
}

export interface ClaudeClientConfig {
  model: string;
  maxTokens: number;
  temperature: number;
  maxRetries?: number;
  /** Token budget. 0 = unlimited. */
  tokenBudget?: number;
}

const DEFAULT_MAX_RETRIES = 3;
const BASE_DELAY_MS = 1000;
const JITTER_FACTOR = 0.2; // 0~20% 랜덤 jitter

/**
 * Anthropic Claude API 공유 클라이언트.
 * Worker Agent들이 공통으로 사용한다. Token budget 추적 포함.
 */
export class ClaudeClient implements IClaudeClient {
  private client: Anthropic;
  private config: ClaudeClientConfig;
  private totalTokensUsed = 0;

  constructor(config: ClaudeClientConfig, apiKey: string) {
    this.client = new Anthropic({ apiKey });
    this.config = config;
  }

  /** 현재까지 사용한 총 토큰 수 */
  get tokensUsed(): number {
    return this.totalTokensUsed;
  }

  async chat(systemPrompt: string, userMessage: string): Promise<ClaudeResponse> {
    // Token budget 체크
    const budget = this.config.tokenBudget ?? 0;
    if (budget > 0 && this.totalTokensUsed >= budget) {
      throw new TokenBudgetError(this.totalTokensUsed, budget);
    }

    const response = await this.withRetry(async () => {
      const result = await this.client.messages.create({
        model: this.config.model,
        max_tokens: this.config.maxTokens,
        temperature: this.config.temperature,
        system: systemPrompt,
        messages: [{ role: 'user', content: userMessage }],
      });

      const textBlock = result.content.find((b) => b.type === 'text');
      return {
        content: textBlock ? textBlock.text : '',
        usage: { inputTokens: result.usage.input_tokens, outputTokens: result.usage.output_tokens },
      };
    });

    // Token 사용량 누적
    this.totalTokensUsed += response.usage.inputTokens + response.usage.outputTokens;
    log.info(
      { inputTokens: response.usage.inputTokens, outputTokens: response.usage.outputTokens, totalUsed: this.totalTokensUsed },
      'Claude usage',
    );

    return response;
  }

  async chatJSON<T>(
    systemPrompt: string,
    userMessage: string,
  ): Promise<{ data: T; usage: ClaudeResponse['usage'] }> {
    const response = await this.chat(
      systemPrompt + '\n\nIMPORTANT: Respond with valid JSON only. No markdown, no explanation.',
      userMessage,
    );

    const data = parseJSONResponse<T>(response.content, 'Claude');
    return { data, usage: response.usage };
  }

  private async withRetry<T>(fn: () => Promise<T>): Promise<T> {
    const maxRetries = this.config.maxRetries ?? DEFAULT_MAX_RETRIES;
    let lastError: Error | null = null;

    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        return await fn();
      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error));
        if (!this.isRetryable(lastError)) throw lastError;
        if (attempt < maxRetries) {
          const jitter = 1 + Math.random() * JITTER_FACTOR;
          const delay = BASE_DELAY_MS * Math.pow(2, attempt) * jitter;
          log.warn(
            {
              attempt: attempt + 1,
              maxRetries,
              delayMs: Math.round(delay),
              err: lastError.message,
            },
            'Retrying',
          );
          await new Promise((r) => setTimeout(r, delay));
        }
      }
    }

    throw lastError!;
  }

  private isRetryable(error: Error): boolean {
    // 커스텀 에러 타입 우선 체크
    if (error instanceof RateLimitError || error instanceof NetworkError) return true;
    if (error instanceof AuthError || error instanceof TokenBudgetError) return false;

    // Anthropic SDK 에러 또는 알 수 없는 에러 → 메시지 기반 판별
    const msg = error.message.toLowerCase();
    if (msg.includes('rate limit') || msg.includes('429')) return true;
    if (msg.includes('timeout') || msg.includes('timed out')) return true;
    if (msg.includes('network') || msg.includes('econnreset') || msg.includes('socket'))
      return true;
    // 단어 경계(\b)로 숫자가 다른 문자열의 일부일 때 false positive 방지
    if (/\b5\d{2}\b/.test(msg)) return true;
    if (msg.includes('401') || msg.includes('403') || msg.includes('invalid')) return false;
    return false; // unknown errors → do not retry (안전한 기본값)
  }
}
