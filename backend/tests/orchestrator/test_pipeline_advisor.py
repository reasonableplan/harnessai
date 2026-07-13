"""pipeline_advisor 단위 테스트 — 파이프라인 상태 → 다음 /ha-* 행동 매핑.

/ha-run 자동 드라이버의 결정 코어. 게이트 복제 없음 검증 포함:
advisor 는 HarnessPlan 만 읽는 순수 함수여야 한다 (파일시스템 접근 없음).
"""

from __future__ import annotations

from src.orchestrator.pipeline_advisor import MODE_AUTO, MODE_HITL, advise
from src.orchestrator.plan_manager import (
    HarnessPlan,
    Pipeline,
    PlanManager,
    SkeletonSpec,
    VerifyRecord,
)


def _plan(
    step: str, *, frozen: bool = True, included: tuple[str, ...] = ("requirements",)
) -> HarnessPlan:
    plan = PlanManager().create(
        project_name="t",
        project_type="python-cli",
        scale="small",
        user_description_original="",
        profiles=[],
        skeleton_sections=SkeletonSpec((), (), included),
        pipeline_steps=["init"],
    )
    plan.pipeline = Pipeline(
        steps=("init",),
        current_step=step,
        completed_steps=(),
        skipped_steps=(),
    )
    if frozen:
        plan.frozen_status = "frozen"
    return plan


def _rec(step: str, passed: bool) -> VerifyRecord:
    return VerifyRecord(step=step, at="2026-07-02T00:00:00+00:00", passed=passed, summary="")


def test_no_plan_advises_init_hitl() -> None:
    advice = advise(None)
    assert advice.action == "init"
    assert advice.mode == MODE_HITL
    assert advice.skill == "/ha-init"


def test_init_advises_design_hitl() -> None:
    advice = advise(_plan("init", frozen=False))
    assert advice.action == "design"
    assert advice.mode == MODE_HITL
    assert advice.skill == "/ha-design"


def test_init_reason_mentions_persona_only_when_lockable() -> None:
    """dogfood #2: persona/screen 섹션 있는 프로젝트만 reason 에 그 표현 사용."""
    with_lockable = advise(_plan("init", frozen=False, included=("requirements", "view.screens")))
    assert "페르소나" in with_lockable.reason or "화면" in with_lockable.reason


def test_init_reason_no_persona_for_cli() -> None:
    """CLI/라이브러리: lockable 섹션 없으면 reason 에 페르소나/화면 언급 안 함."""
    cli = advise(_plan("init", frozen=False, included=("interface.cli", "core.logic")))
    assert "페르소나" not in cli.reason
    assert "화면" not in cli.reason


def test_designed_with_lockable_not_frozen_advises_design_reentry() -> None:
    """persona/screen 섹션이 활성인데 freeze 미완 → HITL 인터뷰 재진입."""
    advice = advise(_plan("designed", frozen=False, included=("requirements",)))
    assert advice.action == "design"
    assert advice.mode == MODE_HITL


def test_designed_no_lockable_not_frozen_advises_plan_auto() -> None:
    """CLI/라이브러리처럼 HITL-lockable 섹션이 없으면 freeze 불필요 →
    non-frozen 이어도 바로 plan (designed→design 무한루프 회귀 방지)."""
    advice = advise(_plan("designed", frozen=False, included=("interface.cli", "core.logic")))
    assert advice.action == "plan"
    assert advice.mode == MODE_AUTO
    assert advice.skill == "/ha-plan"


def test_designed_frozen_advises_plan_auto() -> None:
    advice = advise(_plan("designed"))
    assert advice.action == "plan"
    assert advice.mode == MODE_AUTO
    assert advice.skill == "/ha-plan"


def test_planned_advises_build_resume() -> None:
    advice = advise(_plan("planned"))
    assert advice.action == "build"
    assert advice.mode == MODE_AUTO
    assert advice.skill == "/ha-build"
    assert advice.args == "--resume"


def test_building_advises_build_resume() -> None:
    advice = advise(_plan("building"))
    assert advice.action == "build"
    assert advice.args == "--resume"


def test_building_with_rework_reason_includes_task_id() -> None:
    """verify_history 마지막 ha-verify FAIL 에 [rework: T-003] 마킹 → reason 에 T-003 포함."""
    plan = _plan("building")
    plan.verify_history.append(
        VerifyRecord(
            step="ha-verify",
            at="2026-07-03T00:00:00+00:00",
            passed=False,
            summary="toolchain failed [rework: T-003]",
        )
    )
    advice = advise(plan)
    assert advice.action == "build"
    assert "T-003" in advice.reason


def test_building_without_rework_reason_uses_default() -> None:
    """verify_history 마지막 ha-verify 가 PASS 이거나 rework 마킹 없음 → 기본 문구 사용."""
    plan = _plan("building")
    plan.verify_history.append(_rec("ha-verify", passed=True))
    advice = advise(plan)
    assert advice.action == "build"
    assert "T-" not in advice.reason


def test_built_advises_verify_auto() -> None:
    advice = advise(_plan("built"))
    assert advice.action == "verify"
    assert advice.mode == MODE_AUTO
    assert advice.skill == "/ha-verify"


