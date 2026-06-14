"""R2/R5/R6 회귀 테스트: ha-review 보안 훅 자동 실행 + record gate.

결함 요약:
  R2: cmd_prepare 가 ai-slop 만 실행하고 SecurityHooks 7개 훅과 mobile 룰을 호출 안 함.
  R5: record reject + violations 빈 string 도 통과 (가드레일 미강제).
  R6: record approve + BLOCK 발견 상태에서 통과 가능 (BLOCK 검증 없음).

Fix:
  - _collect_findings() 헬퍼: SecurityHooks.from_profile().run_all() + mobile 룰 모두 실행.
  - cmd_prepare: _collect_findings() 결과를 security_findings + security_summary 로 출력.
  - cmd_record: approve + BLOCK → exit 1. reject + violations 없음 → exit 1.
  - --allow-block flag: 의도적 BLOCK 우회.
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
HA_REVIEW_RUN = REPO_ROOT / "skills" / "ha-review" / "run.py"


@pytest.fixture(scope="module")
def ha_review() -> ModuleType:
    """ha-review/run.py (repo mirror) 를 모듈로 로드."""
    loader = SourceFileLoader("ha_review_record_gate", str(HA_REVIEW_RUN))
    spec = importlib.util.spec_from_loader("ha_review_record_gate", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_review_record_gate"] = mod
    loader.exec_module(mod)
    return mod


# ── R2: prepare 가 security_findings 키 포함 ──────────────────────────


def test_prepare_output_has_security_findings_key(ha_review: ModuleType, tmp_path: Path) -> None:
    """cmd_prepare 출력에 security_findings + security_summary 키가 존재."""
    mock_plan = MagicMock()
    mock_plan.pipeline.current_step = "verified"
    mock_plan.profiles = []
    mock_plan.skeleton_hash = ""

    captured_output: list[str] = []

    def fake_print(data: str, **kwargs) -> None:  # type: ignore[misc]
        captured_output.append(data)

    with (
        patch.object(
            ha_review, "load_plan", return_value=(mock_plan, tmp_path / "harness-plan.md", tmp_path)
        ),
        patch.object(ha_review, "assert_state"),
        patch.object(ha_review, "_check_git_repo"),
        patch.object(ha_review, "get_active_profiles", return_value=[]),
        patch.object(ha_review, "_extract_diff", return_value=("", "test-scope")),
        patch.object(
            ha_review,
            "_collect_findings",
            return_value={
                "ai_slop": [],
                "security": [],
                "block_count": 0,
                "warn_count": 0,
            },
        ),
        patch.object(
            ha_review,
            "check_skeleton_hash",
            return_value=MagicMock(
                skeleton_missing=True,
                is_legacy=False,
                is_match=True,
            ),
        ),
        patch("builtins.print", side_effect=fake_print),
    ):
        args = MagicMock()
        result = ha_review.cmd_prepare(args)

    assert result == 0
    assert len(captured_output) == 1
    output = json.loads(captured_output[0])
    assert "security_findings" in output, f"security_findings missing: {list(output.keys())}"
    assert "security_summary" in output, f"security_summary missing: {list(output.keys())}"
    assert "block_count" in output["security_summary"]
    assert "warn_count" in output["security_summary"]
    # backward compat
    assert "ai_slop_findings_in_diff" in output


def test_prepare_security_summary_reflects_block_count(
    ha_review: ModuleType, tmp_path: Path
) -> None:
    """_collect_findings 가 BLOCK 1건 반환 시 security_summary.block_count == 1."""
    mock_plan = MagicMock()
    mock_plan.pipeline.current_step = "verified"
    mock_plan.profiles = []
    mock_plan.skeleton_hash = ""

    captured_output: list[str] = []

    def fake_print(data: str, **kwargs) -> None:  # type: ignore[misc]
        captured_output.append(data)

    block_finding = {
        "hook": "secret-filter",
        "severity": "BLOCK",
        "message": "하드코딩 시크릿",
        "snippet": "",
    }
    with (
        patch.object(
            ha_review, "load_plan", return_value=(mock_plan, tmp_path / "harness-plan.md", tmp_path)
        ),
        patch.object(ha_review, "assert_state"),
        patch.object(ha_review, "_check_git_repo"),
        patch.object(ha_review, "get_active_profiles", return_value=[]),
        patch.object(ha_review, "_extract_diff", return_value=("", "test-scope")),
        patch.object(
            ha_review,
            "_collect_findings",
            return_value={
                "ai_slop": [],
                "security": [block_finding],
                "block_count": 1,
                "warn_count": 0,
            },
        ),
        patch.object(
            ha_review,
            "check_skeleton_hash",
            return_value=MagicMock(
                skeleton_missing=True,
                is_legacy=False,
                is_match=True,
            ),
        ),
        patch("builtins.print", side_effect=fake_print),
    ):
        args = MagicMock()
        result = ha_review.cmd_prepare(args)

    assert result == 0  # prepare 는 advisory — BLOCK 있어도 exit 0
    output = json.loads(captured_output[0])
    assert output["security_summary"]["block_count"] == 1
    assert len(output["security_findings"]) == 1


# ── R2: _collect_findings 가 SecurityHooks 를 호출 ────────────────────


def test_collect_findings_calls_security_hooks(ha_review: ModuleType, tmp_path: Path) -> None:
    """_collect_findings 가 SecurityHooks.from_profile().run_all() 을 호출."""
    mock_profile = MagicMock()
    mock_profile.id = "fastapi"

    mock_result = MagicMock()
    mock_result.findings = []

    mock_hooks_instance = MagicMock()
    mock_hooks_instance.run_all.return_value = mock_result

    with patch.object(ha_review, "SecurityHooks") as mock_hooks_cls:
        mock_hooks_cls.from_profile.return_value = mock_hooks_instance
        result = ha_review._collect_findings(tmp_path, [mock_profile], "some diff text")

    # extra_python_allowed: tmp_path 에 로컬 패키지 없음 → 빈 frozenset (LESSON-030).
    # backend 모드라 frontend FP #19 채널(extra_frontend_*)은 None.
    mock_hooks_cls.from_profile.assert_called_once_with(
        mock_profile,
        extra_python_allowed=frozenset(),
        extra_frontend_allowed=None,
        extra_frontend_prefixes=None,
    )
    mock_hooks_instance.run_all.assert_called_once()
    assert "security" in result
    assert "ai_slop" in result
    assert "block_count" in result


def test_collect_findings_mobile_profile_runs_mobile_rules(
    ha_review: ModuleType, tmp_path: Path
) -> None:
    """_collect_findings — mobile profile 이면 mobile 룰도 실행."""
    mock_profile = MagicMock()
    mock_profile.id = "react-native-expo"

    mock_result = MagicMock()
    mock_result.findings = []

    mock_hooks_instance = MagicMock()
    mock_hooks_instance.run_all.return_value = mock_result

    diff = "+  await AsyncStorage.setItem('auth_token', token);\n"

    with patch.object(ha_review, "SecurityHooks") as mock_hooks_cls:
        mock_hooks_cls.from_profile.return_value = mock_hooks_instance
        result = ha_review._collect_findings(tmp_path, [mock_profile], diff)

    # mobile 룰(_check_mobile_secret_storage)이 BLOCK 을 추가해야 함
    block_items = [f for f in result["security"] if f.get("severity") == "BLOCK"]
    assert len(block_items) >= 1, (
        f"mobile secret storage BLOCK 기대, got security={result['security']}"
    )
    assert result["block_count"] >= 1


# ── R5: record reject + violations 없음 → exit 1 ──────────────────────


def test_record_reject_without_violations_exits_1(ha_review: ModuleType) -> None:
    """record reject + --violations '' → exit 1."""
    mock_plan = MagicMock()
    mock_plan.pipeline.current_step = "verified"

    with (
        patch.object(
            ha_review,
            "load_plan",
            return_value=(mock_plan, Path("/fake/harness-plan.md"), Path("/fake")),
        ),
        patch.object(ha_review, "assert_state"),
    ):
        args = MagicMock()
        args.verdict = "reject"
        args.violations = ""
        args.summary = "some summary"
        args.allow_block = False
        result = ha_review.cmd_record(args)

    assert result == 1


def test_record_reject_with_empty_json_array_exits_1(ha_review: ModuleType) -> None:
    """record reject + --violations '[]' (빈 배열) → exit 1."""
    mock_plan = MagicMock()
    mock_plan.pipeline.current_step = "verified"

    with (
        patch.object(
            ha_review,
            "load_plan",
            return_value=(mock_plan, Path("/fake/harness-plan.md"), Path("/fake")),
        ),
        patch.object(ha_review, "assert_state"),
    ):
        args = MagicMock()
        args.verdict = "reject"
        args.violations = "[]"
        args.summary = "some summary"
        args.allow_block = False
        result = ha_review.cmd_record(args)

    assert result == 1


def test_record_reject_with_violations_passes(ha_review: ModuleType) -> None:
    """record reject + violations 있는 JSON → 통과 (exit 0)."""
    mock_plan = MagicMock()
    mock_plan.pipeline.current_step = "verified"
    mock_plan.verify_history = []

    captured: list[str] = []

    def fake_print(data: str, **kwargs) -> None:  # type: ignore[misc]
        captured.append(data)

    with (
        patch.object(
            ha_review,
            "load_plan",
            return_value=(mock_plan, Path("/fake/harness-plan.md"), Path("/fake")),
        ),
        patch.object(ha_review, "assert_state"),
        patch.object(ha_review, "record_verify"),
        patch.object(ha_review, "regress"),
        patch.object(ha_review, "save_plan"),
        patch("builtins.print", side_effect=fake_print),
    ):
        args = MagicMock()
        args.verdict = "reject"
        args.violations = '["[auth-guard:BLOCK] src/foo.py:42 — JWT type claim 누락 → T-003"]'
        args.summary = "auth guard violation"
        args.allow_block = False
        result = ha_review.cmd_record(args)

    assert result == 0
    output = json.loads(captured[0])
    assert output["verdict"] == "reject"
    assert len(output["violations"]) == 1


# ── R6: record approve + BLOCK → exit 1 ──────────────────────────────


def test_record_approve_with_block_exits_1(ha_review: ModuleType) -> None:
    """record approve + BLOCK 1건 → exit 1."""
    mock_plan = MagicMock()
    mock_plan.pipeline.current_step = "verified"

    block_finding = {
        "hook": "secret-filter",
        "severity": "BLOCK",
        "message": "하드코딩 시크릿",
        "snippet": "",
    }
    findings_result = {
        "ai_slop": [],
        "security": [block_finding],
        "block_count": 1,
        "warn_count": 0,
    }

    with (
        patch.object(
            ha_review,
            "load_plan",
            return_value=(mock_plan, Path("/fake/harness-plan.md"), Path("/fake")),
        ),
        patch.object(ha_review, "assert_state"),
        patch.object(ha_review, "get_active_profiles", return_value=[]),
        patch.object(ha_review, "_extract_diff", return_value=("", "test-scope")),
        patch.object(ha_review, "_collect_findings", return_value=findings_result),
    ):
        args = MagicMock()
        args.verdict = "approve"
        args.violations = ""
        args.summary = ""
        args.allow_block = False
        result = ha_review.cmd_record(args)

    assert result == 1


def test_record_approve_with_block_and_allow_block_passes(ha_review: ModuleType) -> None:
    """record approve + BLOCK 1건 + --allow-block → 통과 (exit 0)."""
    mock_plan = MagicMock()
    mock_plan.pipeline.current_step = "verified"
    mock_plan.verify_history = []

    captured: list[str] = []

    def fake_print(data: str, **kwargs) -> None:  # type: ignore[misc]
        captured.append(data)

    with (
        patch.object(
            ha_review,
            "load_plan",
            return_value=(mock_plan, Path("/fake/harness-plan.md"), Path("/fake")),
        ),
        patch.object(ha_review, "assert_state"),
        patch.object(ha_review, "record_verify"),
        patch.object(ha_review, "transition"),
        patch.object(ha_review, "save_plan"),
        patch("builtins.print", side_effect=fake_print),
    ):
        args = MagicMock()
        args.verdict = "approve"
        args.violations = ""
        args.summary = "override approved"
        args.allow_block = True
        result = ha_review.cmd_record(args)

    assert result == 0
    output = json.loads(captured[0])
    assert output["verdict"] == "approve"


def test_record_approve_no_block_passes(ha_review: ModuleType) -> None:
    """record approve + BLOCK 0건 → 정상 통과 (exit 0)."""
    mock_plan = MagicMock()
    mock_plan.pipeline.current_step = "verified"
    mock_plan.verify_history = []

    captured: list[str] = []

    def fake_print(data: str, **kwargs) -> None:  # type: ignore[misc]
        captured.append(data)

    findings_result = {"ai_slop": [], "security": [], "block_count": 0, "warn_count": 0}

    with (
        patch.object(
            ha_review,
            "load_plan",
            return_value=(mock_plan, Path("/fake/harness-plan.md"), Path("/fake")),
        ),
        patch.object(ha_review, "assert_state"),
        patch.object(ha_review, "get_active_profiles", return_value=[]),
        patch.object(ha_review, "_extract_diff", return_value=("", "test-scope")),
        patch.object(ha_review, "_collect_findings", return_value=findings_result),
        patch.object(ha_review, "record_verify"),
        patch.object(ha_review, "transition"),
        patch.object(ha_review, "save_plan"),
        patch("builtins.print", side_effect=fake_print),
    ):
        args = MagicMock()
        args.verdict = "approve"
        args.violations = ""
        args.summary = "all clean"
        args.allow_block = False
        result = ha_review.cmd_record(args)

    assert result == 0


def test_record_approve_error_message_mentions_block(
    ha_review: ModuleType, capsys: pytest.CaptureFixture
) -> None:
    """approve + BLOCK 시 에러 메시지에 'BLOCK 위반' 포함."""
    mock_plan = MagicMock()
    mock_plan.pipeline.current_step = "verified"

    block_finding = {
        "hook": "command-guard",
        "severity": "BLOCK",
        "message": "eval() 사용",
        "snippet": "eval(x)",
    }
    findings_result = {
        "ai_slop": [],
        "security": [block_finding],
        "block_count": 1,
        "warn_count": 0,
    }

    with (
        patch.object(
            ha_review,
            "load_plan",
            return_value=(mock_plan, Path("/fake/harness-plan.md"), Path("/fake")),
        ),
        patch.object(ha_review, "assert_state"),
        patch.object(ha_review, "get_active_profiles", return_value=[]),
        patch.object(ha_review, "_extract_diff", return_value=("", "test-scope")),
        patch.object(ha_review, "_collect_findings", return_value=findings_result),
    ):
        args = MagicMock()
        args.verdict = "approve"
        args.violations = ""
        args.summary = ""
        args.allow_block = False
        ha_review.cmd_record(args)

    captured = capsys.readouterr()
    assert "BLOCK 위반" in captured.err or "BLOCK 위반" in captured.out
