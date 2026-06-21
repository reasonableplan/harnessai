#!/usr/bin/env python3
"""HarnessAI v2 — `/ha-plan` 백엔드."""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "_ha_shared"))
from utils import (  # noqa: E402
    HARNESS_HOME,
    assert_state,
    get_active_profiles,
    info,
    load_plan,
    resolve_guideline_paths,
    save_plan,
    transition,
    validate_task_id,
)

# Import backend modules for agent mismatch validation (Group 3 Step 2).
# These are available because _ha_shared/utils.py already inserts backend/ into sys.path.
from src.orchestrator.agent_matching import match_task_to_agent  # noqa: E402
from src.orchestrator.config import load_agents_config  # noqa: E402
from src.orchestrator.profile_loader import (  # noqa: E402
    ProfileLoader,
    ProfileNotFoundError,
    find_consistency_violations,
)
from src.orchestrator.skeleton_hash import (  # noqa: E402
    check_skeleton_hash,
    compute_section_hashes,
    compute_skeleton_hash,
)
from src.orchestrator.tasks_schema import SchemaViolation, validate_tasks_md  # noqa: E402

# Lenient pattern that extracts every "T-..." candidate from tasks.md rows so that
# malformed IDs surface as explicit validation errors instead of silently failing
# downstream. The strict check lives in validate_task_id.
_TASK_ID_CANDIDATE_RE = re.compile(r"\|\s*(T-[\w-]+)\s*\|", re.MULTILINE)

# Parses full task rows to extract (task_id, agent_id) pairs.
# Format: | T-001 | agent_id | depends | description | status |
# Mirrors TASK_ROW_RE from src.orchestrator.task_id — kept local to avoid
# importing that module here (utils already handles the import boundary).
_TASK_AGENT_ROW_RE = re.compile(
    r"^\|\s*(T-\d+)\s*\|\s*(\w+)\s*\|[^|]*\|[^|]*\|[^|]+\|\s*$",
    re.MULTILINE,
)


@dataclass
class _AgentMismatch:
    task_id: str
    agent_id: str
    reason: str


def _validate_agent_mappings(
    tasks_content: str,
    agents_yaml_path: Path,
    active_profile_ids: frozenset[str],
    active_has_keys: frozenset[str],
) -> list[_AgentMismatch]:
    """Validate that each task's declared agent matches the active context.

    Returns a list of mismatches (empty = all OK).

    Semantics (1st-pass guard — agent ↔ active context only):
    - Capability-agnostic agents (architect, reviewer, qa, …) always pass.
    - Specific agents: requires_profile_ids ⊆ active_profile_ids
      AND at least one requires_capabilities atom ∈ active_has_keys.
    - Unknown agent_id (not in agents.yaml) → mismatch with reason "unknown agent".
    """
    try:
        config = load_agents_config(agents_yaml_path)
    except (FileNotFoundError, ValueError) as exc:
        # If agents.yaml cannot be loaded we cannot validate — surface as a
        # single pseudo-mismatch so the caller can report it clearly.
        return [_AgentMismatch(task_id="*", agent_id="*", reason=f"agents.yaml 로드 실패: {exc}")]

    all_agents = config.all_agents()
    mismatches: list[_AgentMismatch] = []

    for m in _TASK_AGENT_ROW_RE.finditer(tasks_content):
        task_id = m.group(1)
        agent_id = m.group(2)

        if agent_id not in all_agents:
            mismatches.append(
                _AgentMismatch(
                    task_id=task_id,
                    agent_id=agent_id,
                    reason=f"unknown agent '{agent_id}' (agents.yaml 에 없음)",
                )
            )
            continue

        result = match_task_to_agent(
            task_required_capabilities=frozenset(),
            task_required_profile_ids=frozenset(),
            agent_config=all_agents[agent_id],
            active_has_keys=active_has_keys,
            active_profile_ids=active_profile_ids,
            agent_id=agent_id,
        )
        if not result.is_match:
            mismatches.append(
                _AgentMismatch(task_id=task_id, agent_id=agent_id, reason=result.reason)
            )

    return mismatches


