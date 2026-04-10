"""Gemini API provider — httpx로 Google Generative AI REST API 호출."""

from __future__ import annotations

import os
from pathlib import Path

import httpx

from src.orchestrator.config import AgentConfig
from src.orchestrator.providers.base import BaseProvider

_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiApiProvider(BaseProvider):
    """Google Generative AI REST API를 httpx로 호출하는 provider.

    환경변수 GEMINI_API_KEY가 필요하다.
    """

    async def execute(
        self,
        agent_name: str,
        config: AgentConfig,
        prompt: str,
        *,
        system_prompt: str | None = None,
        working_dir: Path | None = None,
    ) -> str:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY 환경변수가 설정되어 있지 않습니다."
            )

        url = f"{_API_BASE}/{config.model}:generateContent"
        body: dict = {
            "contents": [
                {"role": "user", "parts": [{"text": prompt}]}
            ],
            "generationConfig": {
                "maxOutputTokens": config.max_tokens,
            },
        }
        if system_prompt:
            body["system_instruction"] = {
                "parts": [{"text": system_prompt}]
            }

        timeout = httpx.Timeout(
            connect=10.0,
            read=float(config.timeout_seconds),
            write=30.0,
            pool=5.0,
        )

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                resp = await client.post(
                    url,
                    params={"key": api_key},
                    json=body,
                )
            except httpx.TimeoutException as exc:
                raise TimeoutError(
                    f"{agent_name} 타임아웃: {config.timeout_seconds}초 초과"
                ) from exc

        if resp.status_code != 200:
            raise RuntimeError(
                f"{agent_name} Gemini API 오류 (HTTP {resp.status_code}): "
                f"{resp.text[:300]}"
            )

        data = resp.json()
        try:
            text: str = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise RuntimeError(
                f"{agent_name} Gemini 응답 파싱 실패: {data}"
            ) from exc

        return text.strip()
