#!/usr/bin/env python3
"""HarnessAI v2 — `/ha-plan` 백엔드."""
from __future__ import annotations

import argparse
import json
import re
import sys
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


# Lenient pattern that extracts every "T-..." candidate from tasks.md rows so that
# malformed IDs surface as explicit validation errors instead of silently failing
# downstream. The strict check lives in validate_task_id.
_TASK_ID_CANDIDATE_RE = re.compile(r"\|\s*(T-[\w-]+)\s*\|", re.MULTILINE)


def cmd_prepare(args: argparse.Namespace) -> int:
    plan, plan_path, project = load_plan()
    assert_state(plan, ["designed"], "/ha-plan")

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
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def cmd_commit(args: argparse.Namespace) -> int:
    plan, plan_path, project = load_plan()
    assert_state(plan, ["designed"], "/ha-plan")

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

    # tasks.md 작성
    tasks_md = (
        f"# Tasks — {project.name}\n\n"
        f"생성: {plan.last_activity}\n\n"
        f"{args.tasks_content.strip()}\n"
    )
    tasks_path.write_text(tasks_md, encoding="utf-8")

    # skeleton 의 tasks 섹션 동기화
    skel_text = skel_path.read_text(encoding="utf-8")
    new_skel = re.sub(
        r"(## \d+\. 태스크 분해\n)(.*?)(?=^## \d+\.|\Z)",
        rf"\1\n{args.tasks_content.strip()}\n\n",
        skel_text, count=1, flags=re.DOTALL | re.MULTILINE,
    )
    if new_skel != skel_text:
        skel_path.write_text(new_skel, encoding="utf-8")

    # 상태 전이
    transition(plan, "planned", completed_step="ha-plan")
    save_plan(plan, plan_path)

    # 태스크 ID 카운트
    task_ids = re.findall(r"\|\s*(T-\d+)\s*\|", args.tasks_content)

    output = {
        "tasks_path": str(tasks_path),
        "skeleton_synced": new_skel != skel_text,
        "task_count": len(task_ids),
        "transitioned_to": plan.pipeline.current_step,
        "next": "/ha-build <T-ID>",
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="ha-plan")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prepare")
    c = sub.add_parser("commit")
    c.add_argument("--tasks-content", required=True)
    args = parser.parse_args()
    if args.cmd == "prepare":
        return cmd_prepare(args)
    return cmd_commit(args)


if __name__ == "__main__":
    sys.exit(main())
