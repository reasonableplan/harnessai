from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.dashboard.routes.deps import get_state_store

router = APIRouter(prefix="/api/stats", tags=["stats"])


class SystemSummary(BaseModel):
    totalAgents: int
    totalTasks: int
    totalEpics: int
    tasksByStatus: dict[str, int]


@router.get("/summary", response_model=SystemSummary)
async def get_summary(store=Depends(get_state_store)):
    agents = await store.get_all_agents()
    tasks = await store.get_all_tasks()
    epics = await store.get_all_epics()

    status_counts: dict[str, int] = {}
    for t in tasks:
        status_counts[t.status] = status_counts.get(t.status, 0) + 1

    return SystemSummary(
        totalAgents=len(agents),
        totalTasks=len(tasks),
        totalEpics=len(epics),
        tasksByStatus=status_counts,
    )
