from __future__ import annotations

import time
from enum import Enum
from typing import Awaitable, Callable, TypeVar, Union

from src.core.errors import CircuitBreakerError
from src.core.logging.logger import get_logger

log = get_logger("CircuitBreaker")

T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """
    외부 서비스 장애 시 빠른 실패 패턴.
    CLOSED → (연속 실패) → OPEN → (타임아웃) → HALF_OPEN → (성공) → CLOSED
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        reset_timeout_ms: int = 30_000,
        half_open_attempts: int = 1,
    ) -> None:
        self.name = name
        self._failure_threshold = failure_threshold
        self._reset_timeout_ms = reset_timeout_ms
        self._half_open_attempts = half_open_attempts

        self._state = CircuitState.CLOSED
        self._failures = 0
        self._last_failure_time: float = 0.0
        self._half_open_successes = 0

    @property
    def state(self) -> CircuitState:
        return self._state

    async def execute(self, fn: Callable[[], Union[Awaitable[T], T]]) -> T:
        if self._state == CircuitState.OPEN:
            elapsed_ms = (time.monotonic() - self._last_failure_time) * 1000
            if elapsed_ms >= self._reset_timeout_ms:
                self._state = CircuitState.HALF_OPEN
                self._half_open_successes = 0
                self._failures = 0
                log.info("Circuit half-open, allowing probe request", circuit=self.name)
            else:
                raise CircuitBreakerError(self.name)

        try:
            import asyncio
            result = fn()
            if asyncio.iscoroutine(result):
                result = await result
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        if self._state == CircuitState.HALF_OPEN:
            self._half_open_successes += 1
            if self._half_open_successes >= self._half_open_attempts:
                self._state = CircuitState.CLOSED
                self._failures = 0
                log.info("Circuit closed (recovered)", circuit=self.name)
        else:
            self._failures = 0

    def _on_failure(self) -> None:
        self._failures += 1
        if self._state == CircuitState.HALF_OPEN:
            self._last_failure_time = time.monotonic()
            self._state = CircuitState.OPEN
            log.warn("Circuit re-opened (half-open probe failed)", circuit=self.name)
        elif self._failures >= self._failure_threshold:
            self._last_failure_time = time.monotonic()
            self._state = CircuitState.OPEN
            log.warn("Circuit opened", circuit=self.name, failures=self._failures)

    def reset(self) -> None:
        """수동 리셋 (테스트/관리용)."""
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._half_open_successes = 0
