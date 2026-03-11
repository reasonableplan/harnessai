import Anthropic from '@anthropic-ai/sdk';
import { createLogger } from '@agent/core';

const log = createLogger('ClaudeClient');

export interface ClaudeClientConfig {
  model: string;
  maxTokens: number;
  temperature: number;
  maxRetries?: number;
}

interface ClaudeResponse {
  content: string;
  usage: { inputTokens: number; outputTokens: number };
}

const DEFAULT_MAX_RETRIES = 3;
const BASE_DELAY_MS = 1000;
const JITTER_FACTOR = 0.2; // 0~20% 랜덤 jitter

export class ClaudeClient {
  private client: Anthropic;
  private config: ClaudeClientConfig;

  constructor(config: ClaudeClientConfig, apiKey?: string) {
    this.client = new Anthropic({ apiKey: apiKey ?? process.env.ANTHROPIC_API_KEY });
    this.config = config;
  }

  async chatJSON<T>(systemPrompt: string, userMessage: string): Promise<{ data: T; usage: ClaudeResponse['usage'] }> {
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

    const jsonStr = ClaudeClient.extractJSON(response.content);
    const data = JSON.parse(jsonStr) as T;
    return { data, usage: response.usage };
  }

  static extractJSON(text: string): string {
    const codeBlockMatch = text.match(/```(?:json)?\s*\n?([\s\S]*?)\n?```/);
    if (codeBlockMatch) return codeBlockMatch[1].trim();

    const firstBrace = text.indexOf('{');
    const firstBracket = text.indexOf('[');

    const startIdx = (firstBracket !== -1 && (firstBrace === -1 || firstBracket < firstBrace))
      ? firstBracket
      : firstBrace;

    if (startIdx !== -1) {
      const extracted = ClaudeClient.extractBalancedJSON(text, startIdx);
      if (extracted) return extracted;
    }

    return text.trim();
  }

  private static extractBalancedJSON(text: string, start: number): string | null {
    const open = text[start];
    const close = open === '{' ? '}' : ']';
    let depth = 0;
    let inString = false;
    let escape = false;

    for (let i = start; i < text.length; i++) {
      const ch = text[i];
      if (escape) { escape = false; continue; }
      if (ch === '\\' && inString) { escape = true; continue; }
      if (ch === '"') { inString = !inString; continue; }
      if (inString) continue;
      if (ch === open) depth++;
      else if (ch === close) { depth--; if (depth === 0) return text.slice(start, i + 1); }
    }

    return null;
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
          log.warn({ attempt: attempt + 1, maxRetries, delayMs: Math.round(delay), err: lastError.message }, 'Retrying');
          await new Promise((r) => setTimeout(r, delay));
        }
      }
    }

    throw lastError!;
  }

  private isRetryable(error: Error): boolean {
    const msg = error.message.toLowerCase();
    if (msg.includes('rate limit') || msg.includes('429')) return true;
    if (msg.includes('timeout') || msg.includes('timed out')) return true;
    if (msg.includes('network') || msg.includes('econnreset') || msg.includes('socket')) return true;
    if (msg.includes('500') || msg.includes('502') || msg.includes('503') || msg.includes('529')) return true;
    if (msg.includes('401') || msg.includes('403') || msg.includes('invalid')) return false;
    return true; // unknown errors → retry (Director와 동일)
  }
}
