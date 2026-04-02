"""에이전트 이벤트 → WebSocket 브로드캐스트 변환."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class EventMapper:
    """에이전트 실행 결과를 WebSocket 이벤트로 변환해서 브로드캐스트."""

    def __init__(self, ws_manager: Any) -> None:
        self._ws = ws_manager

    async def emit_phase_change(self, phase: str, data: dict[str, Any] | None = None) -> None:
        """Phase 전이 이벤트."""
        await self._ws.broadcast("phase.change", {
            "phase": phase,
            "data": data or {},
        })

    async def emit_agent_start(self, agent: str, prompt: str) -> None:
        """에이전트 실행 시작."""
        await self._ws.broadcast("agent.start", {
            "agent": agent,
            "prompt": prompt[:200],
        })

    async def emit_agent_complete(
        self,
        agent: str,
        success: bool,
        duration_ms: int,
        error: str | None = None,
    ) -> None:
        """에이전트 실행 완료."""
        await self._ws.broadcast("agent.complete", {
            "agent": agent,
            "success": success,
            "durationMs": duration_ms,
            "error": error,
        })

    async def emit_validation_result(self, checks: list[dict[str, Any]]) -> None:
        """검증 파이프라인 결과."""
        await self._ws.broadcast("validation.result", {
            "checks": checks,
        })

    async def emit_task_update(
        self,
        task_id: str,
        status: str,
        agent: str | None = None,
    ) -> None:
        """태스크 상태 업데이트."""
        await self._ws.broadcast("task.update", {
            "taskId": task_id,
            "status": status,
            "agent": agent,
        })
