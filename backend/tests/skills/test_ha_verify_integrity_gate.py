"""G2 회귀 테스트: ha-verify cmd_prepare integrity gate.

결함: SKILL.md §1.5 가 harness integrity 실행 지시하지만 run.py cmd_prepare 가 미실행.
Fix: _run_integrity_check 가 harness integrity subprocess 실행 → advisory JSON 필드 포함.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from subprocess import CompletedProcess
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HA_VERIFY_RUN = REPO_ROOT / "skills" / "ha-verify" / "run.py"


@pytest.fixture(scope="module")
def ha_verify() -> ModuleType:
    loader = SourceFileLoader("ha_verify_integrity_gate", str(HA_VERIFY_RUN))
    spec = importlib.util.spec_from_loader("ha_verify_integrity_gate", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_verify_integrity_gate"] = mod
    loader.exec_module(mod)
    return mod


# ── _run_integrity_check 단위 테스트 ──────────────────────────────────────


def test_run_integrity_check_passed_when_harness_exits_0(ha_verify, tmp_path, monkeypatch) -> None:
    """harness integrity exit 0 → passed=True, skipped=False."""
    harness_bin = tmp_path / "harness" / "bin" / "harness"
    harness_bin.parent.mkdir(parents=True)
    harness_bin.touch()

    monkeypatch.setattr(ha_verify, "HARNESS_HOME", tmp_path)
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: CompletedProcess(args=a[0], returncode=0, stdout="OK", stderr=""),
    )

    result = ha_verify._run_integrity_check(tmp_path)

    assert result["passed"] is True
    assert result["skipped"] is False
    assert result["output"] == "OK"


def test_run_integrity_check_failed_when_harness_exits_nonzero(ha_verify, tmp_path, monkeypatch, capsys) -> None:
    """harness integrity exit 1 → passed=False, skipped=False, WARN 출력."""
    harness_bin = tmp_path / "harness" / "bin" / "harness"
    harness_bin.parent.mkdir(parents=True)
    harness_bin.touch()

    monkeypatch.setattr(ha_verify, "HARNESS_HOME", tmp_path)
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: CompletedProcess(args=a[0], returncode=1, stdout="placeholder detected", stderr=""),
    )

    result = ha_verify._run_integrity_check(tmp_path)

    assert result["passed"] is False
    assert result["skipped"] is False
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "[WARN]" in combined


def test_run_integrity_check_skipped_when_harness_bin_missing(ha_verify, tmp_path, monkeypatch) -> None:
    """harness 바이너리 없음 → skipped=True, passed=None."""
    # HARNESS_HOME 을 빈 tmp_path 로 → harness/bin/harness 없음
    monkeypatch.setattr(ha_verify, "HARNESS_HOME", tmp_path)

    result = ha_verify._run_integrity_check(tmp_path)

    assert result["passed"] is None
    assert result["skipped"] is True
    assert "harness 바이너리 없음" in result["reason"]


def test_run_integrity_check_skipped_on_timeout(ha_verify, tmp_path, monkeypatch) -> None:
    """harness integrity 타임아웃 → skipped=True, reason='timeout'."""
    import subprocess
    harness_bin = tmp_path / "harness" / "bin" / "harness"
    harness_bin.parent.mkdir(parents=True)
    harness_bin.touch()

    monkeypatch.setattr(ha_verify, "HARNESS_HOME", tmp_path)

    def _timeout(*a, **kw):
        raise subprocess.TimeoutExpired(cmd=a[0], timeout=60)

    monkeypatch.setattr("subprocess.run", _timeout)

    result = ha_verify._run_integrity_check(tmp_path)

    assert result["passed"] is None
    assert result["skipped"] is True
    assert result["reason"] == "timeout"


# ── cmd_prepare 출력에 integrity 필드 포함 확인 ──────────────────────────


def _make_mock_plan_for_prepare(current_step: str = "built") -> MagicMock:
    mock_plan = MagicMock()
    mock_plan.pipeline.current_step = current_step
    mock_plan.verify_history = []
    mock_plan.profiles = []
    mock_plan.skeleton_hash = ""
    return mock_plan


def test_cmd_prepare_output_includes_integrity_passed(ha_verify, tmp_path, monkeypatch, capsys) -> None:
    """cmd_prepare JSON 출력에 integrity_passed 필드 존재."""
    mock_plan = _make_mock_plan_for_prepare("built")
    plan_path = tmp_path / "docs" / "harness-plan.md"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("", encoding="utf-8")

    # skeleton.md 없음 → check_skeleton_hash 를 SimpleNamespace 로 mock
    mock_hash_check = SimpleNamespace(is_match=True, is_legacy=False, skeleton_missing=True)

    monkeypatch.setattr(ha_verify, "load_plan", lambda: (mock_plan, plan_path, tmp_path))
    monkeypatch.setattr(ha_verify, "assert_state", lambda *a, **kw: None)
    monkeypatch.setattr(ha_verify, "get_active_profiles", lambda *a, **kw: [])
    monkeypatch.setattr(ha_verify, "check_skeleton_hash", lambda *a, **kw: mock_hash_check)
    monkeypatch.setattr(ha_verify, "_run_integrity_check", lambda p: {"passed": True, "skipped": False, "reason": "", "output": "OK"})

    rc = ha_verify.cmd_prepare(SimpleNamespace())

    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert "integrity_passed" in data
    assert "integrity_check" in data
    assert data["integrity_passed"] is True


def test_cmd_prepare_integrity_check_field_on_failure(ha_verify, tmp_path, monkeypatch, capsys) -> None:
    """integrity 실패 시 integrity_passed=False 가 JSON 에 포함."""
    mock_plan = _make_mock_plan_for_prepare("built")
    plan_path = tmp_path / "docs" / "harness-plan.md"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("", encoding="utf-8")

    mock_hash_check = SimpleNamespace(is_match=True, is_legacy=False, skeleton_missing=True)

    monkeypatch.setattr(ha_verify, "load_plan", lambda: (mock_plan, plan_path, tmp_path))
    monkeypatch.setattr(ha_verify, "assert_state", lambda *a, **kw: None)
    monkeypatch.setattr(ha_verify, "get_active_profiles", lambda *a, **kw: [])
    monkeypatch.setattr(ha_verify, "check_skeleton_hash", lambda *a, **kw: mock_hash_check)
    monkeypatch.setattr(ha_verify, "_run_integrity_check", lambda p: {"passed": False, "skipped": False, "reason": "", "output": "placeholder detected"})

    rc = ha_verify.cmd_prepare(SimpleNamespace())

    assert rc == 0  # advisory only — fail-fast 아님
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["integrity_passed"] is False
    assert data["integrity_check"]["output"] == "placeholder detected"
