from __future__ import annotations

import asyncio
import random
from typing import Awaitable, Callable, TypeVar, Union

import httpx

from src.core.logging.logger import get_logger

log = get_logger("ApiRetry")

T = TypeVar("T")


async def with_retry(
    fn: Callable[[], Union[Awaitable[T], T]],
    max_retries: int = 3,
    base_delay_ms: int = 1000,
    max_delay_ms: int = 15_000,
    label: str = "API call",
) -> T:
    """지수 백오프 + 지터로 재시도하는 헬퍼."""
    for attempt in range(max_retries + 1):
        try:
            result = fn()
            if asyncio.iscoroutine(result):
                return await result
            return result
        except Exception as error:
            if attempt >= max_retries or not _is_retryable(error):
                raise

            delay_ms = min(base_delay_ms * (2 ** attempt), max_delay_ms)
            jitter_ms = delay_ms * (0.5 + random.random() * 0.5)

            log.warning(
                "Retrying after error",
                attempt=attempt + 1,
                max_retries=max_retries,
                delay_ms=round(jitter_ms),
                label=label,
                error=str(error),
            )
            await asyncio.sleep(jitter_ms / 1000)

    raise RuntimeError("Exhausted retries")


# HTTP status codes that are safe to retry
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

# HTTP status codes that should NOT be retried (client errors)
_NON_RETRYABLE_STATUS_CODES = frozenset({400, 401, 403, 404, 409, 422})


def _is_retryable(error: Exception) -> bool:
    """httpx 타입 기반으로 재시도 가능 여부를 판단한다."""

    # httpx HTTP status errors — status code로 직접 판단
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        if status in _RETRYABLE_STATUS_CODES:
            return True
        if status in _NON_RETRYABLE_STATUS_CODES:
            return False
        # 그 외 5xx는 재시도
        return status >= 500

    # httpx 네트워크/타임아웃 에러 — 항상 재시도
    if isinstance(error, (httpx.ConnectError, httpx.ReadError, httpx.WriteError, httpx.PoolTimeout)):
        return True
    if isinstance(error, httpx.TimeoutException):
        return True

    # asyncio 타임아웃
    if isinstance(error, (asyncio.TimeoutError, TimeoutError)):
        return True

    # ConnectionError (stdlib)
    if isinstance(error, (ConnectionError, OSError)):
        return True

    # Anthropic SDK rate limit error
    try:
        import anthropic as _anthropic

        if isinstance(error, _anthropic.RateLimitError):
            return True
    except ImportError:
        pass

    # 그 외는 재시도하지 않음
    return False
