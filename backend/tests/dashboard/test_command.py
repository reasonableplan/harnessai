"""POST /api/command 라우트 단위 테스트."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.dashboard.routes.command import _PHASE_AGENT_MAP, router
from src.orchestrator.phase import Phase
from src.orchestrator.runner import RunResult


def _make_run_result(success: bool = True, output: str = "ok") -> RunResult:
    return RunResult(agent="backend_coder", output=output, success=success,
                     duration_ms=100, attempts=1)


def _make_orchestra(phase: Phase) -> MagicMock:
    orchestra = MagicMock()
    orchestra.phase_manager.current_phase = phase
    orchestra.implement_with_retry = AsyncMock(return_value={
        "implement": _make_run_result(),
        "verify": {},
        "attempts": 1,
        "passed": True,
    })
    orchestra.runner.run = AsyncMock(return_value=_make_run_result())
    return orchestra


# ---------------------------------------------------------------------------
# IMPLEMENTING phase — Orchestra.implement_with_retry() 경유
# ---------------------------------------------------------------------------

class TestSendCommandImplementing:
    @pytest.fixture()
    def app(self):
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        return app

    def test_implementing_calls_implement_with_retry(self, app):
        orchestra = _make_orchestra(Phase.IMPLEMENTING)

        with patch("src.dashboard.routes.deps.get_orchestra", return_value=orchestra):
            client = TestClient(app)
            resp = client.post("/api/command", json={"content": "DB 모델 구현"})

        assert resp.status_code == 202
        assert resp.json()["status"] == "accepted"
        assert resp.json()["phase"] == "implementing"

    def test_implementing_does_not_call_runner_run(self, app):
        """IMPLEMENTING에서 raw runner.run()을 직접 호출하지 않는다 (검증 우회 방지)."""
        orchestra = _make_orchestra(Phase.IMPLEMENTING)

        with patch("src.dashboard.routes.deps.get_orchestra", return_value=orchestra):
            client = TestClient(app)
            client.post("/api/command", json={"content": "구현 요청"})

        orchestra.runner.run.assert_not_called()

    def test_non_implementing_calls_runner_run(self, app):
        """IMPLEMENTING 외 phase는 runner.run()을 직접 호출한다."""
        orchestra = _make_orchestra(Phase.DESIGNING)

        with (
            patch("src.dashboard.routes.deps.get_orchestra", return_value=orchestra),
            patch("src.dashboard.routes.deps.get_runner", return_value=orchestra.runner),
        ):
            client = TestClient(app)
            client.post("/api/command", json={"content": "설계 시작"})

        orchestra.runner.run.assert_called_once()
        orchestra.implement_with_retry.assert_not_called()


# ---------------------------------------------------------------------------
# Phase → 에이전트 매핑
# ---------------------------------------------------------------------------

class TestPhaseAgentMap:
    def test_implementing_maps_to_backend_coder(self):
        assert _PHASE_AGENT_MAP["implementing"] == "backend_coder"

    def test_no_agent_phases(self):
        for phase in ("planning", "deploying", "done"):
            assert _PHASE_AGENT_MAP[phase] is None

    def test_all_phase_values_covered(self):
        """모든 Phase enum 값이 _PHASE_AGENT_MAP에 있어야 한다."""
        for phase in Phase:
            assert str(phase) in _PHASE_AGENT_MAP, f"Phase.{phase} 누락"


# ---------------------------------------------------------------------------
# No-agent phase
# ---------------------------------------------------------------------------

class TestSendCommandNoAgent:
    @pytest.fixture()
    def app(self):
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        return app

    def test_planning_phase_returns_no_agent(self, app):
        orchestra = _make_orchestra(Phase.PLANNING)

        with patch("src.dashboard.routes.deps.get_orchestra", return_value=orchestra):
            client = TestClient(app)
            resp = client.post("/api/command", json={"content": "무언가"})

        assert resp.status_code == 202
        assert resp.json()["status"] == "no_agent_for_phase"