def test_verified_without_smoke_advises_smoke() -> None:
    plan = _plan("verified")
    plan.verify_history.append(_rec("ha-verify", passed=True))
    advice = advise(plan)
    assert advice.action == "smoke"
    assert advice.mode == MODE_AUTO
    assert advice.skill == "/ha-smoke"


def test_verified_smoke_passed_advises_accept_auto() -> None:
    """smoke 통과 후 다음 advisory 칸은 수용검증(/ha-accept) — 리뷰 전에 제안."""
    plan = _plan("verified")
    plan.verify_history.append(_rec("ha-verify", passed=True))
    plan.verify_history.append(_rec("smoke", passed=True))
    advice = advise(plan)
    assert advice.action == "accept"
    assert advice.mode == MODE_AUTO
    assert advice.skill == "/ha-accept"


def test_verified_smoke_and_accept_passed_advises_review_auto() -> None:
    plan = _plan("verified")
    plan.verify_history.append(_rec("ha-verify", passed=True))
    plan.verify_history.append(_rec("smoke", passed=True))
    plan.verify_history.append(_rec("accept", passed=True))
    advice = advise(plan)
    assert advice.action == "review"
    assert advice.mode == MODE_AUTO
    assert advice.skill == "/ha-review"


def test_verified_accept_failed_advises_review_hitl() -> None:
    """accept 는 advisory — FAIL 이면 진행/수정을 사용자가 선택 (smoke 와 동일 시맨틱)."""
    plan = _plan("verified")
    plan.verify_history.append(_rec("ha-verify", passed=True))
    plan.verify_history.append(_rec("smoke", passed=True))
    plan.verify_history.append(_rec("accept", passed=False))
    advice = advise(plan)
    assert advice.action == "review"
    assert advice.mode == MODE_HITL
    assert "accept" in advice.reason


def test_verified_stale_accept_from_previous_cycle_advises_accept_again() -> None:
    """이전 rework 사이클의 accept 기록은 무효 — 마지막 성공 ha-verify 이후 기록만 인정."""
    plan = _plan("verified")
    plan.verify_history.append(_rec("accept", passed=True))
    plan.verify_history.append(_rec("ha-verify", passed=False))
    plan.verify_history.append(_rec("ha-verify", passed=True))
    plan.verify_history.append(_rec("smoke", passed=True))
    advice = advise(plan)
    assert advice.action == "accept"


def test_verified_smoke_failed_advises_review_hitl() -> None:
    """smoke 는 advisory — FAIL 이면 진행/수정을 사용자가 선택 (자동 진행 금지)."""
    plan = _plan("verified")
    plan.verify_history.append(_rec("ha-verify", passed=True))
    plan.verify_history.append(_rec("smoke", passed=False))
    advice = advise(plan)
    assert advice.action == "review"
    assert advice.mode == MODE_HITL


def test_verified_stale_smoke_from_previous_cycle_advises_smoke_again() -> None:
    """이전 rework 사이클의 smoke 기록은 무효 — 마지막 성공 ha-verify 이후 기록만 인정."""
    plan = _plan("verified")
    plan.verify_history.append(_rec("smoke", passed=True))
    plan.verify_history.append(_rec("ha-verify", passed=False))
    plan.verify_history.append(_rec("ha-verify", passed=True))
    advice = advise(plan)
    assert advice.action == "smoke"


def test_reviewed_advises_ship_confirm_hitl() -> None:
    """배포/PR 은 외부 행위 — 드라이버가 자동으로 shipped 마킹하면 안 됨."""
    advice = advise(_plan("reviewed"))
    assert advice.action == "ship_confirm"
    assert advice.mode == MODE_HITL
    assert advice.skill == "/ha-ship"


def test_shipped_advises_done() -> None:
    advice = advise(_plan("shipped"))
    assert advice.action == "done"
    assert advice.skill == ""


def test_every_advice_has_nonempty_reason() -> None:
    plans = [None] + [
        _plan(s)
        for s in ("init", "designed", "planned", "building", "built", "reviewed", "shipped")
    ]
    for p in plans:
        assert advise(p).reason.strip(), f"reason 누락: {p and p.pipeline.current_step}"


def test_building_after_review_reject_reports_rework_reason() -> None:
    """ha-review REJECT 로 회귀한 경우도 rework 사유를 보고 (verify FAIL 과 동일 취급).

    REJECT 는 needs_rebuild 를 내리고 building 으로 회귀시킨다. advisor 가 ha-verify
    엔트리만 보면 "다음 ready 태스크 선택 진행" 이라는 엉뚱한 이유를 말한다.
    """
    plan = _plan("building")
    plan.verify_history.append(
        VerifyRecord(
            step="ha-review",
            at="2026-07-13T00:00:00+00:00",
            passed=False,
            summary="WARN 7건 [rework: T-005, T-007]",
        )
    )
    advice = advise(plan)
    assert advice.action == "build"
    assert "T-005" in advice.reason
    assert "review" in advice.reason.lower() or "리뷰" in advice.reason
