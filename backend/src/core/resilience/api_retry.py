from __future__ import annotations

import asyncio
import random
import re
from typing import Awaitable, Callable, TypeVar, Union

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

            log.warn(
                "Retrying after error",
                attempt=attempt + 1,
                max_retries=max_retries,
                delay_ms=round(jitter_ms),
                label=label,
                error=str(error),
            )
            await asyncio.sleep(jitter_ms / 1000)

    raise RuntimeError("Exhausted retries")


def _is_retryable(error: Exception) -> bool:
    msg = str(error).lower()

    # 네트워크/서버 에러
    if any(k in msg for k in ("econnreset", "socket", "timeout", "network", "connection")):
        return True

    # HTTP 5xx
    if re.search(r"\b5\d{2}\b", msg):
        return True

    # Rate limit
    if any(k in msg for k in ("rate limit", "429", "secondary rate")):
        return True

    # 인증/권한 에러는 재시도 불가
    if any(k in msg for k in ("401", "403", "404")):
        return False

    return False
