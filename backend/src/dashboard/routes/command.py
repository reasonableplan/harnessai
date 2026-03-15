from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.core.types import UserInput
from src.dashboard.routes.deps import get_director

router = APIRouter(prefix="/api/command", tags=["command"])

# 진행 중인 백그라운드 태스크 참조 유지 — GC 조기 수집 및 예외 무음 손실 방지
_background_tasks: set[asyncio.Task] = set()


class CommandRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=4096)


@router.post("", status_code=202)
async def send_command(body: CommandRequest, director=Depends(get_director)):
    """사용자 명령을 DirectorAgent에 전달한다. 처리는 비동기로 백그라운드에서 실행된다."""
    user_input = UserInput(source="dashboard", content=body.content)
    task = asyncio.create_task(director.handle_user_input(user_input))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"status": "accepted"}
