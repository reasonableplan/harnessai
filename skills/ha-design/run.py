#!/usr/bin/env python3
"""HarnessAI v2 — `/ha-design` 백엔드 스크립트.

서브커맨드:
- prepare : 사전 조건 검증 + 컨텍스트 (skeleton/agent prompt 경로) JSON 출력
- commit  : skeleton 채움 후 placeholder 검사 + 상태 전이
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# 공유 유틸 import
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
)

# backend src import — HARNESS_HOME 은 utils.py 가 sys.path 에 backend 추가 보장
from src.orchestrator.profile_loader import (  # noqa: E402
    extract_known_lessons,
    find_consistency_violations,
    find_unknown_lesson_references,
)
from src.orchestrator.skeleton_hash import (  # noqa: E402
    compute_section_hashes,
    compute_skeleton_hash,
)


# placeholder 패턴: <PROJECT_NAME>, <예: ...>, _미작성_, <DOMAIN>_NNN 등
_PLACEHOLDER_RE = re.compile(r"<[A-Z_][A-Z0-9_\s/.,'\"\-—:]*?>|_미작성_|_미정_")

# TS/제네릭 타입 파라미터(<T>, <K, V>)는 placeholder 가 아님 — 코드 블록의 제네릭
# 문법(IpcResult<T> 등)을 가짜 placeholder 로 집계하던 FP #6 차단. 단일 대문자
# 또는 콤마 구분 대문자 조합만 제외 — <DOMAIN>/<DB_URL> 같은 실제 placeholder 는 유지.
_GENERIC_TYPE_RE = re.compile(r"^<[A-Z](?:\s*,\s*[A-Z])*>$")


def _find_placeholders(text: str) -> list[str]:
    """미해결 placeholder 토큰 목록. TS 제네릭(<T>, <K, V>)은 제외 (FP #6)."""
    return [m for m in _PLACEHOLDER_RE.findall(text) if not _GENERIC_TYPE_RE.match(m)]

# LOCKED 섹션 fill 상태 감지용 (v0.10.0+ 복구 지원)
_LOCKED_SECTION_IDS = ("requirements", "user_journey", "view.screens")
_AI_WRITABLE_RE = re.compile(
    r"<!--\s*AI-WRITABLE:[^>]*-->(.*?)<!--\s*/AI-WRITABLE\s*-->",
    re.DOTALL,
)
# AI-WRITABLE 존 안에서 남은 placeholder 카운트용. `<...>` 형태 광범위 매칭 —
# `<AI 채움>` / `<AI>` / `<Mobbin URL>` 등 템플릿마다 다른 컨벤션 모두 잡음.
_ANY_PLACEHOLDER_RE = re.compile(r"<[^<>\n]{1,80}>")


def _locked_section_status(skeleton_text: str, section_id: str) -> str:
    """LOCKED 섹션의 fill 상태 반환.

    반환값:
    - "not_included": HUMAN-LOCKED 블록 자체가 skeleton 에 없음 (해당 섹션 미활성)
    - "empty": AI-WRITABLE 후보 표가 아직 placeholder 가득 → Step A 부터 진행 필요
    - "filled": 후보 표가 채워짐 (사용자 확정 여부는 별도 판단) → Claude 가 본문 확인 후 결정
    """
    # 여는/닫는 마커 모두 id 뒤 ` — 설명` 접미사를 허용 — 템플릿 fragment
    # (templates/skeleton/*.md) 의 실제 마커는 `HUMAN-LOCKED:id — 설명 -->` 형태다.
    # `\b[^>]*` 로 id 경계 이후 `>` 직전까지 흡수 (prefix-id 오매칭은 \b 가 차단).
    block_re = re.compile(
        rf"<!--\s*HUMAN-LOCKED:{re.escape(section_id)}\b[^>]*-->(.*?)<!--\s*/HUMAN-LOCKED:{re.escape(section_id)}\b[^>]*-->",
        re.DOTALL,
    )
    m = block_re.search(skeleton_text)
    if not m:
        return "not_included"
    ai_zone = "".join(z.group(1) for z in _AI_WRITABLE_RE.finditer(m.group(1)))
    return "empty" if len(_ANY_PLACEHOLDER_RE.findall(ai_zone)) >= 3 else "filled"


def cmd_prepare(args: argparse.Namespace) -> int:
    plan, plan_path, project = load_plan()
    assert_state(plan, ["init"], "/ha-design")

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

    # v0.10.0+ 세션 중단 복구 — 각 LOCKED 섹션의 fill 상태 감지.
    # 빈 섹션만 인터뷰 재개하도록 SKILL.md 가 이 필드 보고 분기.
    skeleton_path = plan_path.parent / "skeleton.md"
    if skeleton_path.exists():
        skeleton_text = skeleton_path.read_text(encoding="utf-8")
        locked_section_status = {
            sid: _locked_section_status(skeleton_text, sid)
            for sid in _LOCKED_SECTION_IDS
        }
    else:
        locked_section_status = {sid: "not_included" for sid in _LOCKED_SECTION_IDS}

    output = {
        "project": str(project),
        "plan_path": str(plan_path),
        "skeleton_path": str(skeleton_path),
        "current_step": plan.pipeline.current_step,
        "included_sections": list(plan.skeleton_sections.included),
        # v0.10.0 HITL — 어느 included 섹션이 LOCKED 인지 SKILL.md 에 알림.
        "locked_section_ids": [
            sid for sid in plan.skeleton_sections.included
            if sid in {"requirements", "user_journey", "view.screens"}
        ],
        "locked_section_status": locked_section_status,
        "activation_trace": activation_trace,
        "profiles": [
            {
                "id": p.id,
                "path": (HARNESS_HOME / "backend" / "agents" / p.id / "CLAUDE.md")
                if (HARNESS_HOME / "backend" / "agents" / p.id / "CLAUDE.md").exists()
                else None,
                "body_path": str(_resolve_profile_body(p.id)),
                "components": [
                    {"id": c.id, "skeleton_section": c.skeleton_section}
                    for c in p.components
                ],
                "guideline_paths": [str(g) for g in resolve_guideline_paths(p.id)],
            }
            for p in profiles
        ],
        "agent_prompts": {
            "architect": str(HARNESS_HOME / "backend" / "agents" / "architect" / "CLAUDE.md"),
            "designer": str(HARNESS_HOME / "backend" / "agents" / "designer" / "CLAUDE.md"),
        },
        "lessons_path": str(HARNESS_HOME / "backend" / "docs" / "shared-lessons.md"),
        "user_description": plan.user_description_original,
        "consistency_violations": consistency_violations,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def cmd_commit(args: argparse.Namespace) -> int:
    plan, plan_path, project = load_plan()
    assert_state(plan, ["init"], "/ha-design")

    skel = Path(args.skeleton_path) if args.skeleton_path else plan_path.parent / "skeleton.md"
    if not skel.exists():
        info(f"[FAIL] skeleton.md 없음: {skel}")
        return 1

    text = skel.read_text(encoding="utf-8")

    # tasks/notes 섹션은 placeholder 검사에서 제외 (이후 스킬이 채움)
    text_for_check = re.sub(
        r"## \d+\. (태스크 분해|구현 노트).*?(?=^## \d+\.|\Z)",
        "",
        text,
        flags=re.DOTALL | re.MULTILINE,
    )
    placeholders = _find_placeholders(text_for_check)

    info(f"[check] 미해결 placeholder: {len(placeholders)} 개")
    if placeholders[:5]:
        for p in placeholders[:5]:
            info(f"  - {p[:60]}")
        if len(placeholders) > 5:
            info(f"  ... +{len(placeholders) - 5} 개 더")

    # 설계-시점 cross-section 검증 (design backlog A) — advisory, commit 은 진행.
    # 섹션 간 참조가 어긋난 채 freeze 되는 것을 표면화 — §4 충돌 검토(LLM)의 기계 보강.
    from src.orchestrator.consistency_checker import run_all_checks  # noqa: PLC0415
    design_findings = [
        {
            "severity": f.severity,
            "pattern": f.pattern,
            "target": f.target,
            "message": f.message,
        }
        for f in run_all_checks(skeleton_text=text)
    ]
    if design_findings:
        info(f"[WARN] 설계 정합 advisory {len(design_findings)}건 — 검토 권장:")
        for df in design_findings[:8]:
            info(f"  - [{df['severity']}] {df['pattern']}: {df['target']}")

    # 스켈레톤 품질 게이트 (Spec Kit /checklist 흡수 A1) — advisory. 명료성(미정량
    # 표현) + 엣지케이스(I/O 경계 실패경로 누락) 를 결정론으로 표면화. 차단 안 함.
    from src.orchestrator.skeleton_checklist import check_skeleton_quality  # noqa: PLC0415
    checklist_findings = [
        {"severity": cf.severity, "category": cf.category, "section_id": cf.section_id, "message": cf.message}
        for cf in check_skeleton_quality(text)
    ]
    if checklist_findings:
        info(f"[WARN] 스켈레톤 품질 advisory {len(checklist_findings)}건 (검토 권장):")
        for cf in checklist_findings[:8]:
            info(f"  - [{cf['category']}] {cf['section_id']}: {cf['message']}")

    # LESSON reference 검증
    lessons_path = HARNESS_HOME / "backend" / "docs" / "shared-lessons.md"
    unknown_lesson_refs: list[dict] = []

    if not lessons_path.exists():
        info(
            "[WARN] shared-lessons.md 없음 — LESSON 인용 검증 skip. "
            f"(예상 경로: {lessons_path})"
        )
    else:
        known_lessons = extract_known_lessons(lessons_path)
        unknown = find_unknown_lesson_references(text, known_lessons)
        unknown_lesson_refs = [
            {"lesson_id": r.lesson_id, "occurrences": r.occurrences} for r in unknown
        ]
        if unknown:
            lines = [
                f"  - {r.lesson_id} ({r.occurrences}회 인용) — shared-lessons.md 에 정의 없음"
                for r in unknown
            ]
            if args.allow_unknown_lessons:
                info(
                    "[WARN] 미정의 LESSON 인용 발견 (--allow-unknown-lessons 로 계속 진행):\n"
                    + "\n".join(lines)
                )
            else:
                info(
                    "[FAIL] 미정의 LESSON 인용 발견 — shared-lessons.md 에 정의 없음:\n"
                    + "\n".join(lines)
                    + "\n해결 방법: 인용 제거 또는 shared-lessons.md 에 LESSON 추가."
                    "\n의도적이면 --allow-unknown-lessons flag 사용."
                )
                output = {
                    "skeleton_path": str(skel),
                    "plan_path": str(plan_path),
                    "placeholders_remaining": len(placeholders),
                    "unknown_lesson_references": unknown_lesson_refs,
                    "transitioned_to": None,
                    "next": None,
                }
                print(json.dumps(output, ensure_ascii=False, indent=2))
                return 1

    # v0.10.0 HITL gate — freeze plan when LOCKED sections were filled via interview.
    locked = list(args.locked_sections or [])
    ai_drafted = list(args.ai_drafted_sections or [])

    # 방어선: ai-drafted 박혔는데 명시 옵트인 없으면 거부.
    if ai_drafted and not args.ai_draft:
        info(
            "[FAIL] --ai-drafted-sections 박았는데 --ai-draft 옵트인 누락. "
            "AI 추측 채우기는 명시 동의 필요."
        )
        output = {
            "skeleton_path": str(skel),
            "plan_path": str(plan_path),
            "placeholders_remaining": len(placeholders),
            "unknown_lesson_references": unknown_lesson_refs,
            "transitioned_to": None,
            "next": None,
            "frozen_status": plan.frozen_status,
            "locked_sections": list(plan.locked_sections),
            "ai_drafted_sections": list(plan.ai_drafted_sections),
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 1

    # skeleton hash 저장 — downstream skills 가 외부 수정을 감지할 수 있도록
    plan.skeleton_hash = compute_skeleton_hash(skel)
    # 섹션별 hash snapshot — ha-redesign 이 변경 섹션을 diff 해 stale done-task 를
    # 결정론적으로 파생할 수 있게 baseline 기록 (architecture review F3).
    plan.section_hashes = compute_section_hashes(skel)

    # locked_sections 박혔으면 plan.freeze() 호출.
    if locked:
        from src.orchestrator.plan_manager import PlanManager  # noqa: PLC0415
        PlanManager().freeze(
            plan,
            locked_sections=locked,
            ai_drafted_sections=ai_drafted or None,
        )
        info(
            f"[freeze] frozen_status=frozen, locked={len(locked)}, "
            f"ai_drafted={len(ai_drafted)}"
        )

    # 상태 전이
    transition(plan, "designed", completed_step="ha-design")
    save_plan(plan, plan_path)

    # v0.10.0 -- worklog 자동 append (change 카테고리)
    _log_msg = (
        f"/ha-design commit -- frozen_status={plan.frozen_status}, "
        f"locked={len(list(plan.locked_sections))}, "
        f"ai_drafted={len(list(plan.ai_drafted_sections))}"
    )
    try:
        import subprocess  # noqa: PLC0415
        subprocess.run(
            [
                sys.executable,
                str(Path.home() / ".claude" / "skills" / "ha-log" / "run.py"),
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
        "skeleton_path": str(skel),
        "plan_path": str(plan_path),
        "placeholders_remaining": len(placeholders),
        "unknown_lesson_references": unknown_lesson_refs,
        "design_findings": design_findings,
        "checklist_findings": checklist_findings,
        "transitioned_to": plan.pipeline.current_step,
        "next": "/ha-plan",
        "frozen_status": plan.frozen_status,
        "locked_sections": list(plan.locked_sections),
        "ai_drafted_sections": list(plan.ai_drafted_sections),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def _resolve_profile_body(profile_id: str) -> Path:
    """프로파일 .md 파일 경로 (글로벌)."""
    return Path.home() / ".claude" / "harness" / "profiles" / f"{profile_id}.md"


def main() -> int:
    parser = argparse.ArgumentParser(prog="ha-design")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("prepare", help="사전 조건 검증 + 컨텍스트 JSON")

    c = sub.add_parser("commit", help="placeholder 체크 + 상태 전이")
    c.add_argument("--skeleton-path", default="", help="명시 경로 (기본: plan 옆 skeleton.md)")
    c.add_argument(
        "--allow-unknown-lessons",
        action="store_true",
        default=False,
        help="미정의 LESSON 인용 발견 시 차단하지 않고 경고만 출력 후 진행",
    )
    c.add_argument(
        "--locked-sections",
        nargs="*",
        default=[],
        help="HITL gate 통과한 섹션 ID 목록. plan.freeze() 호출. (v0.10.0)",
    )
    c.add_argument(
        "--ai-drafted-sections",
        nargs="*",
        default=[],
        help="--ai-draft 옵트인으로 AI 가 추측 채운 섹션 ID. 사용자 promotion 필요. (v0.10.0)",
    )
    c.add_argument(
        "--ai-draft",
        action="store_true",
        default=False,
        help="--ai-drafted-sections 가 비어있지 않으면 필수. AI 추측 채우기 명시 동의. (v0.10.0)",
    )

    args = parser.parse_args()
    if args.cmd == "prepare":
        return cmd_prepare(args)
    if args.cmd == "commit":
        return cmd_commit(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
