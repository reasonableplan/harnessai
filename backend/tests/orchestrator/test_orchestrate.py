"""Orchestra 오케스트레이터 테스트."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.orchestrator.orchestrate import Orchestra
from src.orchestrator.phase import InvalidTransitionError, Phase
from src.orchestrator.pipeline import CheckResult, CheckStatus, ValidationResult
from src.orchestrator.runner import RunResult


# ── 픽스처 ──────────────────────────────────────────────────────────────────


@pytest.fixture
def orchestra(tmp_path: Path) -> Orchestra:
    """실제 agents.yaml을 사용하되, runner/pipeline은 mock하지 않은 Orchestra."""
    backend_dir = Path(__file__).parents[2]  # backend/
    agents_yaml = backend_dir / "agents.yaml"
    # agents.yaml을 tmp_path로 복사해서 사용
    (tmp_path / "agents.yaml").write_text(
        agents_yaml.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return Orchestra(project_dir=tmp_path)


def _make_run_result(
    agent: str,
    *,
    output: str = "출력",
    success: bool = True,
    escalated: bool = False,
    error: str | None = None,
) -> RunResult:
    return RunResult(
        agent=agent,
        output=output,
        success=success,
        duration_ms=100,
        attempts=1,
        error=error,
        escalated=escalated,
    )


def _make_validation_result(*, passed: bool = True) -> ValidationResult:
    status = CheckStatus.PASSED if passed else CheckStatus.FAILED
    return ValidationResult(
        checks=[CheckResult(name="lint:python", status=status, output="ok")]
    )


# ── 초기화 ───────────────────────────────────────────────────────────────────


class TestOrchestraInit:
    def test_init_loads_config(self, orchestra: Orchestra) -> None:
        assert orchestra.config is not None
        assert orchestra.config.architect is not None

    def test_init_creates_state_manager(self, orchestra: Orchestra) -> None:
        assert orchestra.state is not None

    def test_init_creates_phase_manager(self, orchestra: Orchestra) -> None:
        assert orchestra.phase_manager is not None
        assert orchestra.phase_manager.current_phase == Phase.PLANNING

    def test_from_project_dir_factory(self, tmp_path: Path) -> None:
        backend_dir = Path(__file__).parents[2]
        (tmp_path / "agents.yaml").write_text(
            (backend_dir / "agents.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        orch = Orchestra.from_project_dir(tmp_path)
        assert isinstance(orch, Orchestra)
        assert orch.project_dir == tmp_path.resolve()


# ── design() ────────────────────────────────────────────────────────────────


class TestDesign:
    async def test_design_runs_architect_then_designer(self, orchestra: Orchestra) -> None:
        architect_result = _make_run_result("architect", output="아키텍처 설계")
        designer_result = _make_run_result("designer", output="UI 설계")
        call_order: list[str] = []

        async def mock_run(agent: str, prompt: str, **kwargs: object) -> RunResult:
            call_order.append(agent)
            return architect_result if agent == "architect" else designer_result

        orchestra.runner.run = mock_run  # type: ignore[method-assign]

        results = await orchestra.design("요구사항")

        assert call_order == ["architect", "designer"]
        assert results["architect"] is architect_result
        assert results["designer"] is designer_result

    async def test_design_transitions_to_designing(self, orchestra: Orchestra) -> None:
        orchestra.runner.run = AsyncMock(return_value=_make_run_result("architect"))  # type: ignore[method-assign]

        await orchestra.design("요구사항")

        assert orchestra.phase_manager.current_phase == Phase.DESIGNING

    async def test_design_saves_results_to_state(self, orchestra: Orchestra) -> None:
        orchestra.runner.run = AsyncMock(return_value=_make_run_result("architect", output="결과"))  # type: ignore[method-assign]

        await orchestra.design("요구사항")

        saved = orchestra.state.load_task_result("design")
        assert saved is not None
        assert "architect" in saved
        assert "designer" in saved

    async def test_design_passes_architect_output_to_designer(self, orchestra: Orchestra) -> None:
        captured_prompts: dict[str, str] = {}

        async def mock_run(agent: str, prompt: str, **kwargs: object) -> RunResult:
            captured_prompts[agent] = prompt
            return _make_run_result(agent, output=f"{agent} 출력")

        orchestra.runner.run = mock_run  # type: ignore[method-assign]

        await orchestra.design("PM 요구사항")

        assert "architect 출력" in captured_prompts["designer"]

    async def test_design_logs_escalation(self, orchestra: Orchestra, caplog: pytest.LogCaptureFixture) -> None:
        orchestra.runner.run = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_run_result("architect", success=False, escalated=True, error="타임아웃")
        )

        import logging
        with caplog.at_level(logging.WARNING, logger="src.orchestrator.orchestrate"):
            await orchestra.design("요구사항")

        assert any("에스컬레이션" in r.message for r in caplog.records)

    async def test_design_logs_failure(self, orchestra: Orchestra, caplog: pytest.LogCaptureFixture) -> None:
        orchestra.runner.run = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_run_result("architect", success=False, error="실패")
        )

        import logging
        with caplog.at_level(logging.ERROR, logger="src.orchestrator.orchestrate"):
            await orchestra.design("요구사항")

        assert any("실행 실패" in r.message for r in caplog.records)


# ── implement() ─────────────────────────────────────────────────────────────


class TestImplement:
    async def test_implement_runs_specified_agent(self, orchestra: Orchestra) -> None:
        expected = _make_run_result("backend_coder", output="코드")
        orchestra.runner.run = AsyncMock(return_value=expected)  # type: ignore[method-assign]

        # PLANNING → DESIGNING → TASK_BREAKDOWN → IMPLEMENTING 순서로 강제 전이
        orchestra.phase_manager._current = Phase.TASK_BREAKDOWN

        result = await orchestra.implement("task-001", "backend_coder", "API 구현")

        assert result is expected
        orchestra.runner.run.assert_called_once_with("backend_coder", "API 구현")

    async def test_implement_transitions_to_implementing(self, orchestra: Orchestra) -> None:
        orchestra.runner.run = AsyncMock(return_value=_make_run_result("backend_coder"))  # type: ignore[method-assign]
        orchestra.phase_manager._current = Phase.TASK_BREAKDOWN

        await orchestra.implement("task-001", "backend_coder", "API 구현")

        assert orchestra.phase_manager.current_phase == Phase.IMPLEMENTING

    async def test_implement_saves_task_result(self, orchestra: Orchestra) -> None:
        orchestra.runner.run = AsyncMock(return_value=_make_run_result("backend_coder", output="코드"))  # type: ignore[method-assign]
        orchestra.phase_manager._current = Phase.TASK_BREAKDOWN

        await orchestra.implement("task-001", "backend_coder", "API 구현")

        saved = orchestra.state.load_task_result("task-001")
        assert saved is not None
        assert saved["agent"] == "backend_coder"
        assert saved["output"] == "코드"

    async def test_implement_does_not_retransition_if_already_implementing(
        self, orchestra: Orchestra
    ) -> None:
        orchestra.runner.run = AsyncMock(return_value=_make_run_result("frontend_coder"))  # type: ignore[method-assign]
        orchestra.phase_manager._current = Phase.IMPLEMENTING

        # IMPLEMENTING 상태에서 다시 implement 호출 → 전이 없이 그냥 실행
        result = await orchestra.implement("task-002", "frontend_coder", "UI 구현")

        assert result.success is True
        assert orchestra.phase_manager.current_phase == Phase.IMPLEMENTING

    async def test_implement_frontend_coder(self, orchestra: Orchestra) -> None:
        expected = _make_run_result("frontend_coder", output="컴포넌트")
        orchestra.runner.run = AsyncMock(return_value=expected)  # type: ignore[method-assign]
        orchestra.phase_manager._current = Phase.TASK_BREAKDOWN

        result = await orchestra.implement("task-fe-001", "frontend_coder", "컴포넌트 구현")

        assert result is expected


# ── verify() ────────────────────────────────────────────────────────────────


class TestVerify:
    async def test_verify_runs_pipeline_and_reviewer(self, orchestra: Orchestra) -> None:
        orchestra.phase_manager._current = Phase.IMPLEMENTING

        validation = _make_validation_result(passed=True)
        reviewer_result = _make_run_result("reviewer", output="LGTM")

        orchestra.pipeline.run_all = AsyncMock(return_value=validation)  # type: ignore[method-assign]
        orchestra.runner.run = AsyncMock(return_value=reviewer_result)  # type: ignore[method-assign]

        result = await orchestra.verify("task-001")

        assert result["pipeline"] is validation
        assert result["reviewer"] is reviewer_result
        assert result["passed"] is True

    async def test_verify_pipeline_fail_transitions_back_to_implementing(
        self, orchestra: Orchestra
    ) -> None:
        orchestra.phase_manager._current = Phase.IMPLEMENTING

        orchestra.pipeline.run_all = AsyncMock(return_value=_make_validation_result(passed=False))  # type: ignore[method-assign]
        orchestra.runner.run = AsyncMock(return_value=_make_run_result("reviewer"))  # type: ignore[method-assign]

        result = await orchestra.verify("task-001")

        assert result["passed"] is False
        assert orchestra.phase_manager.current_phase == Phase.IMPLEMENTING

    async def test_verify_reviewer_fail_transitions_back_to_implementing(
        self, orchestra: Orchestra
    ) -> None:
        orchestra.phase_manager._current = Phase.IMPLEMENTING

        orchestra.pipeline.run_all = AsyncMock(return_value=_make_validation_result(passed=True))  # type: ignore[method-assign]
        orchestra.runner.run = AsyncMock(  # type: ignore[method-assign]
            return_value=_make_run_result("reviewer", success=False, error="reject")
        )

        result = await orchestra.verify("task-001")

        assert result["passed"] is False
        assert orchestra.phase_manager.current_phase == Phase.IMPLEMENTING

    async def test_verify_saves_result(self, orchestra: Orchestra) -> None:
        orchestra.phase_manager._current = Phase.IMPLEMENTING

        orchestra.pipeline.run_all = AsyncMock(return_value=_make_validation_result(passed=True))  # type: ignore[method-assign]
        orchestra.runner.run = AsyncMock(return_value=_make_run_result("reviewer"))  # type: ignore[method-assign]

        await orchestra.verify("task-001")

        saved = orchestra.state.load_task_result("verify_task-001")
        assert saved is not None
        assert saved["passed"] is True

    async def test_verify_transitions_to_verifying(self, orchestra: Orchestra) -> None:
        orchestra.phase_manager._current = Phase.IMPLEMENTING

        orchestra.pipeline.run_all = AsyncMock(return_value=_make_validation_result(passed=True))  # type: ignore[method-assign]
        orchestra.runner.run = AsyncMock(return_value=_make_run_result("reviewer"))  # type: ignore[method-assign]

        await orchestra.verify("task-001")

        # passed=True → VERIFYING 유지 (DEPLOYING 전이는 run_full_pipeline에서)
        # passed=False → IMPLEMENTING으로 되돌아감
        # 여기서는 passed=True이므로 VERIFYING
        assert orchestra.phase_manager.current_phase == Phase.VERIFYING


# ── run_phase() ──────────────────────────────────────────────────────────────


class TestRunPhase:
    async def test_planning_returns_none(self, orchestra: Orchestra) -> None:
        result = await orchestra.run_phase(Phase.PLANNING, "프롬프트")
        assert result is None

    async def test_deploying_returns_none(self, orchestra: Orchestra) -> None:
        result = await orchestra.run_phase(Phase.DEPLOYING, "프롬프트")
        assert result is None

    async def test_done_returns_none(self, orchestra: Orchestra) -> None:
        result = await orchestra.run_phase(Phase.DONE, "프롬프트")
        assert result is None

    async def test_designing_runs_designer_last(self, orchestra: Orchestra) -> None:
        """DESIGNING Phase — 마지막 에이전트(designer) 결과 반환."""
        designer_result = _make_run_result("designer", output="UI 설계")
        call_order: list[str] = []

        async def mock_run(agent: str, prompt: str, **kwargs: object) -> RunResult:
            call_order.append(agent)
            return _make_run_result(agent)

        orchestra.runner.run = mock_run  # type: ignore[method-assign]

        await orchestra.run_phase(Phase.DESIGNING, "설계해줘")

        assert call_order == ["architect", "designer"]

    async def test_implementing_uses_agent_kwarg(self, orchestra: Orchestra) -> None:
        called_with: list[str] = []

        async def mock_run(agent: str, prompt: str, **kwargs: object) -> RunResult:
            called_with.append(agent)
            return _make_run_result(agent)

        orchestra.runner.run = mock_run  # type: ignore[method-assign]

        await orchestra.run_phase(Phase.IMPLEMENTING, "코드 작성", agent="frontend_coder")

        assert called_with == ["frontend_coder"]

    async def test_task_breakdown_runs_orchestrator(self, orchestra: Orchestra) -> None:
        called_with: list[str] = []

        async def mock_run(agent: str, prompt: str, **kwargs: object) -> RunResult:
            called_with.append(agent)
            return _make_run_result(agent)

        orchestra.runner.run = mock_run  # type: ignore[method-assign]

        await orchestra.run_phase(Phase.TASK_BREAKDOWN, "태스크 분류")

        assert called_with == ["orchestrator"]


# ── run_full_pipeline() ──────────────────────────────────────────────────────


class TestRunFullPipeline:
    async def test_full_pipeline_runs_all_stages(self, orchestra: Orchestra) -> None:
        run_calls: list[str] = []

        async def mock_run(agent: str, prompt: str, **kwargs: object) -> RunResult:
            run_calls.append(agent)
            return _make_run_result(agent)

        orchestra.runner.run = mock_run  # type: ignore[method-assign]
        orchestra.pipeline.run_all = AsyncMock(return_value=_make_validation_result(passed=True))  # type: ignore[method-assign]

        tasks = [
            {"id": "task-001", "agent": "backend_coder", "prompt": "API 구현"},
            {"id": "task-002", "agent": "frontend_coder", "prompt": "UI 구현"},
        ]
        result = await orchestra.run_full_pipeline("요구사항", tasks)

        assert "architect" in run_calls
        assert "designer" in run_calls
        assert "orchestrator" in run_calls
        assert "backend_coder" in run_calls
        assert "frontend_coder" in run_calls
        assert "reviewer" in run_calls

        assert "design" in result
        assert "tasks" in result
        assert "task-001" in result["tasks"]
        assert "task-002" in result["tasks"]

    async def test_full_pipeline_success_flag_true_when_all_pass(
        self, orchestra: Orchestra
    ) -> None:
        orchestra.runner.run = AsyncMock(return_value=_make_run_result("agent"))  # type: ignore[method-assign]
        orchestra.pipeline.run_all = AsyncMock(return_value=_make_validation_result(passed=True))  # type: ignore[method-assign]

        tasks = [{"id": "task-001", "agent": "backend_coder", "prompt": "구현"}]
        result = await orchestra.run_full_pipeline("요구사항", tasks)

        assert result["success"] is True

    async def test_full_pipeline_success_false_when_verify_fails(
        self, orchestra: Orchestra
    ) -> None:
        orchestra.runner.run = AsyncMock(return_value=_make_run_result("agent"))  # type: ignore[method-assign]
        orchestra.pipeline.run_all = AsyncMock(return_value=_make_validation_result(passed=False))  # type: ignore[method-assign]

        tasks = [{"id": "task-001", "agent": "backend_coder", "prompt": "구현"}]
        result = await orchestra.run_full_pipeline("요구사항", tasks)

        assert result["success"] is False

    async def test_full_pipeline_empty_tasks(self, orchestra: Orchestra) -> None:
        orchestra.runner.run = AsyncMock(return_value=_make_run_result("agent"))  # type: ignore[method-assign]
        orchestra.pipeline.run_all = AsyncMock(return_value=_make_validation_result(passed=True))  # type: ignore[method-assign]

        result = await orchestra.run_full_pipeline("요구사항", [])

        assert result["success"] is True
        assert result["tasks"] == {}
