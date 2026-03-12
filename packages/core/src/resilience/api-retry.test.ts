import { describe, it, expect, vi } from 'vitest';
import { withRetry } from './api-retry.js';

describe('withRetry', () => {
  it('성공 시 바로 결과를 반환한다', async () => {
    const fn = vi.fn().mockResolvedValue('ok');
    const result = await withRetry(fn, { maxRetries: 3, baseDelayMs: 1 });
    expect(result).toBe('ok');
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it('일시적 에러 시 재시도한다', async () => {
    const fn = vi.fn().mockRejectedValueOnce(new Error('socket hang up')).mockResolvedValue('ok');

    const result = await withRetry(fn, { maxRetries: 3, baseDelayMs: 1 });
    expect(result).toBe('ok');
    expect(fn).toHaveBeenCalledTimes(2);
  });

  it('재시도 불가능한 에러는 즉시 throw한다', async () => {
    const fn = vi.fn().mockRejectedValue(new Error('401 Unauthorized'));

    await expect(withRetry(fn, { maxRetries: 3, baseDelayMs: 1 })).rejects.toThrow('401');
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it('최대 재시도 초과 시 마지막 에러를 throw한다', async () => {
    const fn = vi.fn().mockRejectedValue(new Error('503 Service Unavailable'));

    await expect(withRetry(fn, { maxRetries: 2, baseDelayMs: 1 })).rejects.toThrow('503');
    expect(fn).toHaveBeenCalledTimes(3); // 1 initial + 2 retries
  });

  it('rate limit(429) 에러 시 재시도한다', async () => {
    const fn = vi
      .fn()
      .mockRejectedValueOnce(new Error('429 rate limit exceeded'))
      .mockResolvedValue('ok');

    const result = await withRetry(fn, { maxRetries: 3, baseDelayMs: 1 });
    expect(result).toBe('ok');
    expect(fn).toHaveBeenCalledTimes(2);
  });
});
