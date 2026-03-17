"""_is_retryable httpx 타입 기반 판단 테스트."""
from __future__ import annotations

import asyncio

import httpx
import pytest

from src.core.resilience.api_retry import _is_retryable, with_retry


class TestIsRetryable:
    def test_http_429_retryable(self):
        resp = httpx.Response(429)
        assert _is_retryable(httpx.HTTPStatusError("", request=httpx.Request("GET", ""), response=resp))

    def test_http_500_retryable(self):
        resp = httpx.Response(500)
        assert _is_retryable(httpx.HTTPStatusError("", request=httpx.Request("GET", ""), response=resp))

    def test_http_502_retryable(self):
        resp = httpx.Response(502)
        assert _is_retryable(httpx.HTTPStatusError("", request=httpx.Request("GET", ""), response=resp))

    def test_http_503_retryable(self):
        resp = httpx.Response(503)
        assert _is_retryable(httpx.HTTPStatusError("", request=httpx.Request("GET", ""), response=resp))

    def test_http_401_not_retryable(self):
        resp = httpx.Response(401)
        assert not _is_retryable(httpx.HTTPStatusError("", request=httpx.Request("GET", ""), response=resp))

    def test_http_403_not_retryable(self):
        resp = httpx.Response(403)
        assert not _is_retryable(httpx.HTTPStatusError("", request=httpx.Request("GET", ""), response=resp))

    def test_http_404_not_retryable(self):
        resp = httpx.Response(404)
        assert not _is_retryable(httpx.HTTPStatusError("", request=httpx.Request("GET", ""), response=resp))

    def test_http_422_not_retryable(self):
        resp = httpx.Response(422)
        assert not _is_retryable(httpx.HTTPStatusError("", request=httpx.Request("GET", ""), response=resp))

    def test_connect_error_retryable(self):
        assert _is_retryable(httpx.ConnectError("connection refused"))

    def test_timeout_exception_retryable(self):
        assert _is_retryable(httpx.ReadTimeout("timed out"))

    def test_pool_timeout_retryable(self):
        assert _is_retryable(httpx.PoolTimeout("pool full"))

    def test_asyncio_timeout_retryable(self):
        assert _is_retryable(asyncio.TimeoutError())

    def test_connection_error_retryable(self):
        assert _is_retryable(ConnectionError("reset"))

    def test_os_error_retryable(self):
        assert _is_retryable(OSError("network unreachable"))

    def test_value_error_not_retryable(self):
        assert not _is_retryable(ValueError("bad input"))

    def test_runtime_error_not_retryable(self):
        assert not _is_retryable(RuntimeError("something broke"))


class TestWithRetry:
    async def test_succeeds_on_first_try(self):
        calls = 0

        async def fn():
            nonlocal calls
            calls += 1
            return "ok"

        result = await with_retry(fn, max_retries=3, base_delay_ms=10)
        assert result == "ok"
        assert calls == 1

    async def test_retries_on_retryable_error(self):
        calls = 0

        async def fn():
            nonlocal calls
            calls += 1
            if calls < 3:
                raise httpx.ConnectError("refused")
            return "recovered"

        result = await with_retry(fn, max_retries=3, base_delay_ms=10)
        assert result == "recovered"
        assert calls == 3

    async def test_raises_on_non_retryable_error(self):
        async def fn():
            resp = httpx.Response(404)
            raise httpx.HTTPStatusError("", request=httpx.Request("GET", ""), response=resp)

        with pytest.raises(httpx.HTTPStatusError):
            await with_retry(fn, max_retries=3, base_delay_ms=10)

    async def test_raises_after_max_retries(self):
        async def fn():
            raise httpx.ConnectError("refused")

        with pytest.raises(httpx.ConnectError):
            await with_retry(fn, max_retries=2, base_delay_ms=10)
