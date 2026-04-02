"""사용자 명령 처리 — Phase 기반 에이전트 실행."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/command", tags=["command"])

# 진행 중인 백그라운드 태스크 참조 유지 — GC 조기 수집 및 예외 무음 손실 방지
_background_tasks: set[asyncio.Task] = set()

# Phase → 에이전트 매핑 (None이면 해당 phase에서 에이전트 실행 안 함)
_PHASE_AGENT_MAP: dict[str, str | None] = {
    "planning": None,
    "designing": "architect",
    "task_breakdown": "orchestrator",
    "implementing": "backend_coder",
    "verifying": "reviewer",
    "deploying": None,
    "done": None,
}


def _on_task_done(task: asyncio.Task) -> None:
    _background_tasks.discard(task)
    if not task.cancelled() and task.exception():
        logger.error("Command background task failed", exc_info=task.exception())


class CommandRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=4096)


class CommandResponse(BaseModel):
    status: str
    phase: str


@router.post("", status_code=202, response_model=CommandResponse)
async def send_command(body: CommandRequest) -> CommandResponse:
    """사용자 명령을 현재 Phase에 맞는 에이전트에 전달한다."""
    from src.dashboard.routes.deps import get_phase_manager, get_runner

    pm = get_phase_manager()
    runner = get_runner()
    phase = pm.current_phase

    agent = _PHASE_AGENT_MAP.get(str(phase))
    if agent is None:
        return CommandResponse(status="no_agent_for_phase", phase=str(phase))

    async def _run() -> None:
        try:
            result = await runner.run(agent, body.content)
            logger.info("Command completed agent=%s success=%s", agent, result.success)
        except Exception:
            logger.error("Command execution failed agent=%s", agent, exc_info=True)

    task = asyncio.create_task(_run())
    _background_tasks.add(task)
    task.add_done_callback(_on_task_done)

    return CommandResponse(status="accepted", phase=str(phase))
