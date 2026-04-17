"""pipeline_runner 테스트."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.orchestrator.output_parser import parse_phases
from src.orchestrator.phase import Phase
from src.orchestrator.pipeline_runner import _ask_approval, run
from src.orchestrator.runner import RunResult

# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _make_run_result(agent: str, *, output: str = "", success: bool = True) -> RunResult:
    return RunResult(
        agent=agent,
        output=output,
        success=success,
        duration_ms=10,
        attempts=1,
        error=None,
        escalated=False,
    )


_BREAKDOWN_SINGLE_PHASE = (
    "### Phase 1 — MVP\n"
    "| ID | 에이전트 | 의존성 | 설명 | 상태 |\n"
    "|---|---|---|---|---|\n"
    "| T-001 | backend_coder | - | 백엔드 구현 | 대기 |\n"
)

_DESIGN_RESULTS = {
    "architect": RunResult(agent="architect", output="", success=True, duration_ms=10, attempts=1, error=None, escalated=False),
    "designer": RunResult(agent="designer", output="", success=True, duration_ms=10, attempts=1, error=None, escalated=False),
}


def _make_orchestra_mock() -> MagicMock:
    """Orchestra mock 기본 설정 — AsyncMock 사용."""
    mock = MagicMock()
    mock.design = AsyncMock(return_value=_DESIGN_RESULTS)
    mock.materialize_skeleton = MagicMock()
    mock.runner.run = AsyncMock(return_value=_make_run_result("architect"))
    mock.run_breakdown = AsyncMock(
        return_value=(parse_phases(_BREAKDOWN_SINGLE_PHASE), {"output": _BREAKDOWN_SINGLE_PHASE})
    )
    mock.run_phases = AsyncMock(
        return_value={"phases": [{"phase_num": 1, "passed": True}], "success": True}
    )
    mock.phase_manager = MagicMock()
    mock.phase_manager.current_phase = Phase.VERIFYING
    mock.phase_manager.transition = MagicMock()
    return mock


# ---------------------------------------------------------------------------
# _ask_approval
# ---------------------------------------------------------------------------

class TestAskApproval:
    async def test_yes_inputs(self) -> None:
        for answer in ("y", "yes", "ㅇ", "ㅇㅇ", "예", "네"):
            with patch("builtins.input", return_value=answer):
                assert await _ask_approval("계속?") is True

    async def test_no_inputs(self) -> None:
        for answer in ("n", "no", "아니", "아니오", "ㄴ"):
            with patch("builtins.input", return_value=answer):
                assert await _ask_approval("계속?") is False

    async def test_invalid_then_valid(self) -> None:
        """잘못된 입력 후 유효한 입력을 받는지 확인."""
        with patch("builtins.input", side_effect=["x", "?", "y"]):
            assert await _ask_approval("계속?") is True


# ---------------------------------------------------------------------------
# run() — 게이트 경로
# ---------------------------------------------------------------------------

class TestRunInteractivePipeline:
    """run()의 각 게이트 rejection/success 경로 테스트."""

    async def test_gate1_reject_returns_false(self, tmp_path: Path) -> None:
        """GATE 1 거부 시 False 반환 — design 호출 안 됨."""
        mock_orchestra = _make_orchestra_mock()

        with (
            patch("src.orchestrator.pipeline_runner.Orchestra", return_value=mock_orchestra),
            patch("builtins.input", return_value="n"),
        ):
            result = await run("요구사항", tmp_path)

        assert result is False
        mock_orchestra.design.assert_not_called()

    async def test_gate2_reject_returns_false(self, tmp_path: Path) -> None:
        """GATE 2 거부 시 False 반환 — design은 완료됨."""
        mock_orchestra = _make_orchestra_mock()

        with (
            patch("src.orchestrator.pipeline_runner.Orchestra", return_value=mock_orchestra),
            patch("builtins.input", side_effect=["y", "n"]),
        ):
            result = await run("요구사항", tmp_path)

        assert result is False
        mock_orchestra.materialize_skeleton.assert_called_once()
        mock_orchestra.run_breakdown.assert_not_called()

    async def test_gate3_reject_returns_false(self, tmp_path: Path) -> None:
        """GATE 3 거부 시 False 반환 — breakdown까지 완료됨."""
        mock_orchestra = _make_orchestra_mock()

        with (
            patch("src.orchestrator.pipeline_runner.Orchestra", return_value=mock_orchestra),
            patch("builtins.input", side_effect=["y", "y", "n"]),
        ):
            result = await run("요구사항", tmp_path)

        assert result is False
        mock_orchestra.run_breakdown.assert_called_once()
        mock_orchestra.run_phases.assert_not_called()

    async def test_full_success_returns_true(self, tmp_path: Path) -> None:
        """모든 게이트 통과 + 구현 성공 시 True 반환 + Phase.DONE 전환."""
        mock_orchestra = _make_orchestra_mock()

        with (
            patch("src.orchestrator.pipeline_runner.Orchestra", return_value=mock_orchestra),
            patch("builtins.input", side_effect=["y", "y", "y"]),
        ):
            result = await run("요구사항", tmp_path)

        assert result is True
        mock_orchestra.run_phases.assert_called_once()
        done_calls = [c for c in mock_orchestra.phase_manager.transition.call_args_list
                      if c.args and c.args[0] == Phase.DONE]
        assert len(done_calls) == 1

    async def test_breakdown_failure_returns_false(self, tmp_path: Path) -> None:
        """태스크 분해 실패 시 False 반환 — run_phases 호출 안 됨."""
        mock_orchestra = _make_orchestra_mock()
        mock_orchestra.run_breakdown = AsyncMock(
            return_value=([], {"output": "파싱 실패", "success": False})
        )

        with (
            patch("src.orchestrator.pipeline_runner.Orchestra", return_value=mock_orchestra),
            patch("builtins.input", side_effect=["y", "y"]),
        ):
            result = await run("요구사항", tmp_path)

        assert result is False
        mock_orchestra.run_phases.assert_not_called()

    async def test_phase_failure_returns_false(self, tmp_path: Path) -> None:
        """Phase 실행 실패 시 False 반환 — Phase.DONE 전환 안 됨."""
        mock_orchestra = _make_orchestra_mock()
        mock_orchestra.run_phases = AsyncMock(
            return_value={"phases": [{"phase_num": 1, "passed": False}], "success": False}
        )

        with (
            patch("src.orchestrator.pipeline_runner.Orchestra", return_value=mock_orchestra),
            patch("builtins.input", side_effect=["y", "y", "y"]),
        ):
            result = await run("요구사항", tmp_path)

        assert result is False
        done_calls = [c for c in mock_orchestra.phase_manager.transition.call_args_list
                      if c.args and c.args[0] == Phase.DONE]
        assert len(done_calls) == 0
