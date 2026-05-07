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


# placeholder 패턴: <PROJECT_NAME>, <예: ...>, _미작성_, <DOMAIN>_NNN 등
_PLACEHOLDER_RE = re.compile(r"<[A-Z_][A-Z0-9_\s/.,'\"\-—:]*?>|_미작성_|_미정_")


def cmd_prepare(args: argparse.Namespace) -> int:
    plan, plan_path, project = load_plan()
    assert_state(plan, ["init"], "/ha-design")

    profiles = get_active_profiles(plan, project)

    output = {
        "project": str(project),
        "plan_path": str(plan_path),
        "skeleton_path": str(plan_path.parent / "skeleton.md"),
        "current_step": plan.pipeline.current_step,
        "included_sections": list(plan.skeleton_sections.included),
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
    placeholders = _PLACEHOLDER_RE.findall(text_for_check)

    info(f"[check] 미해결 placeholder: {len(placeholders)} 개")
    if placeholders[:5]:
        for p in placeholders[:5]:
            info(f"  - {p[:60]}")
        if len(placeholders) > 5:
            info(f"  ... +{len(placeholders) - 5} 개 더")

    # 상태 전이
    transition(plan, "designed", completed_step="ha-design")
    save_plan(plan, plan_path)

    output = {
        "skeleton_path": str(skel),
        "plan_path": str(plan_path),
        "placeholders_remaining": len(placeholders),
        "transitioned_to": plan.pipeline.current_step,
        "next": "/ha-plan",
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

    args = parser.parse_args()
    if args.cmd == "prepare":
        return cmd_prepare(args)
    if args.cmd == "commit":
        return cmd_commit(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
