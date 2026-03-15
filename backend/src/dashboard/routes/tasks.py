from __future__ import annotations

from fastapi import APIRouter, Depends

from src.dashboard.routes.deps import get_state_store

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("")
async def list_tasks(store=Depends(get_state_store)):
    tasks = await store.get_all_tasks()
    return [
        {
            "id": t.id,
            "epicId": t.epic_id,
            "title": t.title,
            "status": t.status,
            "boardColumn": t.board_column,
            "assignedAgent": t.assigned_agent,
            "priority": t.priority,
            "retryCount": t.retry_count,
        }
        for t in tasks
    ]


@router.get("/{task_id}/history")
async def get_task_history(task_id: str, store=Depends(get_state_store)):
    entries = await store.get_task_history(task_id)
    return [e.model_dump() for e in entries]
