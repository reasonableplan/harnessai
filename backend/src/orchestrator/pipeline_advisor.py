"""Pipeline advisor — maps harness-plan state to the next /ha-* action.

Decision core of the /ha-run driver skill. Pure function of HarnessPlan:
no filesystem access and no gate duplication — BLOCK gates stay in their
owning skills as the single source of truth. This module only computes the
happy-path next step, plus the smoke advisory judgment that needs
cross-step memory (verify_history).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.orchestrator.plan_manager import HarnessPlan, requires_hitl_freeze

# mode 값: auto = 드라이버가 바로 다음 스킬 실행 / hitl = 사용자 개입 지점
MODE_AUTO = "auto"
MODE_HITL = "hitl"


@dataclass(frozen=True)
class Advice:
    """Next pipeline action for the /ha-run driver."""

    action: str  # init|design|plan|build|verify|smoke|review|ship_confirm|done
    mode: str  # MODE_AUTO | MODE_HITL
    skill: str  # skill to invoke (e.g. "/ha-verify"); "" when none
    args: str  # skill arguments (e.g. "--resume"); "" when none
    reason: str  # user-facing explanation (Korean)


def _rework_reason(plan: HarnessPlan) -> str | None:
    """최근 ha-verify FAIL 의 rework_tasks 추출 → reason 문구 생성."""
    for rec in reversed(plan.verify_history):
        if rec.step == "ha-verify" and not rec.passed:
            m = re.search(r"\[rework: ([^\]]+)\]", rec.summary or "")
            if m:
                task_list = m.group(1)
                return f"verify FAIL 원인 태스크 재구현 ({task_list})"
    return None


def _smoke_state(plan: HarnessPlan) -> str:
    """Return 'pending' | 'passed' | 'failed' for the current verify cycle.

    Only smoke records appended after the most recent passing ha-verify count —
    a smoke result from a previous rework cycle validated different code.
    """
    last_verify = -1
    for i, rec in enumerate(plan.verify_history):
        if rec.step == "ha-verify" and rec.passed:
            last_verify = i
    smokes = [
        rec for i, rec in enumerate(plan.verify_history) if rec.step == "smoke" and i > last_verify
    ]
    if not smokes:
        return "pending"
    return "passed" if smokes[-1].passed else "failed"


def advise(plan: HarnessPlan | None) -> Advice:
    """Compute the next action for the given plan state (None = no plan yet)."""
    if plan is None:
        return Advice(
            "init",
            MODE_HITL,
            "/ha-init",
            "",
            "harness-plan.md 없음 — 프로젝트 초기화 인터뷰부터 시작",
        )

    step = plan.pipeline.current_step

    if step == "init":
        scope = "페르소나/기능/화면" if requires_hitl_freeze(plan) else "기능/로직"
        return Advice(
            "design",
            MODE_HITL,
            "/ha-design",
            "",
            f"skeleton 이 비어 있음 — 설계 인터뷰({scope}) 필요",
        )
    if step == "designed":
        if plan.frozen_status != "frozen" and requires_hitl_freeze(plan):
            return Advice(
                "design",
                MODE_HITL,
                "/ha-design",
                "",
                "HITL freeze 미완 — /ha-design 재진입해 LOCKED 섹션(페르소나/기능/화면) 확인 필요",
            )
        return Advice("plan", MODE_AUTO, "/ha-plan", "", "설계 확정 — 태스크 분해 진행")
    if step == "planned":
        return Advice(
            "build",
            MODE_AUTO,
            "/ha-build",
            "--resume",
            "다음 ready 태스크 구현 (--resume 자동 선택)",
        )
    if step == "building":
        rework_reason = _rework_reason(plan)
        reason = rework_reason or "다음 ready 태스크 선택 진행"
        return Advice("build", MODE_AUTO, "/ha-build", "--resume", reason)
    if step == "built":
        return Advice(
            "verify",
            MODE_AUTO,
            "/ha-verify",
            "",
            "전 태스크 resolved — toolchain(test/lint/type) 검증",
        )
    if step == "verified":
        smoke = _smoke_state(plan)
        if smoke == "pending":
            return Advice(
                "smoke",
                MODE_AUTO,
                "/ha-smoke",
                "",
                "런타임 기동 검증 (advisory) — 앱이 실제로 뜨는지 확인",
            )
        if smoke == "failed":
            return Advice(
                "review",
                MODE_HITL,
                "/ha-review",
                "",
                "smoke FAIL (advisory) — 수정 후 재검증할지, 그대로 리뷰로 진행할지 사용자 선택 필요",
            )
        return Advice(
            "review",
            MODE_AUTO,
            "/ha-review",
            "",
            "smoke 통과 — 보안 훅/슬롭/컨벤션 종합 리뷰",
        )
    if step == "reviewed":
        return Advice(
            "ship_confirm",
            MODE_HITL,
            "/ha-ship",
            "",
            "리뷰 승인 완료 — 배포/PR 은 외부 도구로 수행한 뒤 /ha-ship 으로 마킹 (사용자 확인 필요)",
        )
    # "shipped" — Pipeline validates current_step, so this is the only remainder.
    return Advice(
        "done",
        MODE_AUTO,
        "",
        "",
        "파이프라인 완료 (shipped) — 다음 사이클은 /ha-redesign 또는 새 프로젝트",
    )
