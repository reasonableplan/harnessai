#!/usr/bin/env python3
"""HarnessAI v2 — `/ha-redesign` 백엔드.

Mutation propagation entry point. When a decision changes (CEO pivot, eng review
correction, requirement update), this skill records the change and surfaces the
skeleton/tasks context so an Architect+Designer agent can propose a re-derivation.

Phase 2 scope (this file):
- prepare: collect skeleton + tasks context, record a "proposed" entry, return
  JSON for downstream Agent invocation.
- commit:  append the next lifecycle entry (approved | applied | rejected) so
  the audit trail captures what actually happened.

Phase 3 (later) will add the Agent prompt + diff approval flow on top of this.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "_ha_shared"))
from utils import (  # noqa: E402, I001
    HARNESS_HOME,
    SKELETON_HEADING_RE,
    TASK_ROW_RE,
    assert_state,
    get_active_profiles,
    info,
    load_plan,
    save_plan,
)

# backend src import — utils.py 가 backend/ 를 sys.path 에 추가 보장
from src.orchestrator.skeleton_hash import (  # noqa: E402
    check_skeleton_hash,
    compute_skeleton_hash,
)

# Redesign is meaningful only after the initial design exists. "init" has nothing
# to re-derive; "shipped" is treated as immutable (a released artifact must not
# silently mutate). Every state in between allows redesign — pivots can land at
# any phase.
_REDESIGN_ALLOWED_STATES = [
    "designed",
    "planned",
    "building",
    "built",
    "verified",
    "reviewed",
]


def _read_text_or_fail(path: Path, label: str) -> str | None:
    """Read text with OSError surfacing as info() + None return.

    Returning None lets the caller emit an explicit [FAIL] message and stop the
    command cleanly instead of letting an unhandled OSError bubble up as a raw
    traceback (CLAUDE.md rule 5).
    """
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        info(f"[FAIL] {label} 읽기 실패 ({path}): {exc}")
        return None


def _enumerate_skeleton_sections(skel_text: str) -> list[dict[str, str]]:
    """Return ordered section identifiers found in skeleton.md.

    Each entry is {"id": "§13", "title": "컴포넌트 트리"}. The §-prefixed id is the
    canonical reference used in RedesignEntry.affected_sections.
    """
    return [
        {"id": f"§{m.group(1)}", "title": m.group(2).strip()}
        for m in SKELETON_HEADING_RE.finditer(skel_text)
    ]


def _enumerate_tasks(tasks_text: str) -> list[dict[str, str]]:
    """Return ordered task summaries from tasks.md."""
    return [
        {"id": m.group(1), "agent": m.group(2).strip(), "status": m.group(5).strip()}
        for m in TASK_ROW_RE.finditer(tasks_text)
    ]


def cmd_prepare(args: argparse.Namespace) -> int:
    plan, plan_path, project = load_plan()
    assert_state(plan, _REDESIGN_ALLOWED_STATES, "/ha-redesign")

    if not args.decision:
        info("[FAIL] --decision <text> 필요 — 무엇이 바뀌는지 한 줄 요약")
        return 2
    if not args.rationale:
        info("[FAIL] --rationale <text> 필요 — 왜 바뀌는지 (review 출처 / 근거)")
        return 2

    skel_path = plan_path.parent / "skeleton.md"
    if not skel_path.exists():
        info(f"[FAIL] skeleton.md 없음: {skel_path}")
        return 1
    tasks_path = plan_path.parent / "tasks.md"

    skel_text = _read_text_or_fail(skel_path, "skeleton.md")
    if skel_text is None:
        return 1
    sections = _enumerate_skeleton_sections(skel_text)

    tasks: list[dict[str, str]] = []
    if tasks_path.exists():
        tasks_text = _read_text_or_fail(tasks_path, "tasks.md")
        if tasks_text is None:
            return 1
        tasks = _enumerate_tasks(tasks_text)

    # skeleton hash 비교 — 외부 수정 감지 (advisory only)
    hash_check = check_skeleton_hash(plan.skeleton_hash, skel_path)
    if not hash_check.skeleton_missing and not hash_check.is_legacy and not hash_check.is_match:
        info(
            "[WARN] skeleton.md 가 마지막 ha-design/ha-redesign 이후 외부에서 수정된 듯합니다 "
            "(hash mismatch). redesign_history 에 audit trail 누락 가능 — "
            "/ha-redesign 으로 변경 사항 추적 권장."
        )

    # Phase 2 records the "proposed" entry with empty affected_* — the Agent
    # (Phase 3) fills these by reading the skeleton and decision. Keeping the
    # record here means even a manual workflow leaves an audit trail.
    from src.orchestrator.plan_manager import PlanManager  # noqa: E402

    pm = PlanManager()
    pm.record_redesign(
        plan,
        decision=args.decision,
        rationale=args.rationale,
        affected_sections=(),
        affected_tasks=(),
        status="proposed",
    )
    save_plan(plan, plan_path)

    profiles = get_active_profiles(plan, project)

    output = {
        "project": str(project),
        "plan_path": str(plan_path),
        "skeleton_path": str(skel_path),
        "tasks_path": str(tasks_path) if tasks_path.exists() else None,
        "current_step": plan.pipeline.current_step,
        "decision": args.decision,
        "rationale": args.rationale,
        "skeleton_sections": sections,
        "tasks": tasks,
        "redesign_history_count": len(plan.redesign_history),
        "agent_prompts": {
            "architect": str(HARNESS_HOME / "backend" / "agents" / "architect" / "CLAUDE.md"),
            "designer": str(HARNESS_HOME / "backend" / "agents" / "designer" / "CLAUDE.md"),
        },
        "profiles": [
            {"id": p.id, "components": [c.id for c in p.components]} for p in profiles
        ],
        "skeleton_hash_check": {
            "is_match": hash_check.is_match,
            "is_legacy": hash_check.is_legacy,
            "skeleton_missing": hash_check.skeleton_missing,
        },
        "next_step": (
            "Phase 2: 사용자 또는 Agent 가 affected_sections / affected_tasks 식별 후 "
            "`/ha-redesign commit --status approved` (사용자 승인) → "
            "skeleton.md / tasks.md 갱신 → `--status applied`."
        ),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def cmd_commit(args: argparse.Namespace) -> int:
    plan, plan_path, _ = load_plan()
    assert_state(plan, _REDESIGN_ALLOWED_STATES, "/ha-redesign")

    if args.status not in ("approved", "applied", "rejected"):
        info(
            f"[FAIL] commit 의 --status: approved|applied|rejected, 현재 '{args.status}'.\n"
            "       (proposed 는 prepare 단계에서 자동 기록 — commit 으로는 사용 X)"
        )
        return 2

    if not args.decision:
        info("[FAIL] --decision <text> 필요 — prepare 와 동일한 라벨로 묶기 위함")
        return 2

    affected_sections = tuple(
        s.strip() for s in (args.affected_sections or "").split(",") if s.strip()
    )
    affected_tasks = tuple(
        t.strip() for t in (args.affected_tasks or "").split(",") if t.strip()
    )

    # approved/applied stages must reference real sections/tasks. rejected
    # carries no propagation duty so it is exempt — every other path would
    # silently corrupt the audit trail with phantom IDs.
    # Read skeleton/tasks at most once each; reuse below for consistency_check.
    skel_text: str | None = None
    tasks_text: str | None = None
    if args.status in ("approved", "applied"):
        skel_path = plan_path.parent / "skeleton.md"
        if not skel_path.exists():
            info(f"[FAIL] skeleton.md 없음: {skel_path}")
            return 1
        skel_text = _read_text_or_fail(skel_path, "skeleton.md")
        if skel_text is None:
            return 1
        section_ids = {f"§{m.group(1)}" for m in SKELETON_HEADING_RE.finditer(skel_text)}
        invalid_sections = [s for s in affected_sections if s not in section_ids]
        if invalid_sections:
            info(
                f"[FAIL] affected_sections {invalid_sections} 가 skeleton.md 에 없음.\n"
                f"       유효한 섹션 ID: {sorted(section_ids)}"
            )
            return 1

        tasks_path = plan_path.parent / "tasks.md"
        if tasks_path.exists():
            tasks_text = _read_text_or_fail(tasks_path, "tasks.md")
            if tasks_text is None:
                return 1
        if affected_tasks:
            if tasks_text is None:
                info(f"[FAIL] tasks.md 없음인데 affected_tasks 지정됨: {tasks_path}")
                return 1
            known_tasks = {m.group(1) for m in TASK_ROW_RE.finditer(tasks_text)}
            invalid_tasks = [t for t in affected_tasks if t not in known_tasks]
            if invalid_tasks:
                info(
                    f"[FAIL] affected_tasks {invalid_tasks} 가 tasks.md 에 없음.\n"
                    f"       유효한 ID 는 tasks.md 의 1열 — 정확한 형식으로 다시 지정."
                )
                return 1

    from src.orchestrator.plan_manager import PlanManager  # noqa: E402

    pm = PlanManager()
    pm.record_redesign(
        plan,
        decision=args.decision,
        rationale=args.rationale or "",
        affected_sections=affected_sections,
        affected_tasks=affected_tasks,
        status=args.status,
    )
    save_plan(plan, plan_path)

    # Cross-section consistency surfaces drift introduced by re-derivation.
    # Run only at the "applied" stage — that is the moment skeleton/tasks just
    # changed, so any drift came from this redesign and is most actionable.
    # Findings are advisory (info/warn) — never block the lifecycle commit.
    consistency_findings: list[dict[str, str]] = []
    if args.status == "applied" and skel_text is not None:
        from src.orchestrator.consistency_checker import (  # noqa: E402
            run_all_checks,
        )

        for f in run_all_checks(skeleton_text=skel_text, tasks_text=tasks_text):
            consistency_findings.append(
                {
                    "severity": f.severity,
                    "pattern": f.pattern,
                    "target": f.target,
                    "message": f.message,
                }
            )

    # skeleton hash 갱신 — applied 시 skeleton.md 가 변경되었으므로 새 hash 기록.
    # downstream skills (ha-plan/ha-build/ha-verify/ha-review) 가 이후 외부 수정을
    # 정확히 감지할 수 있도록 baseline 을 이 시점으로 갱신.
    if args.status == "applied":
        skel_path_for_hash = plan_path.parent / "skeleton.md"
        if skel_path_for_hash.exists():
            plan.skeleton_hash = compute_skeleton_hash(skel_path_for_hash)
            save_plan(plan, plan_path)

    # Safety guard: when applied, transition any affected done tasks to needs_rebuild
    # so that ha-verify / ha-build --skip-done cannot silently pass stale code.
    # Only "applied" triggers this — proposed/approved/rejected carry no code change.
    rebuild_required_tasks: list[str] = []
    if args.status == "applied" and affected_tasks:
        tasks_path = plan_path.parent / "tasks.md"
        if tasks_path.exists():
            from src.orchestrator.plan_manager import PlanManager  # noqa: E402

            try:
                rebuild_required_tasks = PlanManager().mark_for_rebuild(
                    tasks_path, list(affected_tasks)
                )
            except OSError as exc:
                info(f"[WARN] needs_rebuild 전이 실패 (tasks.md 쓰기 오류): {exc}")
                info("       수동으로 stale task status 를 확인하세요.")

    output = {
        "decision": args.decision,
        "status": args.status,
        "affected_sections": list(affected_sections),
        "affected_tasks": list(affected_tasks),
        "redesign_history_count": len(plan.redesign_history),
        "current_step": plan.pipeline.current_step,
        "consistency_findings": consistency_findings,
        "rebuild_required_tasks": rebuild_required_tasks,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="ha-redesign")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prepare")
    p.add_argument("--decision", required=True, help="One-line label of the change")
    p.add_argument("--rationale", required=True, help="Source/reason for the change")

    c = sub.add_parser("commit")
    c.add_argument("--decision", required=True)
    c.add_argument(
        "--status",
        required=True,
        choices=["approved", "applied", "rejected"],
        help="Lifecycle stage for this entry",
    )
    c.add_argument("--rationale", default="")
    c.add_argument(
        "--affected-sections",
        default="",
        help='Comma-separated, e.g. "§1,§13,§15"',
    )
    c.add_argument(
        "--affected-tasks",
        default="",
        help='Comma-separated, e.g. "T-200,T-201"',
    )

    args = parser.parse_args()
    if args.cmd == "prepare":
        return cmd_prepare(args)
    return cmd_commit(args)


if __name__ == "__main__":
    sys.exit(main())
