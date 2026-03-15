"""
커스텀 에러 계층. isinstance로 에러 분류 가능.

AgentError (base)
├── ConfigError          — 환경변수/설정 누락
├── TokenBudgetError     — 토큰 예산 초과
├── TaskClaimError       — 태스크 선점 실패
├── CircuitBreakerError  — 서킷 브레이커 OPEN
├── SandboxEscapeError   — workDir 밖 경로 접근 시도
├── SyntaxValidationError— 생성 코드 구문 검증 실패
├── ApiError             — 외부 API 호출 실패 (base)
│   ├── RateLimitError   — 429
│   ├── AuthError        — 401/403
│   └── NetworkError     — 네트워크/타임아웃
└── GitServiceError      — GitHub API 에러
"""


class AgentError(Exception):
    def __init__(self, message: str, code: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.cause = cause


class ConfigError(AgentError):
    def __init__(self, message: str, cause: Exception | None = None) -> None:
        super().__init__(message, "CONFIG_ERROR", cause)


class TokenBudgetError(AgentError):
    def __init__(self, used: int, budget: int) -> None:
        super().__init__(
            f"Token budget exhausted: used {used} / {budget} tokens",
            "TOKEN_BUDGET_EXHAUSTED",
        )
        self.used = used
        self.budget = budget


class TaskClaimError(AgentError):
    def __init__(self, task_id: str) -> None:
        super().__init__(f"Failed to claim task: {task_id}", "TASK_CLAIM_FAILED")


class CircuitBreakerError(AgentError):
    def __init__(self, service: str) -> None:
        super().__init__(f"Circuit breaker OPEN for service: {service}", "CIRCUIT_BREAKER_OPEN")


class SandboxEscapeError(AgentError):
    def __init__(self, path: str, work_dir: str) -> None:
        super().__init__(
            f"Path escapes sandbox: {path} (workDir: {work_dir})",
            "SANDBOX_ESCAPE",
        )


class SyntaxValidationError(AgentError):
    def __init__(self, file_path: str, reason: str) -> None:
        super().__init__(
            f"Syntax validation failed for {file_path}: {reason}",
            "SYNTAX_VALIDATION_FAILED",
        )
        self.reason = reason


# ===== API Errors =====


class ApiError(AgentError):
    def __init__(
        self,
        message: str,
        code: str,
        status_code: int | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message, code, cause)
        self.status_code = status_code

    @property
    def retryable(self) -> bool:
        return False


class RateLimitError(ApiError):
    def __init__(self, service: str, cause: Exception | None = None) -> None:
        super().__init__(f"Rate limited by {service}", "RATE_LIMIT", 429, cause)

    @property
    def retryable(self) -> bool:
        return True


class AuthError(ApiError):
    def __init__(self, service: str, status_code: int = 401, cause: Exception | None = None) -> None:
        super().__init__(f"Authentication failed for {service}", "AUTH_ERROR", status_code, cause)


class NetworkError(ApiError):
    def __init__(self, message: str, cause: Exception | None = None) -> None:
        super().__init__(message, "NETWORK_ERROR", None, cause)

    @property
    def retryable(self) -> bool:
        return True


class GitServiceError(AgentError):
    def __init__(self, operation: str, cause: Exception | None = None) -> None:
        super().__init__(f"GitService operation failed: {operation}", "GIT_SERVICE_ERROR", cause)
