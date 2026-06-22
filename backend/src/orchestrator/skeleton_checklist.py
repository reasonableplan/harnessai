"""Skeleton quality gate — Spec Kit /checklist absorption (v1, advisory-only).

Checks skeleton.md for clarity and edge-case coverage using deterministic
regex rules. All findings are severity="warn" in v1 (advisory, never blocking).

Entry point: check_skeleton_quality(skeleton_text) -> list[ChecklistFinding]

Design doc: backend/docs/spec-kit-absorption-design.md §A1
Sibling:    backend/src/orchestrator/consistency_checker.py
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Data model (mirrors ConsistencyFinding in consistency_checker.py)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChecklistFinding:
    """Single skeleton quality check result.

    severity: always "warn" in v1 (advisory).
    category: "clarity" | "edge_case"
    section_id: section heading title string (NOT a number — numbers are
                assigned dynamically per project's active fragment set).
    message: Korean-friendly description (ASCII punctuation only, LESSON-033).
    """

    severity: str
    category: str
    section_id: str
    message: str


# ---------------------------------------------------------------------------
# Section splitting — raw ## headings (not restricted to known SECTION_TITLES)
# ---------------------------------------------------------------------------

# Matches `## N. Title` or `## Title` (bare heading without number prefix).
_H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)

# Sections whose content is tool-generated output, not spec prose.
# Clarity checks are skipped for these to prevent false positives on
# task/implementation notes written by agents rather than the designer.
_SKIP_CLARITY_TITLE_RE = re.compile(
    r"(태스크\s*분해|tasks?|구현\s*노트|notes?|implementation\s*note)",
    re.IGNORECASE,
)

# Code fence delimiter — content between ``` pairs is excluded from checks.
_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)

# Inline backtick — single-line inline code excluded from vague-word scan.
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


def _split_sections_raw(skeleton_text: str) -> list[tuple[str, str]]:
    """Return [(heading_title, body_text)] for every ## section.

    Uses raw ## heading matching so that sections with titles not in
    SECTION_TITLES are also included. Heading numbers are stripped —
    section_id in findings is the bare title string.
    """
    matches = list(_H2_RE.finditer(skeleton_text))
    result: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        raw_title = m.group(1).strip()
        # Strip leading "N. " or "N-M. " number prefix so section_id is
        # the plain title regardless of dynamic numbering.
        title = re.sub(r"^\d+(?:-\d+)?\.\s+", "", raw_title)
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(skeleton_text)
        body = skeleton_text[body_start:body_end]
        result.append((title, body))
    return result


def _strip_code_blocks(text: str) -> str:
    """Remove fenced code blocks and inline backtick spans from text.

    Prevents vague-word regex from firing on code content (LESSON-033
    FP-minimisation: code tokens like `simple=True` are not spec prose).
    """
    text = _CODE_FENCE_RE.sub("", text)
    text = _INLINE_CODE_RE.sub("", text)
    return text


# ---------------------------------------------------------------------------
# Check 1 — clarity: vague/unquantified adjectives/adverbs
# ---------------------------------------------------------------------------

# Vague terms that should be accompanied by a numeric target on the same line.
# Pattern: vague word present AND no adjacent number+unit on the same sentence/line.
_VAGUE_WORD_RE = re.compile(
    r"\b("
    r"빠른|빠르게|빠름|빠르다|빠른지|빠른\s*응답"
    r"|적절한|적절히|적절하게|적절하다"
    r"|충분한|충분히|충분하다"
    r"|간단한|간단히|간단하게|간단하다"
    r"|효율적|효율적인|효율적으로"
    r"|많은|많이|많다"
    r"|fast|simple|scalable|efficient|lightweight|large|small"
    r")\b",
    re.IGNORECASE,
)

# A "quantified" line contains at least one number followed by a unit-like token.
# Units: ms, s, sec, min, hr, %, MB, GB, KB, 건, 개, 명, 초, rpm, rps, req, px, dp
_QUANTIFIED_RE = re.compile(
    r"\d+\s*(?:ms|sec(?:onds?)?|minutes?|hours?|min|hr|%|MB|GB|KB|건|개|명|초|rpm|rps|req|px|dp|p\d{2})",
    re.IGNORECASE,
)


def _check_clarity(title: str, body: str) -> list[ChecklistFinding]:
    """Return findings for vague unquantified expressions in a section body."""
    findings: list[ChecklistFinding] = []
    clean = _strip_code_blocks(body)
    for line in clean.splitlines():
        m = _VAGUE_WORD_RE.search(line)
        if m is None:
            continue
        if _QUANTIFIED_RE.search(line):
            # Same line has a number+unit — considered quantified, skip.
            continue
        vague_word = m.group(1)
        findings.append(
            ChecklistFinding(
                severity="warn",
                category="clarity",
                section_id=title,
                message=(f"'{vague_word}' 미정량 - 목표치(예: ms, 건수) 명시 권장"),
            )
        )
        # One finding per line maximum — avoid duplicate findings for a line
        # that has two vague words.
        break
    # Deduplicate: one finding per (section, vague_word) pair is sufficient.
    # Return at most one finding per section to keep noise low.
    return findings[:1]


# ---------------------------------------------------------------------------
# Check 2 — edge_case: I/O boundary sections missing failure-path keywords
# ---------------------------------------------------------------------------

# Section title keywords that indicate an I/O boundary section.
_IO_BOUNDARY_RE = re.compile(
    r"(인터페이스|interface|api|http|cli|ipc|sdk"
    r"|연동|integration"
    r"|저장|영속|persistence|storage|repository"
    r"|네트워크|network"
    r"|외부|external"
    r"|auth|인증"
    r")",
    re.IGNORECASE,
)

# Failure/error keywords that indicate the section addresses failure paths.
_FAILURE_KEYWORD_RE = re.compile(
    r"(실패|에러|오류|예외|exception"
    r"|timeout|타임아웃"
    r"|fallback|폴백"
    r"|에러\s*코드|error\s*code"
    r"|exit\s*code|종료\s*코드"
    r"|retry|재시도"
    r"|circuit\s*breaker"
    r")",
    re.IGNORECASE,
)


def _check_edge_case(title: str, body: str) -> list[ChecklistFinding]:
    """Return a finding if an I/O boundary section has zero failure-path keywords."""
    if not _IO_BOUNDARY_RE.search(title):
        return []
    if _FAILURE_KEYWORD_RE.search(body):
        return []
    return [
        ChecklistFinding(
            severity="warn",
            category="edge_case",
            section_id=title,
            message=(f"'{title}' I/O 경계인데 실패/에러 경로 미기술"),
        )
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_skeleton_quality(skeleton_text: str) -> list[ChecklistFinding]:
    """Run all v1 quality checks on skeleton.md text.

    Args:
        skeleton_text: Full text content of skeleton.md (string).

    Returns:
        List of ChecklistFinding. Empty list if skeleton_text is empty or
        has no ## sections. Never raises.
    """
    if not skeleton_text.strip():
        return []

    sections = _split_sections_raw(skeleton_text)
    findings: list[ChecklistFinding] = []

    for title, body in sections:
        # --- Check 1: clarity (vague unquantified terms) ---
        # Skip tool-generated sections (task decomposition, implementation notes).
        if not _SKIP_CLARITY_TITLE_RE.search(title):
            findings.extend(_check_clarity(title, body))

        # --- Check 2: edge_case (I/O boundary without failure paths) ---
        findings.extend(_check_edge_case(title, body))

    return findings
