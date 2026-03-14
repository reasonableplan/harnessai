import { createLogger } from '../logging/logger.js';
import { TokenBudgetError } from '../errors.js';
import { withRetry } from '../resilience/api-retry.js';
import { parseJSONResponse } from './json-extract.js';
import type { IClaudeClient, ClaudeResponse } from './claude-client.js';

const log = createLogger('LocalModelClient');

export interface LocalModelClientConfig {
  /** OpenAI 호환 API base URL (예: http://localhost:11434/v1, https://api-inference.huggingface.co/models/meta-llama/Llama-3.1-70B-Instruct/v1) */
  baseUrl: string;
  /** 모델 이름 (예: llama3.1, codellama, deepseek-coder, tgi) */
  model: string;
  maxTokens: number;
  temperature?: number;
  /** API 키. 로컬 모델은 불필요, HuggingFace/OpenRouter 등 클라우드 서비스는 필수. */
  apiKey?: string;
  /** Token budget. 0 = unlimited. */
  tokenBudget?: number;
  /** 요청 타임아웃 (ms). 기본 5분. 로컬 모델은 느릴 수 있다. */
  timeoutMs?: number;
}

/** OpenAI Chat Completion 응답 형식 */
interface ChatCompletionResponse {
  id: string;
  choices: Array<{
    index: number;
    message: { role: string; content: string };
    finish_reason: string;
  }>;
  usage?: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
}

/**
 * OpenAI 호환 API를 사용하는 범용 모델 클라이언트.
 * 로컬 모델과 OpenAI 호환 클라우드 서비스 모두 지원.
 *
 * 설정 예시:
 * - Ollama: baseUrl='http://localhost:11434/v1', model='llama3.1'
 * - LM Studio: baseUrl='http://localhost:1234/v1', model='local-model'
 * - vLLM: baseUrl='http://localhost:8000/v1', model='meta-llama/...'
 * - HuggingFace: baseUrl='https://api-inference.huggingface.co/models/{model}/v1', model='tgi', apiKey='hf_...'
 * - OpenRouter: baseUrl='https://openrouter.ai/api/v1', model='meta-llama/llama-3.1-70b', apiKey='sk-or-...'
 */
/** SSRF 방어: 클라우드 메타데이터 엔드포인트 차단 */
const BLOCKED_HOSTS = new Set([
  '169.254.169.254',       // AWS EC2 metadata
  'metadata.google.internal', // GCP metadata
  '100.100.100.200',       // Alibaba Cloud metadata
  'fd00:ec2::254',         // AWS EC2 metadata (IPv6)
]);

function validateBaseUrl(baseUrl: string): void {
  let parsed: URL;
  try {
    parsed = new URL(baseUrl);
  } catch {
    throw new Error(`Invalid LOCAL_MODEL_BASE_URL: ${baseUrl}`);
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    throw new Error(`Unsupported protocol in LOCAL_MODEL_BASE_URL: ${parsed.protocol} (only http/https allowed)`);
  }
  if (BLOCKED_HOSTS.has(parsed.hostname)) {
    throw new Error(`Blocked SSRF target in LOCAL_MODEL_BASE_URL: ${parsed.hostname}`);
  }
}

export class LocalModelClient implements IClaudeClient {
  private config: LocalModelClientConfig;
  private totalTokensUsed = 0;

  constructor(config: LocalModelClientConfig) {
    validateBaseUrl(config.baseUrl);
    this.config = config;
    log.debug(
      { baseUrl: config.baseUrl, model: config.model },
      'Local model client initialized',
    );
  }

  get tokensUsed(): number {
    return this.totalTokensUsed;
  }

  async chat(systemPrompt: string, userMessage: string): Promise<ClaudeResponse> {
    const budget = this.config.tokenBudget ?? 0;
    if (budget > 0 && this.totalTokensUsed >= budget) {
      throw new TokenBudgetError(this.totalTokensUsed, budget);
    }

    const response = await withRetry(
      () => this.callApi(systemPrompt, userMessage),
      { maxRetries: 2, baseDelayMs: 1000, maxDelayMs: 10_000 },
      'Local Model',
    );

    this.totalTokensUsed += response.usage.inputTokens + response.usage.outputTokens;

    log.info(
      {
        inputTokens: response.usage.inputTokens,
        outputTokens: response.usage.outputTokens,
        totalUsed: this.totalTokensUsed,
      },
      'Local model usage',
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

    const data = parseJSONResponse<T>(response.content, 'local model');
    return { data, usage: response.usage };
  }

  private async callApi(systemPrompt: string, userMessage: string): Promise<ClaudeResponse> {
    const url = `${this.config.baseUrl.replace(/\/+$/, '')}/chat/completions`;
    const timeoutMs = this.config.timeoutMs ?? 5 * 60 * 1000;

    const body = {
      model: this.config.model,
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: userMessage },
      ],
      max_tokens: this.config.maxTokens,
      temperature: this.config.temperature ?? 0.2,
      stream: false,
    };

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (this.config.apiKey) {
        headers['Authorization'] = `Bearer ${this.config.apiKey}`;
      }

      const res = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!res.ok) {
        const errText = await res.text().catch(() => '');
        throw new Error(`Local model API error ${res.status}: ${errText.slice(0, 200)}`);
      }

      const data = await res.json() as ChatCompletionResponse;

      const content = data.choices[0]?.message?.content ?? '';
      const usage = {
        inputTokens: data.usage?.prompt_tokens ?? 0,
        outputTokens: data.usage?.completion_tokens ?? 0,
      };

      return { content, usage };
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') {
        throw new Error(`Local model request timed out after ${timeoutMs}ms`, { cause: err });
      }
      throw err;
    } finally {
      clearTimeout(timeout);
    }
  }
}
