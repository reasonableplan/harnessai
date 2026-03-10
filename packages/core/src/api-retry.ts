import { createLogger } from './logger.js';

const log = createLogger('ApiRetry');

export interface RetryConfig {
  maxRetries?: number;
  baseDelayMs?: number;
  maxDelayMs?: number;
}

/**
 * GitHub API 등 외부 API 호출에 지수 백오프 + 지터 재시도를 적용한다.
 */
export async function withRetry<T>(
  fn: () => Promise<T>,
  config: RetryConfig = {},
  label = 'API call',
): Promise<T> {
  const { maxRetries = 3, baseDelayMs = 1000, maxDelayMs = 15_000 } = config;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      if (attempt >= maxRetries || !isRetryable(error)) {
        throw error;
      }

      const delay = Math.min(baseDelayMs * Math.pow(2, attempt), maxDelayMs);
      const jitter = delay * (0.5 + Math.random() * 0.5);

      log.warn(
        { attempt: attempt + 1, maxRetries, delayMs: Math.round(jitter), label },
        'Retrying after error',
      );

      await new Promise((r) => setTimeout(r, jitter));
    }
  }

  // TypeScript: unreachable but satisfies return type
  throw new Error('Unreachable');
}

function isRetryable(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  const msg = error.message.toLowerCase();

  // 네트워크/서버 에러
  if (msg.includes('econnreset') || msg.includes('socket') || msg.includes('timeout')) return true;
  if (msg.includes('network') || msg.includes('fetch failed')) return true;

  // HTTP 서버 에러
  if (msg.includes('500') || msg.includes('502') || msg.includes('503') || msg.includes('504')) return true;

  // Rate limit
  if (msg.includes('rate limit') || msg.includes('429') || msg.includes('secondary rate')) return true;

  // 인증/권한 에러는 재시도 불가
  if (msg.includes('401') || msg.includes('403') || msg.includes('404')) return false;

  return false;
}
