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
import re
import subprocess
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
    compute_section_hashes,
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
            "/ha-redesign 으로 변경 사항 추적 권장. "
            "→ 의도적 편집이면 /ha-resync 로 해시 재동기하세요."
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


# F3 — 섹션 hash diff 기반 결정론적 rebuild 파생용.
_SPEC_BLOCK_RE = re.compile(
    r"^###\s+(T-\d+)\b(.*?)(?=^###\s+T-\d+\b|\Z)", re.MULTILINE | re.DOTALL
)
_SKELETON_REF_LINE_RE = re.compile(r"\*\*skeleton 참조\*\*\s*:\s*(.+)")


def _tasks_referencing_sections(
    tasks_text: str, changed_section_ids: list[str]
) -> list[str]:
    """spec 블록의 'skeleton 참조' 가 변경 섹션을 가리키는 task ID (문서 순).

    매칭: ref == section_id 또는 ref 가 'section_id.' 로 시작
    (예: persistence.users ← persistence 변경). agent 의 affected_tasks
    recall 과 독립적인 결정론적 파생 (architecture review F3).
    """
    hits: list[str] = []
    for m in _SPEC_BLOCK_RE.finditer(tasks_text):
        task_id, body = m.group(1), m.group(2)
        ref_m = _SKELETON_REF_LINE_RE.search(body)
        if ref_m is None:
            continue
        refs = [r.strip().strip("`") for r in ref_m.group(1).split(",") if r.strip()]
        for ref in refs:
            if any(
                ref == sid or ref.startswith(sid + ".")
                for sid in changed_section_ids
            ):
                hits.append(task_id)
                break
    return hits


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
    # 정확히 감지할 수 있도록 baseline 을 이 시점으로 갱신. 섹션별 hash 도 diff 해
    # 변경 섹션을 참조하는 task 를 결정론적으로 파생 (F3 — agent recall 비의존).
    # legacy plan (섹션 baseline 없음) 은 파생 skip — baseline 만 새로 기록.
    hash_derived_candidates: list[str] = []
    if args.status == "applied":
        skel_path_for_hash = plan_path.parent / "skeleton.md"
        if skel_path_for_hash.exists():
            old_section_hashes = dict(plan.section_hashes or {})
            new_section_hashes = compute_section_hashes(skel_path_for_hash)
            plan.skeleton_hash = compute_skeleton_hash(skel_path_for_hash)
            plan.section_hashes = new_section_hashes
            save_plan(plan, plan_path)

            if old_section_hashes:
                changed_ids = sorted(
                    sid
                    for sid in set(old_section_hashes) | set(new_section_hashes)
                    if old_section_hashes.get(sid) != new_section_hashes.get(sid)
                )
                tasks_path_for_derive = plan_path.parent / "tasks.md"
                if changed_ids and tasks_path_for_derive.exists():
                    already = set(affected_tasks)
                    hash_derived_candidates = [
                        tid
                        for tid in _tasks_referencing_sections(
                            tasks_path_for_derive.read_text(encoding="utf-8"),
                            changed_ids,
                        )
                        if tid not in already
                    ]
                    if hash_derived_candidates:
                        info(
                            "[INFO] 섹션 hash diff 파생 — affected_tasks 에 없지만 "
                            "변경 섹션을 참조하는 task: "
                            f"{', '.join(hash_derived_candidates)} (needs_rebuild 후보 합산)"
                        )

    # Safety guard: when applied, transition any affected done tasks to needs_rebuild
    # so that stale code cannot silently pass ha-verify — `ha-build --resume` never
    # re-selects a done task, so the status must drop for the task to be rebuilt.
    # Only "applied" triggers this — proposed/approved/rejected carry no code change.
    # affected_tasks (agent 판단) ∪ hash 파생 후보. mark_for_rebuild 는 done 상태만
    # 전이하므로 superset 전달이 안전하다.
    rebuild_required_tasks: list[str] = []
    rebuild_candidates = list(dict.fromkeys([*affected_tasks, *hash_derived_candidates]))
    if args.status == "applied" and rebuild_candidates:
        tasks_path = plan_path.parent / "tasks.md"
        if tasks_path.exists():
            from src.orchestrator.plan_manager import PlanManager  # noqa: E402

            try:
                rebuild_required_tasks = PlanManager().mark_for_rebuild(
                    tasks_path, rebuild_candidates
                )
            except OSError as exc:
                info(f"[WARN] needs_rebuild 전이 실패 (tasks.md 쓰기 오류): {exc}")
                info("       수동으로 stale task status 를 확인하세요.")

    # v0.10.0 -- worklog 자동 append (applied 시만, change 카테고리)
    if args.status == "applied":
        _log_msg = (
            f"/ha-redesign applied -- decision={args.decision[:60]}, "
            f"sections={len(affected_sections)}, tasks={len(affected_tasks)}"
        )
        try:
            subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parent.parent / "ha-log" / "run.py"),
                    "append",
                    "--category", "change",
                    "--message", _log_msg,
                    "--project", str(plan_path.parent.parent),
                ],
                capture_output=True,
                timeout=5,
                check=False,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as _worklog_err:
            info(f"[WARN] worklog append failed (commit 진행): {_worklog_err}")

    output = {
        "decision": args.decision,
        "status": args.status,
        "affected_sections": list(affected_sections),
        "affected_tasks": list(affected_tasks),
        "redesign_history_count": len(plan.redesign_history),
        "current_step": plan.pipeline.current_step,
        "consistency_findings": consistency_findings,
        "rebuild_required_tasks": rebuild_required_tasks,
        "hash_derived_rebuild_candidates": hash_derived_candidates,
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
