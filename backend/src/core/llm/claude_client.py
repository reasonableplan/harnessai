"""Anthropic API 기반 Claude 클라이언트."""
from __future__ import annotations

import anthropic

from src.core.config import DEFAULT_CLAUDE_MODEL
from src.core.errors import RateLimitError, TokenBudgetError
from src.core.llm.json_extract import parse_json_response
from src.core.logging.logger import get_logger
from src.core.resilience.api_retry import with_retry

log = get_logger("ClaudeClient")

# Claude 모델 화이트리스트 (injection 방지)
ALLOWED_MODELS = {
    "claude-opus-4-20250514",
    "claude-sonnet-4-20250514",
    "claude-sonnet-4-5-20251001",
    "claude-haiku-4-5-20251001",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229",
}


class ClaudeClient:
    def __init__(self, api_key: str, default_model: str = DEFAULT_CLAUDE_MODEL) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._default_model = default_model
        self._tokens_used = 0

    async def chat(
        self,
        messages: list[dict],
        system: str | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        token_budget: int | None = None,
    ) -> tuple[str, int, int]:
        """
        Claude API 호출.
        Returns: (response_text, input_tokens, output_tokens)
        """
        resolved_model = model or self._default_model
        if resolved_model not in ALLOWED_MODELS:
            log.warn("Unknown model requested, falling back to default", model=resolved_model)
            resolved_model = self._default_model

        if token_budget and self._tokens_used >= token_budget:
            raise TokenBudgetError(self._tokens_used, token_budget)

        async def _call():
            kwargs = {
                "model": resolved_model,
                "max_tokens": max_tokens,
                "messages": messages,
            }
            if system:
                kwargs["system"] = system
            if temperature != 1.0:
                kwargs["temperature"] = temperature
            return await self._client.messages.create(**kwargs)

        try:
            response = await with_retry(
                _call,
                max_retries=3,
                base_delay_ms=1000,
                label=f"Claude {resolved_model}",
            )
        except anthropic.RateLimitError as e:
            raise RateLimitError("Claude API", cause=e) from e

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        self._tokens_used += input_tokens + output_tokens

        text = response.content[0].text if response.content else ""
        return text, input_tokens, output_tokens

    async def chat_json(
        self,
        messages: list[dict],
        system: str | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        token_budget: int | None = None,
    ) -> tuple[dict | list, int, int]:
        """JSON 응답을 파싱해서 반환."""
        text, input_tokens, output_tokens = await self.chat(
            messages=messages,
            system=system,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            token_budget=token_budget,
        )
        return parse_json_response(text), input_tokens, output_tokens

    @property
    def tokens_used(self) -> int:
        return self._tokens_used