def cmd_prepare(args: argparse.Namespace) -> int:
    plan, plan_path, project = load_plan()
    # --replan: ha-redesign 은 cross-cutting 스킬이라 current_step 을 유지(planned)한다.
    # 그래서 redesign 으로 skeleton 이 바뀐 뒤 tasks 를 재생성할 공식 경로가 없었다
    # (issue #2). --replan 은 planned 상태에서의 재실행을 허용한다.
    allowed = ["designed", "planned"] if args.replan else ["designed"]
    assert_state(plan, allowed, "/ha-plan")

    skel_path = plan_path.parent / "skeleton.md"
    if not skel_path.exists():
        info(f"[FAIL] skeleton.md 없음: {skel_path}")
        return 1
    skel_text = skel_path.read_text(encoding="utf-8")

    # 채워짐 검사 — tasks/notes 제외 placeholder 카운트
    text_for_check = re.sub(
        r"## \d+\. (태스크 분해|구현 노트).*?(?=^## \d+\.|\Z)",
        "", skel_text, flags=re.DOTALL | re.MULTILINE,
    )
    placeholders = re.findall(r"<[A-Z_][A-Z0-9_\s/.,'\"\-—:]*?>|_미작성_", text_for_check)

    profiles = get_active_profiles(plan, project)

    # activation_trace: sorted for deterministic output.
    # Legacy plans without this field load as empty dict (backward-compat).
    activation_trace: dict[str, str] = dict(sorted(plan.activation_trace.items()))
    if not activation_trace:
        info(
            "[INFO] 본 plan 은 activation_trace 미포함 (구버전). "
            "cross-check 불가능 — ha-init 재실행 권장"
        )

    # Cross-section consistency check — only when trace is present.
    # trace 가 비어있으면 (legacy plan) 검증 skip.
    if activation_trace:
        consistency_violations_raw = find_consistency_violations(activation_trace, profiles)
    else:
        consistency_violations_raw = []

    consistency_violations = [
        {
            "section_id": v.section_id,
            "trigger_expression": v.trigger_expression,
            "missing_atom": v.missing_atom,
            "expected_providers": list(v.expected_providers),
        }
        for v in consistency_violations_raw
    ]

    if consistency_violations:
        info(
            f"[WARN] plan consistency 위반 {len(consistency_violations)}개 감지 "
            "(task 분해 전 확인 권장):"
        )
        for cv in consistency_violations:
            info(
                f"  - 섹션 '{cv['section_id']}': "
                f"'{cv['missing_atom']}' 미충족 "
                f"(제공 가능 프로파일: {cv['expected_providers']})"
            )

    # skeleton hash 비교 — 외부 수정 감지 (advisory only)
    hash_check = check_skeleton_hash(plan.skeleton_hash, skel_path)
    if not hash_check.skeleton_missing and not hash_check.is_legacy and not hash_check.is_match:
        info(
            "[WARN] skeleton.md 가 마지막 ha-design/ha-redesign 이후 외부에서 수정된 듯합니다 "
            "(hash mismatch). redesign_history 에 audit trail 누락 가능 — "
            "/ha-redesign 으로 변경 사항 추적 권장."
        )

    output = {
        "project": str(project),
        "plan_path": str(plan_path),
        "skeleton_path": str(skel_path),
        "tasks_path": str(plan_path.parent / "tasks.md"),
        "current_step": plan.pipeline.current_step,
        "skeleton_placeholders_remaining": len(placeholders),
        "profiles": [
            {
                "id": p.id,
                "components": [
                    {"id": c.id, "skeleton_section": c.skeleton_section, "required": c.required}
                    for c in p.components
                ],
                "guideline_paths": [str(g) for g in resolve_guideline_paths(p.id)],
            }
            for p in profiles
        ],
        "agent_prompt": str(HARNESS_HOME / "backend" / "agents" / "orchestrator" / "CLAUDE.md"),
        "consistency_violations": consistency_violations,
        "skeleton_hash_check": {
            "is_match": hash_check.is_match,
            "is_legacy": hash_check.is_legacy,
            "skeleton_missing": hash_check.skeleton_missing,
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def cmd_commit(args: argparse.Namespace) -> int:
    plan, plan_path, project = load_plan()
    # --replan: planned 상태에서의 재실행 허용 (issue #2 — redesign 후 재-plan 경로).
    allowed = ["designed", "planned"] if args.replan else ["designed"]
    assert_state(plan, allowed, "/ha-plan")

    if not args.tasks_content:
        info("[FAIL] --tasks-content 비어 있음")
        return 2

    # Enforce the task-ID contract shared with ha-build: extract every candidate
    # from the rows and run validate_task_id for a strict check.
    candidates = _TASK_ID_CANDIDATE_RE.findall(args.tasks_content)
    invalid: list[str] = []
    for cid in candidates:
        try:
            validate_task_id(cid)
        except ValueError:
            invalid.append(cid)
    if invalid:
        info("[FAIL] tasks.md 에 형식 위반 ID 가 있어 commit 거부:")
        for cid in invalid:
            info(f"  · '{cid}'")
        try:
            validate_task_id(invalid[0])  # raise → except 로 메시지 출력
        except ValueError as e:
            info(str(e))
        return 1

    tasks_path = plan_path.parent / "tasks.md"
    skel_path = plan_path.parent / "skeleton.md"

    # ── Agent mismatch validation (Group 3 Step 2) ──────────────────────────
    agents_yaml_path = HARNESS_HOME / "backend" / "agents.yaml"
    try:
        profiles = get_active_profiles(plan, plan_path.parent.parent)
        loader = ProfileLoader(project_dir=plan_path.parent.parent)
        active_has_keys = loader.compute_has_keys(profiles, plan.scale_axes)
    except (OSError, ValueError, KeyError, ProfileNotFoundError) as exc:
        # Expected load failures only — anything else must propagate. A blind
        # except here made the agent-mismatch gate pass vacuously on corrupt
        # agents.yaml (review H4: fail-open).
        info(f"[WARN] agent mismatch 검증 건너뜀 — 프로파일 로드 실패: {exc}")
        active_has_keys = frozenset()
        profiles = []

    active_profile_ids = frozenset(ref.id for ref in plan.profiles)

    mismatches = _validate_agent_mappings(
        args.tasks_content,
        agents_yaml_path,
        active_profile_ids,
        active_has_keys,
    )

    if mismatches and not args.allow_agent_mismatch:
        info(
            f"[FAIL] tasks.md 의 {len(mismatches)}개 task 가 "
            "활성 컨텍스트와 정합하지 않은 agent 에 배정됨:"
        )
        for mm in mismatches:
            info(f"  - {mm.task_id} (agent={mm.agent_id}): {mm.reason}")
        info(
            "해결: tasks.md 의 agent 컬럼을 수정하거나, "
            "plan.profiles 에 적합한 프로파일을 추가하세요.\n"
            "의도적 mismatch 라면 --allow-agent-mismatch flag 를 사용하세요."
        )
        return 1

    if mismatches and args.allow_agent_mismatch:
        info(
            f"[WARN] tasks.md 의 {len(mismatches)}개 task 가 "
            "활성 컨텍스트와 정합하지 않은 agent 에 배정됨 (--allow-agent-mismatch 로 진행):"
        )
        for mm in mismatches:
            info(f"  - {mm.task_id} (agent={mm.agent_id}): {mm.reason}")

    # ── tasks.md schema 검증 (Group 4 Step 1) ───────────────────────────────
    # _TASK_ID_CANDIDATE_RE (위) 는 추출용(느슨) — T-NNN 후보를 뽑아 validate_task_id 로
    # 확인한다. validate_tasks_md() 는 검증용(엄격) — 전체 표 구조/컬럼/상태/의존성.
    # 두 검증은 상호 보완: 위쪽이 fractional ID 를 이미 차단했다면 아래는 도달 못 함.
    # 그러나 위쪽은 _TASK_ID_CANDIDATE_RE 패턴으로만 추출하므로 표 구조 위반은 못 잡음.
    schema_violations: list[SchemaViolation] = validate_tasks_md(args.tasks_content)

    if schema_violations and not args.allow_format_drift:
        info(
            f"[FAIL] tasks.md schema 위반 {len(schema_violations)}개 — commit 거부:"
        )
        for sv in schema_violations:
            info(f"  line {sv.line_number} [{sv.kind}]: {sv.detail}")
        info(
            "해결: tasks.md 표 형식을 표준 schema 에 맞게 수정하세요.\n"
            "의도적 형식 변형이라면 --allow-format-drift flag 를 사용하세요."
        )
        # stdout JSON 에 violations 포함 (도구가 파싱할 수 있도록)
        print(json.dumps(
            {
                "schema_violations": [
                    {"line": sv.line_number, "kind": sv.kind, "detail": sv.detail}
                    for sv in schema_violations
                ],
            },
            ensure_ascii=False,
            indent=2,
        ))
        return 1

    if schema_violations and args.allow_format_drift:
        info(
            f"[WARN] tasks.md schema 위반 {len(schema_violations)}개 "
            "(--allow-format-drift 로 진행):"
        )
        for sv in schema_violations:
            info(f"  line {sv.line_number} [{sv.kind}]: {sv.detail}")

    # tasks.md 작성
    tasks_md = (
        f"# Tasks — {project.name}\n\n"
        f"생성: {plan.last_activity}\n\n"
        f"{args.tasks_content.strip()}\n"
    )

    # skeleton 의 tasks 섹션 동기화 — read first so a missing/corrupt skeleton
    # aborts before tasks.md is written (review H1: no partial state).
    try:
        skel_text = skel_path.read_text(encoding="utf-8")
    except OSError as e:
        info(f"[FAIL] skeleton.md 읽기 실패 — commit 중단: {e}")
        return 1
    # Lambda replacement: tasks_content is LLM-generated and may contain
    # literal "\1"/"\g<...>" sequences that re.sub would treat as group refs.
    new_skel = re.sub(
        r"(## \d+\. 태스크 분해\n)(.*?)(?=^## \d+\.|\Z)",
        lambda m: f"{m.group(1)}\n{args.tasks_content.strip()}\n\n",
        skel_text, count=1, flags=re.DOTALL | re.MULTILINE,
    )
    try:
        tasks_path.write_text(tasks_md, encoding="utf-8")
        if new_skel != skel_text:
            skel_path.write_text(new_skel, encoding="utf-8")
    except OSError as e:
        info(f"[FAIL] tasks.md/skeleton.md 쓰기 실패 — 상태 전이 중단: {e}")
        return 1

    # skeleton hash baseline 갱신 — §태스크 분해 sync 로 skeleton.md 가 바뀌었으면
    # baseline 을 이 시점으로 refresh. 안 하면 다음 ha-redesign/ha-build 의
    # check_skeleton_hash 가 stale baseline(= ha-design 직후 값)과 비교해 거짓
    # "외부 수정" 경고를 띄운다 (issue #1). 태스크 분해는 ha-plan 의 산출물이지
    # 사용자 수정 대상이 아니므로 baseline 에 흡수한다. ha-redesign apply 와 동일 패턴.
    if new_skel != skel_text:
        plan.skeleton_hash = compute_skeleton_hash(skel_path)
        plan.section_hashes = compute_section_hashes(skel_path)

    # 상태 전이
    transition(plan, "planned", completed_step="ha-plan")
    save_plan(plan, plan_path)

    # 태스크 ID 카운트 — 완전한 태스크 행(첫 컬럼 T-ID)만 센다. 순진한
    # `\|\s*(T-\d+)\s*\|` 는 의존성 컬럼의 단일 T-ID 셀(`| T-003 |`)도 집계해
    # 행 수를 부풀린다 (이슈 #10). 검증에 쓰는 _TASK_AGENT_ROW_RE 로 통일.
    task_ids = [m.group(1) for m in _TASK_AGENT_ROW_RE.finditer(args.tasks_content)]

    output = {
        "tasks_path": str(tasks_path),
        "skeleton_synced": new_skel != skel_text,
        "task_count": len(task_ids),
        "transitioned_to": plan.pipeline.current_step,
        "next": "/ha-build <T-ID>",
        "agent_mismatches": [
            {"task_id": mm.task_id, "agent_id": mm.agent_id, "reason": mm.reason}
            for mm in mismatches
        ],
        "schema_violations": [
            {"line": sv.line_number, "kind": sv.kind, "detail": sv.detail}
            for sv in schema_violations
        ],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="ha-plan")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument(
        "--replan",
        action="store_true",
        default=False,
        help="planned 상태에서도 재실행 허용 (ha-redesign 후 tasks 재생성)",
    )
    c = sub.add_parser("commit")
    c.add_argument("--tasks-content", required=True)
    c.add_argument(
        "--replan",
        action="store_true",
        default=False,
        help="planned 상태에서도 재실행 허용 (ha-redesign 후 tasks 재생성)",
    )
    c.add_argument(
        "--allow-agent-mismatch",
        action="store_true",
        default=False,
        help="agent ↔ 활성 컨텍스트 mismatch 를 경고로 처리하고 commit 진행",
    )
    c.add_argument(
        "--allow-format-drift",
        action="store_true",
        default=False,
        help="tasks.md schema 위반을 경고로 처리하고 commit 진행",
    )
    args = parser.parse_args()
    if args.cmd == "prepare":
        return cmd_prepare(args)
    return cmd_commit(args)


if __name__ == "__main__":
    sys.exit(main())
