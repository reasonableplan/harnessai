from __future__ import annotations

import asyncio

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
    # 3개 독립 쿼리를 병렬 실행 (return_exceptions로 부분 실패 허용)
    results = await asyncio.gather(
        store.get_all_agents(),
        store.get_all_tasks(),
        store.get_all_epics(),
        return_exceptions=True,
    )
    agents_result = results[0] if not isinstance(results[0], Exception) else []
    tasks_result = results[1] if not isinstance(results[1], Exception) else []
    epics_result = results[2] if not isinstance(results[2], Exception) else []

    status_counts: dict[str, int] = {}
    for t in tasks_result:
        status_counts[t.status] = status_counts.get(t.status, 0) + 1

    return SystemSummary(
        totalAgents=len(agents_result),
        totalTasks=len(tasks_result),
        totalEpics=len(epics_result),
        tasksByStatus=status_counts,
    )
