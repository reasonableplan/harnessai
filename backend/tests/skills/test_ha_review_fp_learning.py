"""FP-candidate learning: record --allow-block must feed the lesson loop.

2026-07-08 adoption (CodeRabbit-style user-correction learning): when the user
explicitly bypasses BLOCK findings with --allow-block, the bypassed findings
are the strongest false-positive signal we have. record now auto-appends ONE
[FP 후보] entry to the Pending Lessons section (human promotion decides:
global promote / move to project conventions / delete). Lesson extraction is
fail-soft — a scan failure must never block the explicit override path.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from contextlib import ExitStack
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HA_REVIEW_RUN = REPO_ROOT / "skills" / "ha-review" / "run.py"

LESSONS_STUB = "# Shared Lessons\n\n## LESSON-001: 기존 교훈\n\n**문제**: x\n\n**규칙**: y\n\n---\n"

BLOCK_FINDING = {
    "hook": "secret-filter",
    "severity": "BLOCK",
    "message": "하드코딩 시크릿",
    "snippet": "API_KEY = 'x'",
}


@pytest.fixture(scope="module")
def ha_review() -> ModuleType:
    loader = SourceFileLoader("ha_review_fp_learning", str(HA_REVIEW_RUN))
    spec = importlib.util.spec_from_loader("ha_review_fp_learning", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_review_fp_learning"] = mod
    loader.exec_module(mod)
    return mod


def _run_record(
    ha_review: ModuleType, tmp_path: Path, extra_patches: dict[str, dict]
) -> tuple[int, dict]:
    """approve + --allow-block record 를 공통 패치로 실행, (exit, output JSON) 반환."""
    mock_plan = MagicMock()
    mock_plan.pipeline.current_step = "verified"
    mock_plan.verify_history = []

    captured: list[str] = []

    def fake_print(data: str, **kwargs) -> None:  # type: ignore[misc]
        captured.append(data)

    args = MagicMock()
    args.verdict = "approve"
    args.violations = ""
    args.summary = "override approved"
    args.allow_block = True
    args.allow_empty = True

    with ExitStack() as stack:
        stack.enter_context(
            patch.object(
                ha_review,
                "load_plan",
                return_value=(mock_plan, tmp_path / "harness-plan.md", tmp_path),
            )
        )
        stack.enter_context(patch.object(ha_review, "assert_state"))
        stack.enter_context(
            patch.object(ha_review, "_extract_diff", return_value=("some diff", "test-scope"))
        )
        stack.enter_context(patch.object(ha_review, "record_verify"))
        stack.enter_context(patch.object(ha_review, "transition"))
        stack.enter_context(patch.object(ha_review, "save_plan"))
        for name, kw in extra_patches.items():
            stack.enter_context(patch.object(ha_review, name, **kw))
        stack.enter_context(patch("builtins.print", side_effect=fake_print))
        result = ha_review.cmd_record(args)

    return result, json.loads(captured[-1])


def test_allow_block_appends_fp_candidate_lesson(ha_review: ModuleType, tmp_path: Path) -> None:
    """allow-block 우회 시 우회된 BLOCK 이 [FP 후보] Pending lesson 으로 기록."""
    append_mock = MagicMock(return_value=(0, {"lesson_id": "LESSON-042"}))
    result, output = _run_record(
        ha_review,
        tmp_path,
        {
            "get_active_profiles": {"return_value": []},
            "_collect_findings": {
                "return_value": {
                    "ai_slop": [],
                    "security": [BLOCK_FINDING],
                    "block_count": 1,
                    "warn_count": 0,
                }
            },
            "_append_pending_lesson": {"new": append_mock},
        },
    )
    assert result == 0
    assert output["fp_lesson"] == "LESSON-042"
    append_mock.assert_called_once()
    kwargs = append_mock.call_args.kwargs
    assert "[FP 후보]" in kwargs["title"]
    assert "secret-filter" in kwargs["title"]
    assert "하드코딩 시크릿" in kwargs["problem"]
    assert kwargs["origin"] == tmp_path.name


def test_allow_block_without_block_findings_skips_lesson(
    ha_review: ModuleType, tmp_path: Path
) -> None:
    """우회했지만 재스캔 BLOCK 0건 → lesson 기록 없음, fp_lesson=None."""
    append_mock = MagicMock(return_value=(0, {"lesson_id": "LESSON-042"}))
    result, output = _run_record(
        ha_review,
        tmp_path,
        {
            "get_active_profiles": {"return_value": []},
            "_collect_findings": {
                "return_value": {
                    "ai_slop": [],
                    "security": [],
                    "block_count": 0,
                    "warn_count": 0,
                }
            },
            "_append_pending_lesson": {"new": append_mock},
        },
    )
    assert result == 0
    assert output["fp_lesson"] is None
    append_mock.assert_not_called()


def test_allow_block_scan_failure_does_not_block_record(
    ha_review: ModuleType, tmp_path: Path
) -> None:
    """FP 스캔 실패는 명시적 우회를 막지 않는다 (fail-soft) — record 는 정상 종료."""
    result, output = _run_record(
        ha_review,
        tmp_path,
        {"get_active_profiles": {"side_effect": RuntimeError("scan boom")}},
    )
    assert result == 0
    assert output["verdict"] == "approve"
    assert output["fp_lesson"] is None


def test_append_pending_lesson_writes_origin_tag(ha_review: ModuleType, tmp_path: Path) -> None:
    """origin 지정 시 auto_extracted 마커에 origin 태그가 박힌다."""
    lessons = tmp_path / "shared-lessons.md"
    lessons.write_text(LESSONS_STUB, encoding="utf-8")

    code, output = ha_review._append_pending_lesson(
        lessons_path=lessons,
        title="[FP 후보] workout-app: secret-filter BLOCK 우회",
        problem="테스트 픽스처 키가 시크릿으로 오탐",
        rule="반복 시 훅 패턴 조정 검토",
        evidence="record --allow-block",
        origin="workout-app",
    )
    assert code == 0
    assert output["lesson_id"] == "LESSON-002"
    text = lessons.read_text(encoding="utf-8")
    assert "origin: workout-app" in text
    assert "auto_extracted: true" in text


def test_extract_lesson_cli_accepts_origin(ha_review: ModuleType, tmp_path: Path) -> None:
    """extract-lesson 서브커맨드가 --origin 을 마커에 반영."""
    lessons = tmp_path / "shared-lessons.md"
    lessons.write_text(LESSONS_STUB, encoding="utf-8")

    args = MagicMock()
    args.title = "새 패턴"
    args.problem = "문제"
    args.rule = "규칙"
    args.evidence = ""
    args.lessons_path = str(lessons)
    args.origin = "proj-x"

    with patch("builtins.print"):
        result = ha_review.cmd_extract_lesson(args)

    assert result == 0
    assert "origin: proj-x" in lessons.read_text(encoding="utf-8")


def test_extract_lesson_cli_ignores_non_string_origin(
    ha_review: ModuleType, tmp_path: Path
) -> None:
    """origin 미지정(MagicMock 자동 속성 포함) 시 마커에 origin 이 없다."""
    lessons = tmp_path / "shared-lessons.md"
    lessons.write_text(LESSONS_STUB, encoding="utf-8")

    args = MagicMock()
    args.title = "새 패턴2"
    args.problem = "문제"
    args.rule = "규칙"
    args.evidence = ""
    args.lessons_path = str(lessons)
    # args.origin 은 MagicMock 자동 속성 — 문자열이 아니므로 무시돼야 함

    with patch("builtins.print"):
        result = ha_review.cmd_extract_lesson(args)

    assert result == 0
    assert "origin:" not in lessons.read_text(encoding="utf-8")
