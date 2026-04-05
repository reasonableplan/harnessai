"""사용자 명령 처리 — Phase 기반 에이전트 실행."""
from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.orchestrator.orchestrate import PHASE_AGENT_MAP
from src.orchestrator.phase import Phase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/command", tags=["command"])

# 진행 중인 백그라운드 태스크 참조 유지 — GC 조기 수집 및 예외 무음 손실 방지
_background_tasks: set[asyncio.Task] = set()

# 하위 호환: 기존 코드/테스트가 _PHASE_AGENT_MAP을 참조하는 경우를 위한 별칭
_PHASE_AGENT_MAP = PHASE_AGENT_MAP


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
    """사용자 명령을 현재 Phase에 맞는 에이전트에 전달한다.

    IMPLEMENTING phase는 Orchestra.implement_with_retry()를 경유해
    SecurityHooks + ValidationPipeline + Reviewer 검증을 수행한다.
    다른 phase는 단순 에이전트 실행 (설계/분해 결과는 코드가 아니므로).
    """
    from src.dashboard.routes.deps import get_orchestra, get_runner

    orchestra = get_orchestra()
    phase = orchestra.phase_manager.current_phase

    agent = _PHASE_AGENT_MAP.get(str(phase))
    if agent is None:
        return CommandResponse(status="no_agent_for_phase", phase=str(phase))

    async def _run() -> None:
        try:
            if phase == Phase.IMPLEMENTING:
                task_id = f"cmd_{uuid.uuid4().hex[:8]}"
                result = await orchestra.implement_with_retry(task_id, agent, body.content)
                logger.info(
                    "Command completed agent=%s passed=%s attempts=%s",
                    agent, result.get("passed"), result.get("attempts"),
                )
            else:
                runner = get_runner()
                result = await runner.run(agent, body.content)
                logger.info("Command completed agent=%s success=%s", agent, result.success)
        except Exception:
            logger.error("Command execution failed agent=%s", agent, exc_info=True)

    task = asyncio.create_task(_run())
    _background_tasks.add(task)
    task.add_done_callback(_on_task_done)

    return CommandResponse(status="accepted", phase=str(phase))
