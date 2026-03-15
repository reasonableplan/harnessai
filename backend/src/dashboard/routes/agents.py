from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.dashboard.routes.deps import get_state_store

router = APIRouter(prefix="/api/agents", tags=["agents"])


class AgentConfigUpdate(BaseModel):
    claude_model: str | None = Field(None, min_length=1, max_length=100)
    max_tokens: int | None = Field(None, ge=256, le=32768)
    temperature: float | None = Field(None, ge=0.0, le=2.0)
    token_budget: int | None = Field(None, ge=1000)
    task_timeout_ms: int | None = Field(None, ge=1000)
    poll_interval_ms: int | None = Field(None, ge=500)


@router.get("")
async def list_agents(store=Depends(get_state_store)):
    agents = await store.get_all_agents()
    return [
        {
            "id": a.id,
            "domain": a.domain,
            "level": a.level,
            "status": a.status,
            "lastHeartbeat": a.last_heartbeat.isoformat() if a.last_heartbeat else None,
        }
        for a in agents
    ]


@router.get("/{agent_id}/stats")
async def get_agent_stats(agent_id: str, store=Depends(get_state_store)):
    stats = await store.get_agent_stats(agent_id)
    return stats.model_dump()


@router.get("/{agent_id}/config")
async def get_agent_config(agent_id: str, store=Depends(get_state_store)):
    config = await store.get_agent_config(agent_id)
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")
    return config.model_dump()


@router.put("/{agent_id}/config")
async def update_agent_config(
    agent_id: str, body: AgentConfigUpdate, store=Depends(get_state_store)
):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    await store.upsert_agent_config(agent_id, updates)
    return {"ok": True}
