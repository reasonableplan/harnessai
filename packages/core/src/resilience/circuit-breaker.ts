import { createLogger } from '../logging/logger.js';
import { CircuitBreakerError } from '../errors.js';

const log = createLogger('CircuitBreaker');

export type CircuitState = 'CLOSED' | 'OPEN' | 'HALF_OPEN';

export interface CircuitBreakerConfig {
  /** 서킷 이름 (로그용) */
  name: string;
  /** OPEN 전환까지 연속 실패 횟수 (기본 5) */
  failureThreshold?: number;
  /** OPEN → HALF_OPEN 대기 시간 ms (기본 30초) */
  resetTimeoutMs?: number;
  /** HALF_OPEN에서 허용할 시도 횟수 (기본 1) */
  halfOpenAttempts?: number;
}

/**
 * 서킷 브레이커 — 외부 서비스 장애 시 빠른 실패.
 * CLOSED → (연속 실패) → OPEN → (타임아웃) → HALF_OPEN → (성공) → CLOSED
 */
export class CircuitBreaker {
  private state: CircuitState = 'CLOSED';
  private failures = 0;
  private lastFailureTime = 0;
  private halfOpenSuccesses = 0;

  private readonly failureThreshold: number;
  private readonly resetTimeoutMs: number;
  private readonly halfOpenAttempts: number;
  private readonly name: string;

  constructor(config: CircuitBreakerConfig) {
    this.name = config.name;
    this.failureThreshold = config.failureThreshold ?? 5;
    this.resetTimeoutMs = config.resetTimeoutMs ?? 30_000;
    this.halfOpenAttempts = config.halfOpenAttempts ?? 1;
  }

  getState(): CircuitState {
    return this.state;
  }

  /**
   * 서킷 브레이커를 통해 함수를 실행한다.
   * OPEN 상태면 즉시 에러를 던진다.
   */
  async execute<T>(fn: () => Promise<T>): Promise<T> {
    if (this.state === 'OPEN') {
      // 타임아웃 경과 시 HALF_OPEN으로 전환
      if (Date.now() - this.lastFailureTime >= this.resetTimeoutMs) {
        this.state = 'HALF_OPEN';
        this.halfOpenSuccesses = 0;
        log.info({ circuit: this.name }, 'Circuit half-open, allowing probe request');
      } else {
        throw new CircuitBreakerError(this.name);
      }
    }

    try {
      const result = await fn();
      this.onSuccess();
      return result;
    } catch (error) {
      this.onFailure();
      throw error;
    }
  }

  private onSuccess(): void {
    if (this.state === 'HALF_OPEN') {
      this.halfOpenSuccesses++;
      if (this.halfOpenSuccesses >= this.halfOpenAttempts) {
        this.state = 'CLOSED';
        this.failures = 0;
        log.info({ circuit: this.name }, 'Circuit closed (recovered)');
      }
    } else {
      this.failures = 0;
    }
  }

  private onFailure(): void {
    this.failures++;

    if (this.state === 'HALF_OPEN') {
      this.lastFailureTime = Date.now();
      this.state = 'OPEN';
      log.warn({ circuit: this.name }, 'Circuit re-opened (half-open probe failed)');
    } else if (this.failures >= this.failureThreshold) {
      this.lastFailureTime = Date.now();
      this.state = 'OPEN';
      log.warn({ circuit: this.name, failures: this.failures }, 'Circuit opened');
    }
  }

  /** 수동 리셋 (테스트/관리용) */
  reset(): void {
    this.state = 'CLOSED';
    this.failures = 0;
    this.halfOpenSuccesses = 0;
  }
}
