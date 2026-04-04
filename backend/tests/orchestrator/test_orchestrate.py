"""Orchestra 오케스트레이터 테스트."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.orchestrator.orchestrate import Orchestra
from src.orchestrator.output_parser import PhaseReviewResult, ReviewVerdict
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

        # passed=True → VERIFYING 유지 (DEPLOYING 전이는 run_pipeline_with_phases에서)
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


# ── implement_with_retry() ───────────────────────────────────────────────────


class TestImplementWithRetry:
    async def test_approve_on_first_attempt(self, orchestra: Orchestra) -> None:
        orchestra.phase_manager._current = Phase.TASK_BREAKDOWN
        orchestra.runner.run = AsyncMock(
            return_value=_make_run_result("backend_coder", output="## Review Result: APPROVE")
        )  # type: ignore[method-assign]
        orchestra.pipeline.run_all = AsyncMock(return_value=_make_validation_result(passed=True))  # type: ignore[method-assign]

        result = await orchestra.implement_with_retry("T-001", "backend_coder", "구현")

        assert result["passed"] is True
        assert result["attempts"] == 1

    async def test_max_retries_exceeded_returns_failed(self, orchestra: Orchestra) -> None:
        orchestra.phase_manager._current = Phase.TASK_BREAKDOWN
        orchestra.runner.run = AsyncMock(
            return_value=_make_run_result("reviewer", output="## Review Result: REJECT")
        )  # type: ignore[method-assign]
        orchestra.pipeline.run_all = AsyncMock(return_value=_make_validation_result(passed=True))  # type: ignore[method-assign]

        result = await orchestra.implement_with_retry("T-001", "backend_coder", "구현", max_retries=2)

        assert result["passed"] is False
        assert result["attempts"] == 2

    async def test_retry_prompt_includes_violations(self, orchestra: Orchestra) -> None:
        orchestra.phase_manager._current = Phase.TASK_BREAKDOWN
        captured_prompts: list[str] = []

        async def mock_run(agent: str, prompt: str, **kwargs: object) -> RunResult:
            if agent == "backend_coder":
                captured_prompts.append(prompt)
                return _make_run_result(agent)
            if agent == "reviewer":
                if len(captured_prompts) == 1:
                    return _make_run_result(
                        agent,
                        output="## Review Result: REJECT\n### 위반 사항\n1. raw SQL 사용",
                    )
                return _make_run_result(agent, output="## Review Result: APPROVE")
            return _make_run_result(agent)

        orchestra.runner.run = mock_run  # type: ignore[method-assign]
        orchestra.pipeline.run_all = AsyncMock(return_value=_make_validation_result(passed=True))  # type: ignore[method-assign]

        await orchestra.implement_with_retry("T-001", "backend_coder", "구현", max_retries=3)

        assert len(captured_prompts) >= 2
        assert "review_feedback" in captured_prompts[1]
        assert "raw SQL" in captured_prompts[1]

    async def test_passed_true_on_pipeline_and_approve(self, orchestra: Orchestra) -> None:
        orchestra.phase_manager._current = Phase.TASK_BREAKDOWN
        orchestra.runner.run = AsyncMock(
            return_value=_make_run_result("reviewer", output="## Review Result: APPROVE")
        )  # type: ignore[method-assign]
        orchestra.pipeline.run_all = AsyncMock(return_value=_make_validation_result(passed=True))  # type: ignore[method-assign]

        result = await orchestra.implement_with_retry("T-002", "frontend_coder", "UI")

        assert result["passed"] is True
        assert "implement" in result
        assert "verify" in result


# ── review_phase() ───────────────────────────────────────────────────────────


class TestReviewPhase:
    async def test_approve_returns_phase_review_result(self, orchestra: Orchestra) -> None:
        orchestra.phase_manager._current = Phase.IMPLEMENTING
        orchestra.runner.run = AsyncMock(
            return_value=_make_run_result(
                "reviewer",
                output="## Phase 1 Review Result: APPROVE\n\n### 다음 Phase 진행 가능 여부\n- 가능",
            )
        )  # type: ignore[method-assign]
        orchestra.state.save_task_result("T-001", {"output": "구현 완료"})

        result = await orchestra.review_phase(1, ["T-001"])

        assert result is not None
        assert result.verdict == ReviewVerdict.APPROVE
        assert result.can_proceed is True

    async def test_reject_returns_phase_review_result(self, orchestra: Orchestra) -> None:
        orchestra.phase_manager._current = Phase.IMPLEMENTING
        orchestra.runner.run = AsyncMock(
            return_value=_make_run_result(
                "reviewer",
                output=(
                    "## Phase 1 Review Result: REJECT\n\n"
                    "### 미구현 항목\n- API: POST /issues — 구현 없음\n\n"
                    "### 다음 Phase 진행 가능 여부\n- 불가"
                ),
            )
        )  # type: ignore[method-assign]

        result = await orchestra.review_phase(1, ["T-001"])

        assert result is not None
        assert result.verdict == ReviewVerdict.REJECT
        assert result.can_proceed is False
        assert len(result.missing_items) == 1

    async def test_parse_failure_returns_none(self, orchestra: Orchestra) -> None:
        orchestra.phase_manager._current = Phase.IMPLEMENTING
        orchestra.runner.run = AsyncMock(
            return_value=_make_run_result("reviewer", output="리뷰 결과 없음")
        )  # type: ignore[method-assign]

        result = await orchestra.review_phase(1, [])

        assert result is None

    async def test_saves_result_to_state(self, orchestra: Orchestra) -> None:
        orchestra.phase_manager._current = Phase.IMPLEMENTING
        orchestra.runner.run = AsyncMock(
            return_value=_make_run_result("reviewer", output="## Phase 2 Review Result: APPROVE")
        )  # type: ignore[method-assign]

        await orchestra.review_phase(2, [])

        saved = orchestra.state.load_task_result("phase_2_review")
        assert saved is not None


# ── run_pipeline_with_phases() ───────────────────────────────────────────────


class TestRunPipelineWithPhases:
    async def test_single_phase_approve(self, orchestra: Orchestra) -> None:
        async def mock_run(agent: str, prompt: str, **kwargs: object) -> RunResult:
            if agent == "reviewer":
                return _make_run_result(
                    agent,
                    output=(
                        "## Review Result: APPROVE\n"
                        "## Phase 1 Review Result: APPROVE\n"
                        "### 다음 Phase 진행 가능 여부\n- 가능"
                    ),
                )
            return _make_run_result(agent)

        orchestra.runner.run = mock_run  # type: ignore[method-assign]
        orchestra.pipeline.run_all = AsyncMock(return_value=_make_validation_result(passed=True))  # type: ignore[method-assign]

        phases = [[{"id": "T-001", "agent": "backend_coder", "prompt": "구현"}]]
        result = await orchestra.run_pipeline_with_phases("요구사항", phases)

        assert result["success"] is True
        assert len(result["phases"]) == 1
        assert result["phases"][0]["passed"] is True

    async def test_phase_reject_stops_pipeline(self, orchestra: Orchestra) -> None:
        async def mock_run(agent: str, prompt: str, **kwargs: object) -> RunResult:
            if agent == "reviewer":
                return _make_run_result(
                    agent,
                    output=(
                        "## Review Result: APPROVE\n"
                        "## Phase 1 Review Result: REJECT\n"
                        "### 다음 Phase 진행 가능 여부\n- 불가"
                    ),
                )
            return _make_run_result(agent)

        orchestra.runner.run = mock_run  # type: ignore[method-assign]
        orchestra.pipeline.run_all = AsyncMock(return_value=_make_validation_result(passed=True))  # type: ignore[method-assign]

        phases = [
            [{"id": "T-001", "agent": "backend_coder", "prompt": "구현"}],
            [{"id": "T-010", "agent": "frontend_coder", "prompt": "구현"}],
        ]
        result = await orchestra.run_pipeline_with_phases("요구사항", phases, max_phase_retries=1)

        assert result["success"] is False
        # Phase 1 실패로 Phase 2는 실행 안 됨
        assert len(result["phases"]) == 1

    async def test_design_result_included(self, orchestra: Orchestra) -> None:
        async def mock_run(agent: str, prompt: str, **kwargs: object) -> RunResult:
            if agent == "reviewer":
                return _make_run_result(
                    agent,
                    output=(
                        "## Review Result: APPROVE\n"
                        "## Phase 1 Review Result: APPROVE\n"
                        "### 다음 Phase 진행 가능 여부\n- 가능"
                    ),
                )
            return _make_run_result(agent)

        orchestra.runner.run = mock_run  # type: ignore[method-assign]
        orchestra.pipeline.run_all = AsyncMock(return_value=_make_validation_result(passed=True))  # type: ignore[method-assign]

        phases = [[{"id": "T-001", "agent": "backend_coder", "prompt": "구현"}]]
        result = await orchestra.run_pipeline_with_phases("요구사항", phases)

        assert "design" in result
        assert "architect" in result["design"]

    async def test_two_phases_both_approve(self, orchestra: Orchestra) -> None:
        phase_review_counts: dict[int, int] = {1: 0, 2: 0}

        async def mock_run(agent: str, prompt: str, **kwargs: object) -> RunResult:
            if agent == "reviewer" and "Phase 1" in prompt:
                phase_review_counts[1] += 1
                return _make_run_result(
                    agent,
                    output=(
                        "## Review Result: APPROVE\n"
                        "## Phase 1 Review Result: APPROVE\n"
                        "### 다음 Phase 진행 가능 여부\n- 가능"
                    ),
                )
            if agent == "reviewer" and "Phase 2" in prompt:
                phase_review_counts[2] += 1
                return _make_run_result(
                    agent,
                    output=(
                        "## Review Result: APPROVE\n"
                        "## Phase 2 Review Result: APPROVE\n"
                        "### 다음 Phase 진행 가능 여부\n- 가능"
                    ),
                )
            if agent == "reviewer":
                return _make_run_result(agent, output="## Review Result: APPROVE")
            return _make_run_result(agent)

        orchestra.runner.run = mock_run  # type: ignore[method-assign]
        orchestra.pipeline.run_all = AsyncMock(return_value=_make_validation_result(passed=True))  # type: ignore[method-assign]

        phases = [
            [{"id": "T-001", "agent": "backend_coder", "prompt": "구현"}],
            [{"id": "T-010", "agent": "frontend_coder", "prompt": "구현"}],
        ]
        result = await orchestra.run_pipeline_with_phases("요구사항", phases)

        assert result["success"] is True
        assert len(result["phases"]) == 2
        assert result["phases"][0]["passed"] is True
        assert result["phases"][1]["passed"] is True

    async def test_phase_done_on_success(self, orchestra: Orchestra) -> None:
        """전체 성공 시 Phase.DONE으로 전환되는지 확인."""
        async def mock_run(agent: str, prompt: str, **kwargs: object) -> RunResult:
            if agent == "reviewer":
                return _make_run_result(
                    agent,
                    output=(
                        "## Review Result: APPROVE\n"
                        "## Phase 1 Review Result: APPROVE\n"
                        "### 다음 Phase 진행 가능 여부\n- 가능"
                    ),
                )
            return _make_run_result(agent)

        orchestra.runner.run = mock_run  # type: ignore[method-assign]
        orchestra.pipeline.run_all = AsyncMock(return_value=_make_validation_result(passed=True))  # type: ignore[method-assign]

        await orchestra.run_pipeline_with_phases(
            "요구사항",
            [[{"id": "T-001", "agent": "backend_coder", "prompt": "구현"}]],
        )

        assert orchestra.phase_manager.current_phase == Phase.DONE

    async def test_phase_not_done_on_failure(self, orchestra: Orchestra) -> None:
        """Phase 실패 시 Phase.DONE으로 전환하지 않는지 확인."""
        async def mock_run(agent: str, prompt: str, **kwargs: object) -> RunResult:
            if agent == "reviewer":
                return _make_run_result(
                    agent,
                    output=(
                        "## Review Result: REJECT\n"
                        "## Phase 1 Review Result: REJECT\n"
                        "### 다음 Phase 진행 가능 여부\n- 불가"
                    ),
                )
            return _make_run_result(agent)

        orchestra.runner.run = mock_run  # type: ignore[method-assign]
        orchestra.pipeline.run_all = AsyncMock(return_value=_make_validation_result(passed=True))  # type: ignore[method-assign]

        result = await orchestra.run_pipeline_with_phases(
            "요구사항",
            [[{"id": "T-001", "agent": "backend_coder", "prompt": "구현"}]],
        )

        assert result["success"] is False
        assert orchestra.phase_manager.current_phase != Phase.DONE


# ── materialize_skeleton() ───────────────────────────────────────────────────


class TestMaterializeSkeleton:
    def test_creates_skeleton_md(self, orchestra: Orchestra, tmp_path: Path) -> None:
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "skeleton_template.md").write_text(
            "## 6. DB 스키마\n_미작성_\n\n## 7. API 스키마\n_미작성_\n",
            encoding="utf-8",
        )

        architect_out = "## 6. DB 스키마\n| id | UUID |\n"
        designer_out = "## 7. API 스키마\n| GET | /api |\n"

        path = orchestra.materialize_skeleton(architect_out, designer_out)

        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "| id | UUID |" in content
        assert "| GET | /api |" in content

    def test_no_template_creates_empty_skeleton(self, orchestra: Orchestra) -> None:
        path = orchestra.materialize_skeleton("출력 A", "출력 B")

        assert path.exists()

    def test_no_sections_extracted_copies_template(
        self, orchestra: Orchestra, tmp_path: Path
    ) -> None:
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        template_content = "## 6. DB 스키마\n_미작성_\n"
        (docs_dir / "skeleton_template.md").write_text(template_content, encoding="utf-8")

        # 섹션 헤딩 없는 출력
        orchestra.materialize_skeleton("일반 텍스트", "일반 텍스트")

        skeleton_path = tmp_path / "docs" / "skeleton.md"
        assert skeleton_path.read_text(encoding="utf-8") == template_content

    def test_run_pipeline_with_phases_calls_materialize(
        self, orchestra: Orchestra, tmp_path: Path
    ) -> None:
        """run_pipeline_with_phases가 design() 후 skeleton.md를 생성하는지 확인."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        async def mock_run(agent: str, prompt: str, **kwargs: object) -> RunResult:
            if agent == "architect":
                return _make_run_result(agent, output="## 6. DB 스키마\n| id | UUID |\n")
            if agent == "reviewer":
                return _make_run_result(
                    agent,
                    output=(
                        "## Review Result: APPROVE\n"
                        "## Phase 1 Review Result: APPROVE\n"
                        "### 다음 Phase 진행 가능 여부\n- 가능"
                    ),
                )
            return _make_run_result(agent)

        orchestra.runner.run = mock_run  # type: ignore[method-assign]
        orchestra.pipeline.run_all = AsyncMock(return_value=_make_validation_result(passed=True))  # type: ignore[method-assign]

        import asyncio
        asyncio.get_event_loop().run_until_complete(
            orchestra.run_pipeline_with_phases(
                "요구사항",
                [[{"id": "T-001", "agent": "backend_coder", "prompt": "구현"}]],
            )
        )

        skeleton_path = tmp_path / "docs" / "skeleton.md"
        assert skeleton_path.exists()
        assert "| id | UUID |" in skeleton_path.read_text(encoding="utf-8")
