"""LESSON-021: ha-build 의 toolchain 게이트 (`_run_toolchain_gate`) 단위 테스트.

대상: `skills/ha-build/run.py::_run_toolchain_gate`, `_detect_no_tests_signal`
전략: subprocess.run 을 monkeypatch 해 OS 의존성 없이 성공/실패 흐름 검증.
B3: _detect_no_tests_signal 단위 + no-tests WARN 출력 검증 추가.
"""

from __future__ import annotations

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from subprocess import CompletedProcess
from types import ModuleType, SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_ha_build() -> ModuleType:
    loader = SourceFileLoader("ha_build_run", str(REPO_ROOT / "skills" / "ha-build" / "run.py"))
    spec = importlib.util.spec_from_loader("ha_build_run", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_build_run"] = mod
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ha_build():
    return _load_ha_build()


def _make_plan(profile_id: str, path: str, test_cmd: str, lint_cmd: str, type_cmd: str | None):
    """최소 plan 객체 — _run_toolchain_gate 가 요구하는 구조만 충족."""
    return SimpleNamespace(
        profiles=[SimpleNamespace(id=profile_id, path=path)],
    )


def _patch_get_active_profiles(
    ha_build, profile_id: str, test_cmd: str, lint_cmd: str, type_cmd: str | None, monkeypatch
):
    """get_active_profiles 를 모킹해 가짜 프로파일 반환."""
    fake_profile = SimpleNamespace(
        id=profile_id,
        toolchain=SimpleNamespace(test=test_cmd, lint=lint_cmd, type=type_cmd),
    )
    monkeypatch.setattr(ha_build, "get_active_profiles", lambda plan, project: [fake_profile])


def _make_subprocess_mock(fail_cmds: set[str]):
    """지정 명령은 rc=1, 나머지는 rc=0 반환하는 subprocess.run 대체."""

    def _run(cmd, **kwargs):
        rc = 1 if cmd in fail_cmds else 0
        return CompletedProcess(args=cmd, returncode=rc, stdout=b"", stderr=b"")

    return _run


def test_toolchain_gate_passes_when_all_commands_succeed(ha_build, tmp_path, monkeypatch) -> None:
    _patch_get_active_profiles(
        ha_build, "python-cli", "cmd-test", "cmd-lint", "cmd-type", monkeypatch
    )
    monkeypatch.setattr("subprocess.run", _make_subprocess_mock(set()))
    plan = _make_plan("python-cli", ".", "cmd-test", "cmd-lint", "cmd-type")
    failures = ha_build._run_toolchain_gate(tmp_path, plan)
    assert failures == []


def test_toolchain_gate_reports_failing_test(ha_build, tmp_path, monkeypatch) -> None:
    _patch_get_active_profiles(
        ha_build, "python-cli", "cmd-test", "cmd-lint", "cmd-type", monkeypatch
    )
    monkeypatch.setattr("subprocess.run", _make_subprocess_mock({"cmd-test"}))
    plan = _make_plan("python-cli", ".", "cmd-test", "cmd-lint", "cmd-type")
    failures = ha_build._run_toolchain_gate(tmp_path, plan)
    assert len(failures) == 1
    assert "test 실패" in failures[0]
    assert "python-cli" in failures[0]


def test_toolchain_gate_reports_multiple_failures(ha_build, tmp_path, monkeypatch) -> None:
    (tmp_path / "backend").mkdir()
    _patch_get_active_profiles(ha_build, "fastapi", "cmd-test", "cmd-lint", "cmd-type", monkeypatch)
    monkeypatch.setattr("subprocess.run", _make_subprocess_mock({"cmd-test", "cmd-type"}))
    plan = _make_plan("fastapi", "backend", "cmd-test", "cmd-lint", "cmd-type")
    failures = ha_build._run_toolchain_gate(tmp_path, plan)
    assert len(failures) == 2
    messages = "\n".join(failures)
    assert "test 실패" in messages
    assert "type 실패" in messages
    assert "lint 실패" not in messages


def test_toolchain_gate_skips_none_commands(ha_build, tmp_path, monkeypatch) -> None:
    _patch_get_active_profiles(ha_build, "claude-skill", "cmd-test", "cmd-lint", None, monkeypatch)
    monkeypatch.setattr("subprocess.run", _make_subprocess_mock(set()))
    plan = _make_plan("claude-skill", ".", "cmd-test", "cmd-lint", None)
    failures = ha_build._run_toolchain_gate(tmp_path, plan)
    assert failures == []


def test_toolchain_gate_iterates_all_profiles(ha_build, tmp_path, monkeypatch) -> None:
    (tmp_path / "backend").mkdir()
    (tmp_path / "frontend").mkdir()
    profile_a = SimpleNamespace(
        id="fastapi",
        toolchain=SimpleNamespace(test="cmd-a-test", lint="cmd-a-lint", type="cmd-a-type"),
    )
    profile_b = SimpleNamespace(
        id="react-vite",
        toolchain=SimpleNamespace(test="cmd-b-test", lint="cmd-b-lint", type="cmd-b-type"),
    )
    monkeypatch.setattr(
        ha_build, "get_active_profiles", lambda plan, project: [profile_a, profile_b]
    )
    # react-vite 의 lint 만 실패
    monkeypatch.setattr("subprocess.run", _make_subprocess_mock({"cmd-b-lint"}))
    plan = SimpleNamespace(
        profiles=[
            SimpleNamespace(id="fastapi", path="backend"),
            SimpleNamespace(id="react-vite", path="frontend"),
        ]
    )
    failures = ha_build._run_toolchain_gate(tmp_path, plan)
    assert len(failures) == 1
    assert "react-vite" in failures[0]
    assert "lint 실패" in failures[0]


# ── B3: _detect_no_tests_signal 단위 테스트 ──────────────────────────────────


def test_detect_no_tests_signal_pytest_no_tests_ran(ha_build) -> None:
    """pytest 'no tests ran' → True."""
    stdout = "collected 0 items\n\n====== no tests ran ======"
    assert ha_build._detect_no_tests_signal(stdout) is True


def test_detect_no_tests_signal_pytest_no_tests_found(ha_build) -> None:
    """pytest 'no tests found' → True."""
    stdout = "ERROR: no tests found in /src/tests"
    assert ha_build._detect_no_tests_signal(stdout) is True


def test_detect_no_tests_signal_jest_pass_with_no_tests(ha_build) -> None:
    """jest --passWithNoTests 출력 → True."""
    stdout = "Test Suites: 0 skipped, 0 total\npassWithNoTests enabled, exiting with code 0"
    assert ha_build._detect_no_tests_signal(stdout) is True


def test_detect_no_tests_signal_zero_tests(ha_build) -> None:
    """'0 tests' 단독 → True."""
    stdout = "0 tests, 0 passing"
    assert ha_build._detect_no_tests_signal(stdout) is True


def test_detect_no_tests_signal_zero_passed_standalone(ha_build) -> None:
    """'0 passed' 단독 (실패도 없음) → True."""
    stdout = "0 passed in 0.01s"
    assert ha_build._detect_no_tests_signal(stdout) is True


def test_detect_no_tests_signal_normal_output_returns_false(ha_build) -> None:
    """정상 pytest 출력 (테스트 통과) → False."""
    stdout = "collected 42 items\n\n====== 42 passed in 1.23s ======"
    assert ha_build._detect_no_tests_signal(stdout) is False


def test_detect_no_tests_signal_empty_string_returns_false(ha_build) -> None:
    """빈 stdout → False."""
    assert ha_build._detect_no_tests_signal("") is False


def test_detect_no_tests_signal_zero_passed_with_failures_false(ha_build) -> None:
    """'0 passed, 5 failed' 는 false-positive 방지 → False."""
    stdout = "0 passed, 5 failed in 2.00s"
    assert ha_build._detect_no_tests_signal(stdout) is False


# ── B3: _run_toolchain_gate no-tests WARN 출력 검증 ─────────────────────────


def _make_subprocess_mock_with_output(stdout_map: dict[str, str]):
    """명령별 stdout 을 반환하는 subprocess.run 대체 (항상 rc=0)."""

    def _run(cmd, **kwargs):
        stdout = stdout_map.get(cmd, "all good")
        return CompletedProcess(args=cmd, returncode=0, stdout=stdout, stderr="")

    return _run


def test_toolchain_gate_warns_on_no_tests_signal(ha_build, tmp_path, monkeypatch, capsys) -> None:
    """test 명령 exit 0 이지만 no-tests 신호 → WARN 출력, failures 비어있음."""
    _patch_get_active_profiles(ha_build, "python-cli", "cmd-test", "cmd-lint", None, monkeypatch)
    # cmd-test 는 'no tests ran' 신호 포함 stdout 반환
    mock = _make_subprocess_mock_with_output({"cmd-test": "no tests ran"})
    monkeypatch.setattr("subprocess.run", mock)
    plan = _make_plan("python-cli", ".", "cmd-test", "cmd-lint", None)

    failures = ha_build._run_toolchain_gate(tmp_path, plan)

    # WARN 이지 BLOCK 아님 — failures 는 비어있어야 함
    assert failures == []
    # info() 가 stdout 에 WARN 메시지를 출력해야 함
    captured = capsys.readouterr()
    assert "LESSON-021 강화" in captured.out or "LESSON-021 강화" in captured.err


def test_toolchain_gate_no_warn_on_normal_test_output(
    ha_build, tmp_path, monkeypatch, capsys
) -> None:
    """정상 test 출력 → WARN 없음, failures 비어있음."""
    _patch_get_active_profiles(ha_build, "python-cli", "cmd-test", "cmd-lint", None, monkeypatch)
    mock = _make_subprocess_mock_with_output({"cmd-test": "42 passed in 1.23s"})
    monkeypatch.setattr("subprocess.run", mock)
    plan = _make_plan("python-cli", ".", "cmd-test", "cmd-lint", None)

    failures = ha_build._run_toolchain_gate(tmp_path, plan)

    assert failures == []
    captured = capsys.readouterr()
    assert "LESSON-021 강화" not in captured.out
    assert "LESSON-021 강화" not in captured.err
