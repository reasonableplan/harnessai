"""OpenAI 호환 로컬 모델 클라이언트 (Ollama, LM Studio, vLLM, OpenRouter 등)."""
from __future__ import annotations

import httpx

from src.core.errors import AuthError, NetworkError, RateLimitError, TokenBudgetError
from src.core.llm.json_extract import parse_json_response
from src.core.logging.logger import get_logger
from src.core.resilience.api_retry import with_retry

log = get_logger("LocalModelClient")

# SSRF 방어: 메타데이터 엔드포인트 차단
_BLOCKED_HOSTS = {
    "169.254.169.254",
    "metadata.google.internal",
    "169.254.170.2",
    "fd00:ec2::254",
}

TIMEOUT_S = 120.0


def _check_ssrf(url: str) -> None:
    from urllib.parse import urlparse
    host = urlparse(url).hostname or ""
    if host in _BLOCKED_HOSTS:
        raise ValueError(f"SSRF protection: blocked host {host!r}")


class LocalModelClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
    ) -> None:
        _check_ssrf(base_url)
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._client = httpx.AsyncClient(timeout=TIMEOUT_S)
        self._tokens_used = 0

    async def close(self) -> None:
        await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def chat(
        self,
        messages: list[dict],
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        token_budget: int | None = None,
    ) -> tuple[str, int, int]:
        """
        OpenAI-compatible /v1/chat/completions 호출.
        Returns: (response_text, input_tokens, output_tokens)
        """
        if token_budget and self._tokens_used >= token_budget:
            raise TokenBudgetError(self._tokens_used, token_budget)

        if system:
            messages = [{"role": "system", "content": system}, *messages]

        body = {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        async def _call():
            resp = await self._client.post(
                f"{self._base_url}/chat/completions",
                headers=self._headers(),
                json=body,
            )
            # 모든 HTTP 에러를 raise_for_status()로 통일 — 외부 except에서 분류
            resp.raise_for_status()
            return resp.json()

        try:
            data = await with_retry(_call, max_retries=3, label="LocalModel")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthError("LocalModel", cause=e) from e
            if e.response.status_code == 429:
                raise RateLimitError("LocalModel", cause=e) from e
            raise NetworkError(f"LocalModel HTTP {e.response.status_code}", cause=e) from e
        except httpx.ConnectError as e:
            raise NetworkError(f"Connection failed to {self._base_url}", cause=e) from e
        except httpx.TimeoutException as e:
            raise NetworkError("LocalModel request timed out", cause=e) from e

        choice = data["choices"][0]
        text = choice["message"]["content"] or ""
        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        self._tokens_used += input_tokens + output_tokens
        return text, input_tokens, output_tokens

    async def chat_json(
        self,
        messages: list[dict],
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        token_budget: int | None = None,
    ) -> tuple[dict | list, int, int]:
        text, input_tokens, output_tokens = await self.chat(
            messages=messages, system=system, max_tokens=max_tokens, temperature=temperature,
            token_budget=token_budget,
        )
        return parse_json_response(text), input_tokens, output_tokens
