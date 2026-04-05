"""EventMapper 단위 테스트."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.dashboard.event_mapper import EventMapper


@pytest.fixture()
def ws_manager() -> MagicMock:
    mock = MagicMock()
    mock.broadcast = AsyncMock()
    return mock


@pytest.fixture()
def mapper(ws_manager: MagicMock) -> EventMapper:
    return EventMapper(ws_manager)


class TestEmitPhaseChange:
    async def test_broadcasts_phase_change(self, mapper: EventMapper, ws_manager: MagicMock) -> None:
        await mapper.emit_phase_change("IMPLEMENTING")
        ws_manager.broadcast.assert_called_once_with(
            "phase.change",
            {"phase": "IMPLEMENTING", "data": {}},
        )

    async def test_includes_data_when_provided(self, mapper: EventMapper, ws_manager: MagicMock) -> None:
        await mapper.emit_phase_change("VERIFYING", data={"task_id": "T-001"})
        ws_manager.broadcast.assert_called_once_with(
            "phase.change",
            {"phase": "VERIFYING", "data": {"task_id": "T-001"}},
        )

    async def test_data_defaults_to_empty_dict_when_none(
        self, mapper: EventMapper, ws_manager: MagicMock
    ) -> None:
        await mapper.emit_phase_change("DONE", data=None)
        _, kwargs_payload = ws_manager.broadcast.call_args[0]
        assert kwargs_payload["data"] == {}


class TestEmitAgentStart:
    async def test_broadcasts_agent_start(self, mapper: EventMapper, ws_manager: MagicMock) -> None:
        await mapper.emit_agent_start("backend_coder", "DB 모델 구현")
        ws_manager.broadcast.assert_called_once_with(
            "agent.start",
            {"agent": "backend_coder", "prompt": "DB 모델 구현"},
        )

    async def test_prompt_truncated_to_200(self, mapper: EventMapper, ws_manager: MagicMock) -> None:
        long_prompt = "x" * 500
        await mapper.emit_agent_start("architect", long_prompt)
        _, payload = ws_manager.broadcast.call_args[0]
        assert len(payload["prompt"]) == 200

    async def test_short_prompt_not_truncated(self, mapper: EventMapper, ws_manager: MagicMock) -> None:
        short = "짧은 프롬프트"
        await mapper.emit_agent_start("reviewer", short)
        _, payload = ws_manager.broadcast.call_args[0]
        assert payload["prompt"] == short


class TestEmitAgentComplete:
    async def test_broadcasts_success(self, mapper: EventMapper, ws_manager: MagicMock) -> None:
        await mapper.emit_agent_complete("frontend_coder", success=True, duration_ms=1234)
        ws_manager.broadcast.assert_called_once_with(
            "agent.complete",
            {"agent": "frontend_coder", "success": True, "durationMs": 1234, "error": None},
        )

    async def test_broadcasts_failure_with_error(
        self, mapper: EventMapper, ws_manager: MagicMock
    ) -> None:
        await mapper.emit_agent_complete("qa", success=False, duration_ms=500, error="타임아웃")
        _, payload = ws_manager.broadcast.call_args[0]
        assert payload["success"] is False
        assert payload["error"] == "타임아웃"

    async def test_error_defaults_to_none(self, mapper: EventMapper, ws_manager: MagicMock) -> None:
        await mapper.emit_agent_complete("orchestrator", success=True, duration_ms=300)
        _, payload = ws_manager.broadcast.call_args[0]
        assert payload["error"] is None


class TestEmitValidationResult:
    async def test_broadcasts_validation_result(
        self, mapper: EventMapper, ws_manager: MagicMock
    ) -> None:
        checks = [{"name": "lint", "passed": True}, {"name": "test", "passed": False}]
        await mapper.emit_validation_result(checks)
        ws_manager.broadcast.assert_called_once_with(
            "validation.result",
            {"checks": checks},
        )

    async def test_empty_checks(self, mapper: EventMapper, ws_manager: MagicMock) -> None:
        await mapper.emit_validation_result([])
        _, payload = ws_manager.broadcast.call_args[0]
        assert payload["checks"] == []


class TestEmitTaskUpdate:
    async def test_broadcasts_task_update_with_agent(
        self, mapper: EventMapper, ws_manager: MagicMock
    ) -> None:
        await mapper.emit_task_update("T-001", "completed", agent="backend_coder")
        ws_manager.broadcast.assert_called_once_with(
            "task.update",
            {"taskId": "T-001", "status": "completed", "agent": "backend_coder"},
        )

    async def test_broadcasts_task_update_without_agent(
        self, mapper: EventMapper, ws_manager: MagicMock
    ) -> None:
        await mapper.emit_task_update("T-002", "in_progress")
        _, payload = ws_manager.broadcast.call_args[0]
        assert payload["agent"] is None

    async def test_task_id_and_status_forwarded(
        self, mapper: EventMapper, ws_manager: MagicMock
    ) -> None:
        await mapper.emit_task_update("T-999", "failed")
        _, payload = ws_manager.broadcast.call_args[0]
        assert payload["taskId"] == "T-999"
        assert payload["status"] == "failed"


class TestEmitPhaseMessage:
    async def test_broadcasts_phase_message(self, mapper: EventMapper, ws_manager: MagicMock) -> None:
        await mapper.emit_phase_message("orchestrator", "태스크 분해 완료")
        ws_manager.broadcast.assert_called_once_with(
            "phase.message",
            {"from": "orchestrator", "content": "태스크 분해 완료"},
        )


class TestEmitPhasePlan:
    async def test_broadcasts_phase_plan(self, mapper: EventMapper, ws_manager: MagicMock) -> None:
        plan = {"phases": [{"phase_num": 1, "tasks": ["T-001"]}]}
        await mapper.emit_phase_plan(plan)
        ws_manager.broadcast.assert_called_once_with("phase.plan", plan)


class TestEmitPhaseCommitted:
    async def test_broadcasts_phase_committed(
        self, mapper: EventMapper, ws_manager: MagicMock
    ) -> None:
        await mapper.emit_phase_committed(1, ["T-001", "T-002"])
        ws_manager.broadcast.assert_called_once_with(
            "phase.committed",
            {"phaseNum": 1, "taskIds": ["T-001", "T-002"]},
        )
