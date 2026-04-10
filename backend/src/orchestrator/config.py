"""agents.yaml 로더 — 에이전트 운영 설정 파싱 및 검증."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, model_validator


class Provider(StrEnum):
    CLAUDE_CLI = "claude-cli"
    GEMINI = "gemini"
    GEMINI_CLI = "gemini-cli"
    OPENAI = "openai"
    LOCAL = "local"


class OnTimeout(StrEnum):
    ESCALATE = "escalate"
    RETRY = "retry"
    LOG_ONLY = "log_only"


class AgentConfig(BaseModel):
    """단일 에이전트의 운영 설정."""

    provider: Provider
    model: str
    prompt_path: str
    timeout_seconds: int = 300
    on_timeout: OnTimeout = OnTimeout.ESCALATE
    max_retries_on_timeout: int = 1
    max_tokens: int = 8192
    api_base: str | None = None  # local provider용

    @model_validator(mode="after")
    def validate_retry_with_timeout_policy(self) -> Self:
        if self.on_timeout != OnTimeout.RETRY and self.max_retries_on_timeout > 0:
            # retry가 아닌데 max_retries > 0이면 무시되므로 0으로 보정
            self.max_retries_on_timeout = 0
        return self

    @model_validator(mode="after")
    def validate_local_needs_api_base(self) -> Self:
        if self.provider == Provider.LOCAL and not self.api_base:
            raise ValueError("local provider는 api_base가 필수입니다.")
        return self


class OrchestratorConfig(BaseModel):
    """전체 에이전트 설정."""

    architect: AgentConfig
    designer: AgentConfig
    orchestrator: AgentConfig
    backend_coder: AgentConfig
    frontend_coder: AgentConfig
    reviewer: AgentConfig
    qa: AgentConfig
    max_concurrent: int = 2  # 동시 실행 에이전트 수 제한

    def get_agent(self, name: str) -> AgentConfig:
        """에이전트 이름으로 설정 조회."""
        if name not in type(self).model_fields:
            raise ValueError(f"알 수 없는 에이전트: {name}")
        return getattr(self, name)

    def all_agents(self) -> dict[str, AgentConfig]:
        """전체 에이전트 설정을 dict로 반환."""
        return {
            field: getattr(self, field)
            for field, info in type(self).model_fields.items()
            if info.annotation is AgentConfig
        }


def load_agents_config(path: str | Path) -> OrchestratorConfig:
    """agents.yaml 파일을 읽어 OrchestratorConfig로 파싱."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"agents.yaml을 찾을 수 없습니다: {path}")

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"agents.yaml 형식이 올바르지 않습니다: dict 예상, {type(raw).__name__} 받음")

    return OrchestratorConfig(**raw)
