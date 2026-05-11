"""lessons — LESSON reference extraction and validation.

Parses shared-lessons.md to find defined LESSON ids, then cross-references
them against a skeleton body to surface unknown (dangling) references.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_LESSON_DEF_RE = re.compile(r"^##\s+(LESSON-[A-Z0-9][A-Z0-9\-]*?)(?::|$|\s)", re.MULTILINE)
_LESSON_REF_RE = re.compile(r"\bLESSON-[A-Z0-9][A-Z0-9\-]*\b")


@dataclass(frozen=True)
class UnknownLessonReference:
    """skeleton.md body references a LESSON id not defined in shared-lessons.md."""

    lesson_id: str
    occurrences: int  # how many times the id appears in the body (>= 1)


def extract_known_lessons(lessons_md_path: Path) -> frozenset[str]:
    """Parse shared-lessons.md and return the set of defined LESSON ids.

    Recognizes headings of the form ``## LESSON-NNN:`` or ``## LESSON-NNN <title>``.
    Returns an empty frozenset if the file is missing — caller decides how to handle.
    """
    if not lessons_md_path.exists():
        return frozenset()
    try:
        text = lessons_md_path.read_text(encoding="utf-8")
    except OSError:
        return frozenset()
    return frozenset(_LESSON_DEF_RE.findall(text))


def find_unknown_lesson_references(
    skeleton_md_body: str,
    known_lessons: frozenset[str],
) -> list[UnknownLessonReference]:
    """Extract LESSON-NNN-form references from body and return those not in known_lessons.

    Recognized form: ``\\bLESSON-[A-Z0-9-]+\\b`` (uppercase letters, digits,
    hyphens; case-sensitive to match author convention).
    Sorted by lesson_id for deterministic output.
    """
    counts: dict[str, int] = {}
    for match in _LESSON_REF_RE.finditer(skeleton_md_body):
        lid = match.group(0)
        if lid not in known_lessons:
            counts[lid] = counts.get(lid, 0) + 1
    return sorted(
        [UnknownLessonReference(lesson_id=lid, occurrences=n) for lid, n in counts.items()],
        key=lambda r: r.lesson_id,
    )
