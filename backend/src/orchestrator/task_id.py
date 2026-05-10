"""Single source of truth for task ID + skeleton heading regexes.

Prior to v0.7.0 the same patterns lived in three files (ha-build/run.py,
ha-redesign/run.py, consistency_checker.py) with subtly different relaxations
(`T-\\d+` strict in one, `T-[\\w-]+` lenient in others), creating a silent
contract gap: a malformed ID could pass one stage and fail another.

Centralising here ensures every consumer agrees on:
- the canonical task ID format (T-NNN, no semantic suffixes)
- the tasks.md row layout
- the skeleton.md section heading layout
- the strict validation message a user can act on
"""
from __future__ import annotations

import re

# Canonical task ID — semantic suffixes (T-013a, T-013-PTT) are rejected.
# Decomposition must use new numeric IDs (T-013, T-014, T-015).
TASK_ID_RE = re.compile(r"^T-\d+$")

# tasks.md row: | T-001 | agent | depends | description | status |
# The ID fragment intentionally matches TASK_ID_RE — keep them in lockstep.
TASK_ROW_RE = re.compile(
    r"^\|\s*(T-\d+)\s*\|\s*(\w+)\s*\|\s*([^|]*)\|\s*([^|]*)\|\s*([^|]+)\|\s*$",
    re.MULTILINE,
)

# skeleton.md section heading: "## 13. 컴포넌트 트리" → group 1 = "13", group 2 = title.
SKELETON_HEADING_RE = re.compile(r"^##\s+(\d+)\.\s+(.+?)\s*$", re.MULTILINE)


def validate_task_id(task_id: str) -> None:
    """Raise ValueError if ``task_id`` does not match T-NNN.

    The message is intentionally Korean so the CLI user can act on it directly —
    every ha-* skill surfaces this string verbatim through ``info()``.
    """
    if not TASK_ID_RE.match(task_id):
        raise ValueError(
            f"Task ID '{task_id}' 형식 오류: T-NNN (예: T-013, T-014) 이어야 합니다.\n"
            f"  · 의미적 suffix 금지 (T-013a, T-013-PTT, T-013h 등 X)\n"
            f"  · 분해가 필요하면 별도 번호로 늘리세요 (T-013, T-014, T-015)\n"
            f"  · ha-plan/commit + ha-build/prepare 가 같은 정규식을 공유합니다."
        )
