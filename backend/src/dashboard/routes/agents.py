"""GET /api/agents — 에이전트 목록 및 설정 조회."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, Field, field_validator

from src.dashboard.routes.deps import get_config

router = APIRouter(prefix="/api/agents", tags=["agents"])

# 대시보드에서 에이전트 모델 override 시 허용되는 값 (claude_client 의존 제거).
# agents.yaml 의 `models` 티어 별칭이 가리키는 현재 모델 + 대체 선택지.
_ALLOWED_MODELS: frozenset[str] = frozenset(
    {
        "claude-opus-4-8",  # judge tier (현재)
        "claude-sonnet-5",  # code tier (현재)
        "claude-haiku-4-5-20251001",  # 저렴/빠른 대체
        "claude-opus-4-6",  # 이전 세대 fallback
        "claude-sonnet-4-6",  # 이전 세대 fallback
    }
)


class AgentSummary(BaseModel):
    id: str
    provider: str
    model: str
    timeout_seconds: int
    on_timeout: str


class AgentConfigUpdate(BaseModel):
    model: str | None = Field(None, min_length=1, max_length=100)
    timeout_seconds: int | None = Field(None, ge=1, le=3600)

    @field_validator("model")
    @classmethod
    def validate_model(cls, v: str | None) -> str | None:
        if v is not None and v not in _ALLOWED_MODELS:
            raise ValueError(f"Unknown model. Allowed: {sorted(_ALLOWED_MODELS)}")
        return v


@router.get("", response_model=list[AgentSummary])
async def list_agents() -> list[AgentSummary]:
    """에이전트 목록을 반환한다."""
    config = get_config()
    return [
        AgentSummary(
            id=name,
            provider=str(agent_cfg.provider),
            model=agent_cfg.model,
            timeout_seconds=agent_cfg.timeout_seconds,
            on_timeout=str(agent_cfg.on_timeout),
        )
        for name, agent_cfg in config.all_agents().items()
    ]


@router.get("/{agent_id}")
async def get_agent(
    agent_id: str = Path(..., min_length=1, max_length=64),
) -> dict:
    """특정 에이전트 설정을 반환한다."""
    config = get_config()
    try:
        agent_cfg = config.get_agent(agent_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Agent not found") from None
    return {
        "id": agent_id,
        "provider": str(agent_cfg.provider),
        "model": agent_cfg.model,
        "timeout_seconds": agent_cfg.timeout_seconds,
        "on_timeout": str(agent_cfg.on_timeout),
        "max_retries_on_timeout": agent_cfg.max_retries_on_timeout,
        "max_tokens": agent_cfg.max_tokens,
    }
