"""GET /api/stats — 시스템 요약 통계."""
from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stats", tags=["stats"])


class SystemSummary(BaseModel):
    totalAgents: int
    currentPhase: str
    taskResultCount: int


@router.get("/summary", response_model=SystemSummary)
async def get_summary() -> SystemSummary:
    """에이전트 수, 현재 Phase, task result 파일 수를 반환한다."""
    from src.dashboard.routes.deps import get_config, get_phase_manager, get_state_manager

    config = get_config()
    pm = get_phase_manager()
    sm = get_state_manager()

    # results/ 디렉토리의 JSON 파일 수로 태스크 결과 수를 파악
    results_dir = sm._results_dir
    try:
        task_count = sum(1 for p in results_dir.iterdir() if p.suffix == ".json")
    except Exception as exc:
        logger.warning("stats: results 디렉토리 읽기 실패: %s", exc)
        task_count = 0

    return SystemSummary(
        totalAgents=len(config.all_agents()),
        currentPhase=str(pm.current_phase),
        taskResultCount=task_count,
    )
