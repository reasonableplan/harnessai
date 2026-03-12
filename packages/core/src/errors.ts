/**
 * 커스텀 에러 계층. instanceof로 에러 분류 가능.
 *
 * AgentError (base)
 * ├── ConfigError          — 환경변수/설정 누락
 * ├── TokenBudgetError     — 토큰 예산 초과
 * ├── TaskClaimError       — 태스크 선점 실패
 * ├── CircuitBreakerError  — 서킷 브레이커 OPEN
 * ├── SandboxEscapeError   — workDir 밖 경로 접근 시도
 * ├── SyntaxValidationError— 생성 코드 구문 검증 실패
 * ├── ApiError             — 외부 API 호출 실패 (base)
 * │   ├── RateLimitError   — 429
 * │   ├── AuthError        — 401/403
 * │   └── NetworkError     — 네트워크/타임아웃
 * └── GitServiceError      — GitHub API 에러
 */

export class AgentError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly cause?: Error,
  ) {
    super(message);
    this.name = 'AgentError';
  }
}

export class ConfigError extends AgentError {
  constructor(message: string, cause?: Error) {
    super(message, 'CONFIG_ERROR', cause);
    this.name = 'ConfigError';
  }
}

export class TokenBudgetError extends AgentError {
  constructor(
    public readonly used: number,
    public readonly budget: number,
  ) {
    super(`Token budget exhausted: used ${used} / ${budget} tokens`, 'TOKEN_BUDGET_EXHAUSTED');
    this.name = 'TokenBudgetError';
  }
}

export class TaskClaimError extends AgentError {
  constructor(taskId: string) {
    super(`Failed to claim task: ${taskId}`, 'TASK_CLAIM_FAILED');
    this.name = 'TaskClaimError';
  }
}

export class CircuitBreakerError extends AgentError {
  constructor(service: string) {
    super(`Circuit breaker OPEN for service: ${service}`, 'CIRCUIT_BREAKER_OPEN');
    this.name = 'CircuitBreakerError';
  }
}

export class SandboxEscapeError extends AgentError {
  constructor(path: string, workDir: string) {
    super(`Path escapes sandbox: ${path} (workDir: ${workDir})`, 'SANDBOX_ESCAPE');
    this.name = 'SandboxEscapeError';
  }
}

export class SyntaxValidationError extends AgentError {
  constructor(
    filePath: string,
    public readonly reason: string,
  ) {
    super(`Syntax validation failed for ${filePath}: ${reason}`, 'SYNTAX_VALIDATION_FAILED');
    this.name = 'SyntaxValidationError';
  }
}

// ===== API Errors =====

export class ApiError extends AgentError {
  constructor(
    message: string,
    code: string,
    public readonly statusCode?: number,
    cause?: Error,
  ) {
    super(message, code, cause);
    this.name = 'ApiError';
  }

  get retryable(): boolean {
    return false;
  }
}

export class RateLimitError extends ApiError {
  constructor(service: string, cause?: Error) {
    super(`Rate limited by ${service}`, 'RATE_LIMIT', 429, cause);
    this.name = 'RateLimitError';
  }

  override get retryable(): boolean {
    return true;
  }
}

export class AuthError extends ApiError {
  constructor(service: string, statusCode: number = 401, cause?: Error) {
    super(`Authentication failed for ${service}`, 'AUTH_ERROR', statusCode, cause);
    this.name = 'AuthError';
  }
}

export class NetworkError extends ApiError {
  constructor(message: string, cause?: Error) {
    super(message, 'NETWORK_ERROR', undefined, cause);
    this.name = 'NetworkError';
  }

  override get retryable(): boolean {
    return true;
  }
}

export class GitServiceError extends AgentError {
  constructor(
    operation: string,
    cause?: Error,
  ) {
    super(`GitService operation failed: ${operation}`, 'GIT_SERVICE_ERROR', cause);
    this.name = 'GitServiceError';
  }
}
