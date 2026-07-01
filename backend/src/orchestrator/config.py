"""agents.yaml loader — parse and validate agent runtime configuration."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, Field, model_validator


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
    """Runtime configuration for a single agent."""

    provider: Provider
    model: str  # concrete 모델 문자열. model_tier 사용 시 로더가 models 별칭으로 채운다.
    model_tier: str | None = None  # judge|code 등 — agents.yaml 의 models 맵 키 (introspection 용)
    prompt_path: str
    timeout_seconds: int = 300
    on_timeout: OnTimeout = OnTimeout.ESCALATE
    max_retries_on_timeout: int = 1
    max_tokens: int = 8192
    api_base: str | None = None  # required for local provider
    # Capability-based routing (Group 3 Step 1).
    # Empty list = capability-agnostic (architect, reviewer, etc.).
    # Non-empty = agent handles tasks that share at least one of these
    # has.* atoms (any-of) AND all listed profile IDs are active.
    requires_capabilities: list[str] = Field(default_factory=list)
    requires_profile_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_retry_with_timeout_policy(self) -> Self:
        if self.on_timeout != OnTimeout.RETRY and self.max_retries_on_timeout > 0:
            # max_retries is meaningless without RETRY policy — reset to 0
            self.max_retries_on_timeout = 0
        return self

    @model_validator(mode="after")
    def validate_local_needs_api_base(self) -> Self:
        if self.provider == Provider.LOCAL and not self.api_base:
            raise ValueError("local provider requires api_base")
        return self


class OrchestratorConfig(BaseModel):
    """Top-level orchestrator configuration holding all agent configs."""

    architect: AgentConfig
    designer: AgentConfig
    orchestrator: AgentConfig
    backend_coder: AgentConfig
    frontend_coder: AgentConfig
    mobile_coder_rn: AgentConfig
    mobile_coder_flutter: AgentConfig
    mobile_coder_android: AgentConfig
    mobile_coder_ios: AgentConfig
    reviewer: AgentConfig
    qa: AgentConfig
    max_concurrent: int = 2  # max parallel agent executions

    def get_agent(self, name: str) -> AgentConfig:
        """Look up agent config by name."""
        if name not in type(self).model_fields:
            raise ValueError(f"unknown agent: {name}")
        return getattr(self, name)

    def all_agents(self) -> dict[str, AgentConfig]:
        """Return all agent configs as a dict."""
        return {
            field: getattr(self, field)
            for field, info in type(self).model_fields.items()
            if info.annotation is AgentConfig
        }


def _resolve_model_tiers(raw: dict) -> dict:
    """`models` 별칭 맵으로 각 에이전트의 `model_tier` 를 concrete `model` 로 해석.

    - 상단 `models: {judge: ..., code: ...}` 를 정의하면 에이전트는 `model_tier: judge`
      한 줄로 참조 → 신모델 출시 시 `models` 두 줄만 바꾸면 전체 반영.
    - 에이전트에 `model` 이 명시돼 있으면 그대로 둔다 (override 허용, backward compatible).
    - `models` 블록이 없고 모두 concrete `model` 인 구형 yaml 도 그대로 동작.
    """
    models = raw.pop("models", {})
    if not isinstance(models, dict):
        raise ValueError(f"'models' must be a mapping, got {type(models).__name__}")

    for name, spec in raw.items():
        if not isinstance(spec, dict):
            continue  # max_concurrent 등 스칼라는 스킵
        if spec.get("model"):
            continue  # 명시적 model 우선
        tier = spec.get("model_tier")
        if tier is None:
            raise ValueError(f"agent {name!r}: 'model' 또는 'model_tier' 중 하나가 필요합니다")
        if tier not in models:
            raise ValueError(
                f"agent {name!r}: model_tier {tier!r} 가 models 에 없습니다 "
                f"(정의된 tier: {sorted(models)})"
            )
        spec["model"] = models[tier]

    return raw


def load_agents_config(path: str | Path) -> OrchestratorConfig:
    """Read agents.yaml and parse into OrchestratorConfig."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"agents.yaml not found: {path}")

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"invalid agents.yaml format: expected dict, got {type(raw).__name__}")

    raw = _resolve_model_tiers(raw)

    return OrchestratorConfig(**raw)
