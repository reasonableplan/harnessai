"""V6 회귀 테스트: ha-verify record 재작업 T-ID 게이트.

결함 요약:
  V6: cmd_record 가 --summary 텍스트만 받고 T-ID 명시 없어도 통과.
  SKILL.md 가드레일 "passed=false 시 재작업 T-ID 없이 FAIL 보고 금지" 미강제.

Fix:
  - --rework-tasks "T-001,T-002" (CSV) 추가.
  - passed=false 면 --rework-tasks 비어있지 않거나 --no-rework 명시 필수.
  - 둘 다 없으면 exit 1 + actionable 한국어 에러.
  - verify_history summary 에 [rework: T-001,T-002] 자동 포함.
  - passed=true → 기존대로 (rework 체크 없음).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HA_VERIFY_RUN = REPO_ROOT / "skills" / "ha-verify" / "run.py"


@pytest.fixture(scope="module")
def ha_verify() -> ModuleType:
    """ha-verify/run.py (repo mirror) 를 모듈로 로드."""
    loader = SourceFileLoader("ha_verify_record_gate", str(HA_VERIFY_RUN))
    spec = importlib.util.spec_from_loader("ha_verify_record_gate", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_verify_record_gate"] = mod
    loader.exec_module(mod)
    return mod


def _make_mock_plan(current_step: str = "built") -> MagicMock:
    """최소 mock plan 생성."""
    mock_plan = MagicMock()
    mock_plan.pipeline.current_step = current_step
    mock_plan.verify_history = []
    return mock_plan


# ── V6-1: passed=false + rework-tasks 없음 + no-rework 없음 → exit 1 ──


def test_record_failed_without_rework_exits_1(ha_verify: ModuleType) -> None:
    """passed=false + --rework-tasks '' + --no-rework 없음 → exit 1."""
    mock_plan = _make_mock_plan("built")

    with (
        patch.object(
            ha_verify,
            "load_plan",
            return_value=(mock_plan, Path("/fake/harness-plan.md"), Path("/fake")),
        ),
        patch.object(ha_verify, "assert_state"),
    ):
        args = MagicMock()
        args.passed = "false"
        args.summary = "pytest 5 failed"
        args.rework_tasks = ""
        args.no_rework = False
        result = ha_verify.cmd_record(args)

    assert result == 1


def test_record_failed_error_message_mentions_rework_tasks(
    ha_verify: ModuleType, capsys: pytest.CaptureFixture
) -> None:
    """passed=false 게이트 에러 메시지에 '--rework-tasks' 포함."""
    mock_plan = _make_mock_plan("built")

    with (
        patch.object(
            ha_verify,
            "load_plan",
            return_value=(mock_plan, Path("/fake/harness-plan.md"), Path("/fake")),
        ),
        patch.object(ha_verify, "assert_state"),
    ):
        args = MagicMock()
        args.passed = "false"
        args.summary = "some failure"
        args.rework_tasks = ""
        args.no_rework = False
        ha_verify.cmd_record(args)

    captured = capsys.readouterr()
    combined = captured.err + captured.out
    assert "--rework-tasks" in combined or "재작업 T-ID" in combined


# ── V6-2: passed=false + --rework-tasks "T-001" → 통과 + summary 포함 ──


def test_record_failed_with_rework_tasks_passes(ha_verify: ModuleType) -> None:
    """passed=false + --rework-tasks "T-001,T-002" → exit 0 + summary 에 rework 포함."""
    mock_plan = _make_mock_plan("built")

    captured: list[str] = []

    def fake_print(data: str, **kwargs) -> None:  # type: ignore[misc]
        captured.append(data)

    with (
        patch.object(
            ha_verify,
            "load_plan",
            return_value=(mock_plan, Path("/fake/harness-plan.md"), Path("/fake")),
        ),
        patch.object(ha_verify, "assert_state"),
        patch.object(ha_verify, "record_verify"),
        patch.object(ha_verify, "regress"),
        patch.object(ha_verify, "save_plan"),
        patch("builtins.print", side_effect=fake_print),
    ):
        args = MagicMock()
        args.passed = "false"
        args.summary = "pytest 5 failed"
        args.rework_tasks = "T-001,T-002"
        args.no_rework = False
        result = ha_verify.cmd_record(args)

    assert result == 0
    output = json.loads(captured[0])
    assert output["rework_tasks"] == ["T-001", "T-002"]
    assert "rework" in output["summary"].lower() or "T-001" in output["summary"]


def test_record_failed_summary_includes_rework_tag(ha_verify: ModuleType) -> None:
    """passed=false + rework-tasks → summary 에 '[rework: T-001,T-002]' 자동 추가."""
    mock_plan = _make_mock_plan("built")

    captured: list[str] = []

    def fake_print(data: str, **kwargs) -> None:  # type: ignore[misc]
        captured.append(data)

    with (
        patch.object(
            ha_verify,
            "load_plan",
            return_value=(mock_plan, Path("/fake/harness-plan.md"), Path("/fake")),
        ),
        patch.object(ha_verify, "assert_state"),
        patch.object(ha_verify, "record_verify"),
        patch.object(ha_verify, "regress"),
        patch.object(ha_verify, "save_plan"),
        patch("builtins.print", side_effect=fake_print),
    ):
        args = MagicMock()
        args.passed = "false"
        args.summary = "pyright 3 errors"
        args.rework_tasks = "T-003"
        args.no_rework = False
        result = ha_verify.cmd_record(args)

    assert result == 0
    output = json.loads(captured[0])
    assert "[rework: T-003]" in output["summary"]


# ── V6-3: passed=false + --no-rework → 통과 ──────────────────────────


def test_record_failed_with_no_rework_passes(ha_verify: ModuleType) -> None:
    """passed=false + --no-rework → exit 0 (환경 문제 등 task 재작업 아닐 때)."""
    mock_plan = _make_mock_plan("built")

    captured: list[str] = []

    def fake_print(data: str, **kwargs) -> None:  # type: ignore[misc]
        captured.append(data)

    with (
        patch.object(
            ha_verify,
            "load_plan",
            return_value=(mock_plan, Path("/fake/harness-plan.md"), Path("/fake")),
        ),
        patch.object(ha_verify, "assert_state"),
        patch.object(ha_verify, "record_verify"),
        patch.object(ha_verify, "regress"),
        patch.object(ha_verify, "save_plan"),
        patch("builtins.print", side_effect=fake_print),
    ):
        args = MagicMock()
        args.passed = "false"
        args.summary = "install 실패: 네트워크 오류"
        args.rework_tasks = ""
        args.no_rework = True
        result = ha_verify.cmd_record(args)

    assert result == 0
    output = json.loads(captured[0])
    assert output["rework_tasks"] == []


# ── V6-4: passed=true → 기존대로 (rework 체크 없음) ─────────────────


def test_record_passed_no_rework_check(ha_verify: ModuleType) -> None:
    """passed=true → rework-tasks 없어도 통과 (exit 0)."""
    mock_plan = _make_mock_plan("built")

    captured: list[str] = []

    def fake_print(data: str, **kwargs) -> None:  # type: ignore[misc]
        captured.append(data)

    with (
        patch.object(
            ha_verify,
            "load_plan",
            return_value=(mock_plan, Path("/fake/harness-plan.md"), Path("/fake")),
        ),
        patch.object(ha_verify, "assert_state"),
        patch.object(ha_verify, "record_verify"),
        patch.object(ha_verify, "transition"),
        patch.object(ha_verify, "save_plan"),
        patch("builtins.print", side_effect=fake_print),
    ):
        args = MagicMock()
        args.passed = "true"
        args.summary = "pytest 327 passed, ruff clean, pyright 0 errors"
        args.rework_tasks = ""
        args.no_rework = False
        result = ha_verify.cmd_record(args)

    assert result == 0
    output = json.loads(captured[0])
    assert output["passed"] is True
    assert output["rework_tasks"] == []


def test_record_passed_output_has_rework_tasks_field(ha_verify: ModuleType) -> None:
    """passed=true 출력에도 rework_tasks 필드가 빈 리스트로 존재."""
    mock_plan = _make_mock_plan("built")

    captured: list[str] = []

    def fake_print(data: str, **kwargs) -> None:  # type: ignore[misc]
        captured.append(data)

    with (
        patch.object(
            ha_verify,
            "load_plan",
            return_value=(mock_plan, Path("/fake/harness-plan.md"), Path("/fake")),
        ),
        patch.object(ha_verify, "assert_state"),
        patch.object(ha_verify, "record_verify"),
        patch.object(ha_verify, "transition"),
        patch.object(ha_verify, "save_plan"),
        patch("builtins.print", side_effect=fake_print),
    ):
        args = MagicMock()
        args.passed = "true"
        args.summary = "all passed"
        args.rework_tasks = ""
        args.no_rework = False
        ha_verify.cmd_record(args)

    output = json.loads(captured[0])
    assert "rework_tasks" in output, f"rework_tasks field missing: {list(output.keys())}"
    assert output["rework_tasks"] == []
