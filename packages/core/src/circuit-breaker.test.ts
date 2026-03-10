import { describe, it, expect, vi } from 'vitest';
import { CircuitBreaker } from './circuit-breaker.js';

describe('CircuitBreaker', () => {
  it('CLOSED 상태에서 정상 호출이 성공한다', async () => {
    const cb = new CircuitBreaker({ name: 'test' });
    const result = await cb.execute(() => Promise.resolve('ok'));
    expect(result).toBe('ok');
    expect(cb.getState()).toBe('CLOSED');
  });

  it('연속 실패가 threshold에 도달하면 OPEN으로 전환한다', async () => {
    const cb = new CircuitBreaker({ name: 'test', failureThreshold: 3 });

    for (let i = 0; i < 3; i++) {
      await expect(cb.execute(() => Promise.reject(new Error('fail')))).rejects.toThrow();
    }

    expect(cb.getState()).toBe('OPEN');
  });

  it('OPEN 상태에서 요청이 즉시 거부된다', async () => {
    const cb = new CircuitBreaker({ name: 'test', failureThreshold: 1, resetTimeoutMs: 60_000 });

    await expect(cb.execute(() => Promise.reject(new Error('fail')))).rejects.toThrow();
    expect(cb.getState()).toBe('OPEN');

    await expect(cb.execute(() => Promise.resolve('ok'))).rejects.toThrow('Circuit breaker "test" is OPEN');
  });

  it('resetTimeout 후 HALF_OPEN으로 전환되어 probe 요청을 허용한다', async () => {
    const cb = new CircuitBreaker({ name: 'test', failureThreshold: 1, resetTimeoutMs: 10 });

    await expect(cb.execute(() => Promise.reject(new Error('fail')))).rejects.toThrow();
    expect(cb.getState()).toBe('OPEN');

    // 타임아웃 대기
    await new Promise((r) => setTimeout(r, 20));

    const result = await cb.execute(() => Promise.resolve('recovered'));
    expect(result).toBe('recovered');
    expect(cb.getState()).toBe('CLOSED');
  });

  it('HALF_OPEN에서 probe가 실패하면 다시 OPEN으로 전환한다', async () => {
    const cb = new CircuitBreaker({ name: 'test', failureThreshold: 1, resetTimeoutMs: 10 });

    await expect(cb.execute(() => Promise.reject(new Error('fail')))).rejects.toThrow();
    await new Promise((r) => setTimeout(r, 20));

    await expect(cb.execute(() => Promise.reject(new Error('still failing')))).rejects.toThrow();
    expect(cb.getState()).toBe('OPEN');
  });

  it('성공 시 실패 카운터가 리셋된다', async () => {
    const cb = new CircuitBreaker({ name: 'test', failureThreshold: 3 });

    // 2번 실패 후 1번 성공
    await expect(cb.execute(() => Promise.reject(new Error('fail')))).rejects.toThrow();
    await expect(cb.execute(() => Promise.reject(new Error('fail')))).rejects.toThrow();
    await cb.execute(() => Promise.resolve('ok'));

    // 다시 2번 실패해도 OPEN 안 됨 (카운터 리셋됨)
    await expect(cb.execute(() => Promise.reject(new Error('fail')))).rejects.toThrow();
    await expect(cb.execute(() => Promise.reject(new Error('fail')))).rejects.toThrow();
    expect(cb.getState()).toBe('CLOSED');
  });

  it('reset()으로 수동 리셋할 수 있다', async () => {
    const cb = new CircuitBreaker({ name: 'test', failureThreshold: 1 });

    await expect(cb.execute(() => Promise.reject(new Error('fail')))).rejects.toThrow();
    expect(cb.getState()).toBe('OPEN');

    cb.reset();
    expect(cb.getState()).toBe('CLOSED');

    const result = await cb.execute(() => Promise.resolve('ok'));
    expect(result).toBe('ok');
  });
});
