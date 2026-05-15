#!/usr/bin/env python3
"""PreToolUse hook — Edit/Write 가 skeleton.md 의 HUMAN-LOCKED 섹션 안인지 검사.

Claude Code hooks 양식 (v1):
  - stdin: JSON {"tool_name": "Edit"|"Write", "tool_input": {...}}
  - stdout: 무시 (사용자에게 안 보임)
  - stderr: 사용자 메시지
  - exit 0: 통과 / exit 2: 차단 (사용자에게 stderr 보임)

Escape hatch: env HARNESS_SKIP_LOCK_HOOK=1 → 무조건 통과 (개발/마이그레이션용).
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_LOCKED_RE = re.compile(
    r"<!--\s*HUMAN-LOCKED:([\w.]+)\s+—.*?-->\s*\n(.*?)<!--\s*/HUMAN-LOCKED:\1\s*-->",
    re.DOTALL,
)


def _is_skeleton_file(file_path: str) -> bool:
    """skeleton.md 또는 spec.md 파일인지 확인 (Windows / POSIX path 모두)."""
    norm = file_path.replace("\\", "/")
    return (
        norm.endswith("/docs/skeleton.md")
        or norm.endswith("/docs/spec.md")
        or norm == "skeleton.md"
        or norm == "spec.md"
    )


def main() -> int:
    if os.environ.get("HARNESS_SKIP_LOCK_HOOK") == "1":
        return 0

    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0  # malformed input — fail open (don't block other workflows)

    tool = payload.get("tool_name", "")
    if tool not in ("Edit", "Write"):
        return 0

    inp = payload.get("tool_input", {})
    file_path = inp.get("file_path", "")
    if not file_path or not _is_skeleton_file(file_path):
        return 0

    p = Path(file_path)
    if not p.exists():
        return 0  # 신규 파일 — LOCKED 섹션 자체가 없음

    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return 0  # read 실패 — fail open

    locked_blocks = [(m.group(1), m.group(2)) for m in _LOCKED_RE.finditer(text)]
    if not locked_blocks:
        return 0

    if tool == "Edit":
        old = inp.get("old_string", "")
        if not old:
            return 0
        for section_id, body in locked_blocks:
            if old in body:
                print(
                    f"[HITL BLOCK] Edit 차단 — section '{section_id}' 가 HUMAN-LOCKED.\n"
                    f"  · 변경 시 /ha-redesign 거치기 (mutation propagation 기록).\n"
                    f"  · 개발/마이그레이션 우회: HARNESS_SKIP_LOCK_HOOK=1",
                    file=sys.stderr,
                )
                return 2

    if tool == "Write":
        content = inp.get("content", "")
        # Re-parse content with the same regex to detect both:
        # (a) marker removal, and (b) body mutation under preserved markers.
        new_locked = {m.group(1): m.group(2) for m in _LOCKED_RE.finditer(content)}
        for section_id, body in locked_blocks:
            if section_id not in new_locked:
                print(
                    f"[HITL BLOCK] Write 차단 — section '{section_id}' LOCKED 마커가 사라짐.\n"
                    f"  · 전체 덮어쓰기로 LOCKED 섹션 손실 방지.\n"
                    f"  · 변경 시 /ha-redesign 거치기.\n"
                    f"  · 개발/마이그레이션 우회: HARNESS_SKIP_LOCK_HOOK=1",
                    file=sys.stderr,
                )
                return 2
            # Body mutation check — marker preserved but content swapped is the
            # most dangerous case (silent HITL bypass). Strip trailing whitespace
            # only — internal whitespace must stay identical (otherwise Edit-style
            # rewrites slip through).
            if new_locked[section_id].strip() != body.strip():
                print(
                    f"[HITL BLOCK] Write 차단 — section '{section_id}' LOCKED body 변조 감지.\n"
                    f"  · 마커는 유지됐지만 내용이 바뀜 (silent HITL bypass).\n"
                    f"  · 변경 시 /ha-redesign 거치기.\n"
                    f"  · 개발/마이그레이션 우회: HARNESS_SKIP_LOCK_HOOK=1",
                    file=sys.stderr,
                )
                return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
