"""GET /api/agents — 에이전트 목록 및 설정 조회."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel

from src.dashboard.routes.deps import get_config

router = APIRouter(prefix="/api/agents", tags=["agents"])


class AgentSummary(BaseModel):
    id: str
    provider: str
    model: str
    timeout_seconds: int
    on_timeout: str


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
