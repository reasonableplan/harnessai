#!/usr/bin/env python3
"""HarnessAI v0.10.0 -- worklog.md append."""
from __future__ import annotations

import argparse
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "_ha_shared"))
from utils import HARNESS_HOME, info  # noqa: E402

_CATEGORIES = {
    "discussion": "### 논의 / 합의",
    "change": "### 변경",
    "next": "### 다음",
}

_TITLE = "# 작업 일지"
_HEADER = (
    f"{_TITLE}\n\n"
    "> Append-only. 최신이 위. 사람-AI 공동 작성.\n"
    '> 자동: /ha-design, /ha-build, /ha-redesign commit 시 박힘.\n'
    '> 수동: /ha-log "..." 명령.\n'
)


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _resolve_worklog_path(project_arg: str | None) -> Path:
    """worklog.md 경로 해석. 기본은 docs/worklog.md 이되, 프로젝트 루트에 이미
    worklog.md 가 있으면 그쪽을 우선한다 (issue #3 — split-brain 방지).

    도구는 docs/ 에 append 하는데 사람/메모리는 루트 worklog.md 를 진실의 원천으로
    보던 불일치를 없앤다. 기존 루트 히스토리를 가진 프로젝트는 계속 루트에 쌓이고,
    새 프로젝트는 docs/ 를 쓴다 — 프로젝트당 한 파일로 수렴.
    """
    base = Path(project_arg).resolve() if project_arg else HARNESS_HOME / "backend"
    root_worklog = base / "worklog.md"
    if root_worklog.exists():
        return root_worklog
    return base / "docs" / "worklog.md"


def append_entry(worklog_path: Path, category: str, message: str) -> None:
    """Append a bullet to today's section. Idempotent on header creation."""
    if category not in _CATEGORIES:
        raise ValueError(f"category must be one of {sorted(_CATEGORIES)}, got '{category}'")

    today = _today()
    section_marker = f"## {today}"
    sub_header = _CATEGORIES[category]
    bullet = f"- {message.strip()}"

    if not worklog_path.exists():
        worklog_path.parent.mkdir(parents=True, exist_ok=True)
        worklog_path.write_text(
            _HEADER + "\n" + section_marker + "\n\n" + sub_header + "\n" + bullet + "\n",
            encoding="utf-8",
        )
        return

    text = worklog_path.read_text(encoding="utf-8")

    # 오늘 날짜 섹션이 있나? (## YYYY-MM-DD 정확 매칭)
    today_re = re.compile(rf"^{re.escape(section_marker)}\b", re.MULTILINE)
    today_match = today_re.search(text)

    if today_match is None:
        # 오늘 섹션 신규 - Title 직후 (HEADER 끝) 에 삽입.
        next_section_re = re.compile(r"^## \d{4}-\d{2}-\d{2}\b", re.MULTILINE)
        next_match = next_section_re.search(text)
        insert_at = next_match.start() if next_match else len(text)
        new_block = section_marker + "\n\n" + sub_header + "\n" + bullet + "\n\n"
        new_text = text[:insert_at] + new_block + text[insert_at:]
        worklog_path.write_text(new_text, encoding="utf-8")
        return

    # 오늘 섹션 안에서 sub_header 찾기.
    # 오늘 섹션 끝 = 다음 ## 헤딩 또는 EOF.
    section_start = today_match.end()
    next_section_re = re.compile(r"\n## \d{4}-\d{2}-\d{2}\b", re.MULTILINE)
    next_match = next_section_re.search(text, pos=section_start)
    section_end = next_match.start() if next_match else len(text)
    section_body = text[section_start:section_end]

    sub_header_re = re.compile(rf"^{re.escape(sub_header)}\s*$", re.MULTILINE)
    sub_match = sub_header_re.search(section_body)

    if sub_match is None:
        # sub_header 신규 - 섹션 끝에 추가.
        new_section_body = section_body.rstrip() + "\n\n" + sub_header + "\n" + bullet + "\n"
    else:
        # sub_header 다음에 bullet 박음.
        sub_start = sub_match.end()
        next_sub_re = re.compile(r"\n### ", re.MULTILINE)
        next_sub_match = next_sub_re.search(section_body, pos=sub_start)
        sub_end = next_sub_match.start() if next_sub_match else len(section_body)
        sub_body = section_body[sub_start:sub_end].rstrip()
        new_sub_body = sub_body + "\n" + bullet
        new_section_body = (
            section_body[:sub_start] + "\n" + new_sub_body + "\n" + section_body[sub_end:]
        )

    new_text = text[:section_start] + new_section_body + text[section_end:]
    worklog_path.write_text(new_text, encoding="utf-8")


def cmd_append(args: argparse.Namespace) -> int:
    worklog_path = _resolve_worklog_path(args.project or None)
    try:
        append_entry(worklog_path, args.category, args.message)
    except ValueError as e:
        info(f"[FAIL] {e}")
        return 2
    except OSError as e:
        info(f"[FAIL] worklog.md 쓰기 실패: {e}")
        return 1
    info(f"[OK] {worklog_path.name} : {args.category} append")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="ha-log")
    sub = parser.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("append", help="worklog.md 에 사용자 메시지 append")
    a.add_argument("--message", required=True, help="박을 텍스트 (한 줄 또는 짧은 문단)")
    a.add_argument(
        "--category",
        default="discussion",
        choices=list(_CATEGORIES.keys()),
        help="discussion (논의/합의), change (변경), next (다음 단계). default: discussion",
    )
    a.add_argument(
        "--project",
        default="",
        help="프로젝트 루트 (기본: HARNESS_AI_HOME/backend)",
    )
    args = parser.parse_args()
    if args.cmd == "append":
        return cmd_append(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
