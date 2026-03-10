import Anthropic from '@anthropic-ai/sdk';
import { createLogger } from '@agent/core';

const log = createLogger('ClaudeClient');

export interface ClaudeResponse {
  content: string;
  usage: { inputTokens: number; outputTokens: number };
}

export interface ClaudeClientConfig {
  model: string;
  maxTokens: number;
  temperature: number;
  /** 최대 재시도 횟수 (기본 3) */
  maxRetries?: number;
}

const DEFAULT_MAX_RETRIES = 3;
const BASE_DELAY_MS = 1000;

/**
 * Claude API 래퍼. Director가 사용하는 유일한 LLM 인터페이스.
 * 테스트 시 이 클래스를 mock으로 대체한다.
 */
export class ClaudeClient {
  private client: Anthropic;
  private config: ClaudeClientConfig;

  constructor(config: ClaudeClientConfig, apiKey?: string) {
    this.client = new Anthropic({ apiKey: apiKey ?? process.env.ANTHROPIC_API_KEY });
    this.config = config;
  }

  async chat(systemPrompt: string, userMessage: string): Promise<ClaudeResponse> {
    return this.withRetry(async () => {
      const response = await this.client.messages.create({
        model: this.config.model,
        max_tokens: this.config.maxTokens,
        temperature: this.config.temperature,
        system: systemPrompt,
        messages: [{ role: 'user', content: userMessage }],
      });

      const textBlock = response.content.find((b) => b.type === 'text');
      const content = textBlock ? textBlock.text : '';

      return {
        content,
        usage: {
          inputTokens: response.usage.input_tokens,
          outputTokens: response.usage.output_tokens,
        },
      };
    });
  }

  /**
   * JSON 구조화 응답을 요청한다. Claude에게 JSON만 반환하도록 지시.
   * 마크다운 코드블록이나 서문이 포함되어도 JSON 부분만 추출한다.
   */
  async chatJSON<T>(systemPrompt: string, userMessage: string): Promise<{ data: T; usage: ClaudeResponse['usage'] }> {
    const response = await this.chat(
      systemPrompt + '\n\nIMPORTANT: Respond with valid JSON only. No markdown, no explanation.',
      userMessage,
    );

    const jsonStr = ClaudeClient.extractJSON(response.content);
    const data = JSON.parse(jsonStr) as T;
    return { data, usage: response.usage };
  }

  /**
   * 응답에서 JSON 부분만 추출한다.
   * - 마크다운 코드블록 (```json ... ```) 처리
   * - 서문/후문 텍스트 제거
   * - 순수 JSON은 그대로 반환
   */
  static extractJSON(text: string): string {
    // 1. 마크다운 코드블록에서 추출
    const codeBlockMatch = text.match(/```(?:json)?\s*\n?([\s\S]*?)\n?```/);
    if (codeBlockMatch) {
      return codeBlockMatch[1].trim();
    }

    // 2. 첫 번째 JSON 구조 감지 (배열이 먼저 나오면 배열, 객체가 먼저 나오면 객체)
    const firstBrace = text.indexOf('{');
    const firstBracket = text.indexOf('[');

    if (firstBracket !== -1 && (firstBrace === -1 || firstBracket < firstBrace)) {
      // 배열이 먼저 → [ ... ] 추출
      const arrayMatch = text.match(/\[[\s\S]*\]/);
      if (arrayMatch) return arrayMatch[0];
    }

    if (firstBrace !== -1) {
      // 객체 → { ... } 추출
      const objectMatch = text.match(/\{[\s\S]*\}/);
      if (objectMatch) return objectMatch[0];
    }

    // 4. 그대로 반환 (JSON.parse가 에러를 던질 것)
    return text.trim();
  }

  /**
   * 지수 백오프 재시도. Rate limit, 네트워크 에러 등 일시적 오류 대응.
   */
  private async withRetry<T>(fn: () => Promise<T>): Promise<T> {
    const maxRetries = this.config.maxRetries ?? DEFAULT_MAX_RETRIES;
    let lastError: Error | null = null;

    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        return await fn();
      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error));

        // 재시도 불가능한 에러 (인증 실패, 잘못된 요청 등)는 즉시 throw
        if (!this.isRetryable(lastError)) {
          throw lastError;
        }

        if (attempt < maxRetries) {
          const delay = BASE_DELAY_MS * Math.pow(2, attempt);
          log.warn({ attempt: attempt + 1, maxRetries, delayMs: delay, err: lastError.message }, 'Retrying');
          await new Promise((r) => setTimeout(r, delay));
        }
      }
    }

    throw lastError!;
  }

  private isRetryable(error: Error): boolean {
    const msg = error.message.toLowerCase();
    // Rate limit, timeout, network errors → retryable
    if (msg.includes('rate limit') || msg.includes('429')) return true;
    if (msg.includes('timeout') || msg.includes('timed out')) return true;
    if (msg.includes('network') || msg.includes('econnreset') || msg.includes('socket')) return true;
    if (msg.includes('500') || msg.includes('502') || msg.includes('503') || msg.includes('529')) return true;
    // Auth errors, bad request → not retryable
    if (msg.includes('401') || msg.includes('403') || msg.includes('invalid')) return false;
    // Default: retry
    return true;
  }
}
