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
    model: str
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


def load_agents_config(path: str | Path) -> OrchestratorConfig:
    """Read agents.yaml and parse into OrchestratorConfig."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"agents.yaml not found: {path}")

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"invalid agents.yaml format: expected dict, got {type(raw).__name__}")

    return OrchestratorConfig(**raw)
