from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.dashboard.routes.deps import get_state_store

router = APIRouter(prefix="/api/hooks", tags=["hooks"])


class ToggleBody(BaseModel):
    enabled: bool


@router.get("")
async def list_hooks(store=Depends(get_state_store)):
    hooks = await store.get_all_hooks()
    return [h.model_dump() for h in hooks]


@router.put("/{hook_id}/toggle")
async def toggle_hook(hook_id: str, body: ToggleBody, store=Depends(get_state_store)):
    await store.toggle_hook(hook_id, body.enabled)
    return {"ok": True}
