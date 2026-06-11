"""extract-lesson 서브커맨드 테스트 (v0.10.0 — ChatDev 영감).

5개 테스트:
  1. Pending 섹션 없을 때 — 신규 섹션 생성 + LESSON 블록 박힘
  2. Pending 섹션 있을 때 — 그 안에 append (다음 ## 헤딩 직전)
  3. 기존 LESSON-001 ~ LESSON-014 있는 파일 → 새 LESSON-015 부여
  4. 기존 LESSON 제목과 동일 (lowercase) → SKIP, exit 0, skipped: true
  5. --evidence 박으면 LESSON 블록에 **근거**: 추가
"""

from __future__ import annotations

import importlib.util
import json
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HA_REVIEW_RUN = REPO_ROOT / "skills" / "ha-review" / "run.py"


@pytest.fixture(scope="module")
def ha_review() -> ModuleType:
    """ha-review/run.py (repo mirror) 를 모듈로 로드."""
    loader = SourceFileLoader("ha_review_run_extract", str(HA_REVIEW_RUN))
    spec = importlib.util.spec_from_loader("ha_review_run_extract", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_review_run_extract"] = mod
    loader.exec_module(mod)
    return mod


def _make_lessons_file(tmp_path: Path, content: str) -> Path:
    """tmp_path 에 shared-lessons.md 생성."""
    p = tmp_path / "shared-lessons.md"
    p.write_text(content, encoding="utf-8")
    return p


def _make_args(
    *,
    title: str,
    problem: str,
    rule: str,
    evidence: str = "",
    lessons_path: str,
) -> object:
    """argparse.Namespace 와 동일한 duck-type 객체."""

    class _Args:
        pass

    a = _Args()
    a.title = title  # type: ignore[attr-defined]
    a.problem = problem  # type: ignore[attr-defined]
    a.rule = rule  # type: ignore[attr-defined]
    a.evidence = evidence  # type: ignore[attr-defined]
    a.lessons_path = lessons_path  # type: ignore[attr-defined]
    return a


# ── 테스트 1: Pending 섹션 없을 때 신규 생성 ──────────────────────────


def test_extract_lesson_appends_to_pending_section(
    ha_review: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """Pending 섹션 없을 때 — 신규 섹션 생성 + LESSON 블록 박힘."""
    initial = (
        "# Shared Lessons\n\n"
        "## LESSON-001: 기존 레슨\n\n"
        "**문제**: 기존 문제.\n\n"
        "**규칙**: 기존 규칙.\n\n"
        "---\n"
    )
    lessons_path = _make_lessons_file(tmp_path, initial)

    captured_output: list[str] = []

    def fake_print(data: str, **kwargs: object) -> None:
        captured_output.append(data)

    import builtins

    original_print = builtins.print
    builtins.print = fake_print  # type: ignore[assignment]
    try:
        args = _make_args(
            title="신규 테스트 레슨",
            problem="문제 설명",
            rule="규칙 설명",
            lessons_path=str(lessons_path),
        )
        result = ha_review.cmd_extract_lesson(args)
    finally:
        builtins.print = original_print

    assert result == 0, "exit 0 기대"

    text = lessons_path.read_text(encoding="utf-8")
    assert "## Pending Lessons (자동 추출 — 사용자 promotion 대기)" in text
    assert "## LESSON-002: 신규 테스트 레슨" in text
    assert "auto_extracted: true" in text
    assert "**문제**: 문제 설명" in text
    assert "**규칙**: 규칙 설명" in text

    assert len(captured_output) == 1
    output = json.loads(captured_output[0])
    assert output["lesson_id"] == "LESSON-002"
    assert output["promotion_pending"] is True
    assert output["section"] == "Pending Lessons"


# ── 테스트 2: Pending 섹션 있을 때 그 안에 append ────────────────────


def test_extract_lesson_appends_to_existing_pending(
    ha_review: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """Pending 섹션 있을 때 — 그 안에 append (다음 ## 헤딩 직전)."""
    initial = (
        "# Shared Lessons\n\n"
        "## LESSON-001: 기존 레슨\n\n"
        "**문제**: 기존 문제.\n\n"
        "**규칙**: 기존 규칙.\n\n"
        "---\n\n"
        "## Pending Lessons (자동 추출 — 사용자 promotion 대기)\n\n"
        "> 자동 추출된 LESSON.\n\n"
        "## LESSON-002: 기존 Pending 레슨\n"
        "<!-- auto_extracted: true / promotion_pending: true / extracted_at: 2026-01-01 -->\n\n"
        "**문제**: 기존 pending 문제.\n\n"
        "**규칙**: 기존 pending 규칙.\n\n"
        "---\n"
    )
    lessons_path = _make_lessons_file(tmp_path, initial)

    captured_output: list[str] = []

    def fake_print(data: str, **kwargs: object) -> None:
        captured_output.append(data)

    import builtins

    original_print = builtins.print
    builtins.print = fake_print  # type: ignore[assignment]
    try:
        args = _make_args(
            title="두 번째 Pending 레슨",
            problem="두 번째 문제",
            rule="두 번째 규칙",
            lessons_path=str(lessons_path),
        )
        result = ha_review.cmd_extract_lesson(args)
    finally:
        builtins.print = original_print

    assert result == 0

    text = lessons_path.read_text(encoding="utf-8")
    # Pending 섹션 내에 두 LESSON 모두 있어야 함
    assert "## LESSON-002: 기존 Pending 레슨" in text
    assert "## LESSON-003: 두 번째 Pending 레슨" in text

    # Pending 헤더 이후에 두 LESSON 이 모두 존재
    pending_idx = text.index("## Pending Lessons")
    assert text.index("## LESSON-003:") > pending_idx

    output = json.loads(captured_output[0])
    assert output["lesson_id"] == "LESSON-003"


# ── 테스트 3: ID 자동 증가 (max+1) ──────────────────────────────────


def test_extract_lesson_id_auto_increments(ha_review: ModuleType, tmp_path: Path) -> None:
    """기존 LESSON-001 ~ LESSON-014 있는 파일 → 새 LESSON-015 부여."""
    lines = ["# Shared Lessons\n\n"]
    for i in range(1, 15):
        lines.append(
            f"## LESSON-{i:03d}: 레슨 {i}\n\n**문제**: 문제.\n\n**규칙**: 규칙.\n\n---\n\n"
        )
    initial = "".join(lines)
    lessons_path = _make_lessons_file(tmp_path, initial)

    captured_output: list[str] = []

    def fake_print(data: str, **kwargs: object) -> None:
        captured_output.append(data)

    import builtins

    original_print = builtins.print
    builtins.print = fake_print  # type: ignore[assignment]
    try:
        args = _make_args(
            title="열다섯 번째 레슨",
            problem="문제",
            rule="규칙",
            lessons_path=str(lessons_path),
        )
        result = ha_review.cmd_extract_lesson(args)
    finally:
        builtins.print = original_print

    assert result == 0
    output = json.loads(captured_output[0])
    assert output["lesson_id"] == "LESSON-015", f"기대 LESSON-015, got {output['lesson_id']}"

    text = lessons_path.read_text(encoding="utf-8")
    assert "## LESSON-015: 열다섯 번째 레슨" in text


# ── 테스트 4: 중복 제목 → SKIP ───────────────────────────────────────


def test_extract_lesson_skips_duplicate_title(ha_review: ModuleType, tmp_path: Path) -> None:
    """기존 LESSON 제목과 동일 (lowercase) 추출 → SKIP, exit 0, skipped: true."""
    initial = (
        "# Shared Lessons\n\n"
        "## LESSON-001: Query params에 camelCase 사용 금지\n\n"
        "**문제**: 기존 문제.\n\n"
        "**규칙**: 기존 규칙.\n\n"
        "---\n"
    )
    lessons_path = _make_lessons_file(tmp_path, initial)

    captured_output: list[str] = []

    def fake_print(data: str, **kwargs: object) -> None:
        captured_output.append(data)

    import builtins

    original_print = builtins.print
    builtins.print = fake_print  # type: ignore[assignment]
    try:
        # 대소문자만 다른 동일 제목
        args = _make_args(
            title="query params에 camelcase 사용 금지",
            problem="중복",
            rule="중복",
            lessons_path=str(lessons_path),
        )
        result = ha_review.cmd_extract_lesson(args)
    finally:
        builtins.print = original_print

    assert result == 0, "중복이어도 exit 0"
    # info() 도 fake_print 를 통과하므로 JSON 파싱 가능한 항목만 필터
    json_outputs = [s for s in captured_output if s.strip().startswith("{")]
    assert len(json_outputs) == 1
    output = json.loads(json_outputs[0])
    assert output["skipped"] is True
    assert output["lesson_id"] is None
    assert output["reason"] == "duplicate_title"

    # 파일이 변경되지 않았는지 확인
    text = lessons_path.read_text(encoding="utf-8")
    assert "LESSON-002" not in text


# ── 테스트 5: --evidence 포함 시 근거 필드 추가 ───────────────────────


def test_extract_lesson_includes_evidence(ha_review: ModuleType, tmp_path: Path) -> None:
    """--evidence 박으면 LESSON 블록에 **근거**: 추가."""
    initial = (
        "# Shared Lessons\n\n"
        "## LESSON-001: 기존 레슨\n\n"
        "**문제**: 기존 문제.\n\n"
        "**규칙**: 기존 규칙.\n\n"
        "---\n"
    )
    lessons_path = _make_lessons_file(tmp_path, initial)

    captured_output: list[str] = []

    def fake_print(data: str, **kwargs: object) -> None:
        captured_output.append(data)

    import builtins

    original_print = builtins.print
    builtins.print = fake_print  # type: ignore[assignment]
    try:
        args = _make_args(
            title="근거 포함 레슨",
            problem="문제 설명",
            rule="규칙 설명",
            evidence="src/auth.py:42 에서 3회 발견",
            lessons_path=str(lessons_path),
        )
        result = ha_review.cmd_extract_lesson(args)
    finally:
        builtins.print = original_print

    assert result == 0

    text = lessons_path.read_text(encoding="utf-8")
    assert "**근거**: src/auth.py:42 에서 3회 발견" in text

    output = json.loads(captured_output[0])
    assert output["lesson_id"] == "LESSON-002"
