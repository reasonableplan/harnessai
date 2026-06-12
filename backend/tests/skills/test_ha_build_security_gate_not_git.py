"""G3 회귀 테스트: ha-build _run_security_gate — not-git repo 에서 visible WARN.

결함: git repo 아니거나 git 미설치면 returncode≠0 → diff_text="" → return [] (silent pass).
Fix: _is_git_repo 로 명시적 git repo 체크 → WARN 출력 + 빈 리스트 반환 (visible pass).
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
    loader = SourceFileLoader("ha_build_run_sg", str(REPO_ROOT / "skills" / "ha-build" / "run.py"))
    spec = importlib.util.spec_from_loader("ha_build_run_sg", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_build_run_sg"] = mod
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ha_build() -> ModuleType:
    return _load_ha_build()


def _make_plan():
    return SimpleNamespace(profiles=[SimpleNamespace(id="fastapi", path=".")])


# ── _is_git_repo 단위 테스트 ───────────────────────────────────────────────


def test_is_git_repo_returns_true_when_git_repo(ha_build, tmp_path, monkeypatch) -> None:
    """git rev-parse --git-dir 성공 (rc=0) → (True, True)."""
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: CompletedProcess(args=a[0], returncode=0, stdout=".git", stderr=""),
    )
    is_repo, git_installed = ha_build._is_git_repo(tmp_path)
    assert is_repo is True
    assert git_installed is True


def test_is_git_repo_returns_false_when_not_repo(ha_build, tmp_path, monkeypatch) -> None:
    """git rev-parse --git-dir 실패 (rc=128) → (False, True)."""
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: CompletedProcess(
            args=a[0], returncode=128, stdout="", stderr="fatal: not a git repository"
        ),
    )
    is_repo, git_installed = ha_build._is_git_repo(tmp_path)
    assert is_repo is False
    assert git_installed is True


def test_is_git_repo_returns_false_when_git_not_installed(ha_build, tmp_path, monkeypatch) -> None:
    """git 미설치 → FileNotFoundError → (False, False)."""

    def _raise(*a, **kw):
        raise FileNotFoundError("git not found")

    monkeypatch.setattr("subprocess.run", _raise)
    is_repo, git_installed = ha_build._is_git_repo(tmp_path)
    assert is_repo is False
    assert git_installed is False


# ── _run_security_gate not-git WARN 테스트 ────────────────────────────────


def test_security_gate_warns_when_git_not_installed(
    ha_build, tmp_path, monkeypatch, capsys
) -> None:
    """git 미설치 → WARN 출력 + 빈 리스트 반환 (silent pass → visible pass)."""
    monkeypatch.setattr(ha_build, "_is_git_repo", lambda p: (False, False))
    plan = _make_plan()

    result = ha_build._run_security_gate(tmp_path, plan)

    assert result == []
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "[WARN]" in combined
    assert "git" in combined


def test_security_gate_warns_when_not_git_repo(ha_build, tmp_path, monkeypatch, capsys) -> None:
    """git 있지만 repo 아님 → WARN 출력 + 빈 리스트 반환."""
    monkeypatch.setattr(ha_build, "_is_git_repo", lambda p: (False, True))
    plan = _make_plan()

    result = ha_build._run_security_gate(tmp_path, plan)

    assert result == []
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "[WARN]" in combined
    assert "git" in combined


def test_security_gate_warn_message_includes_git_init_hint(
    ha_build, tmp_path, monkeypatch, capsys
) -> None:
    """not-repo WARN 메시지에 git init 힌트 포함."""
    monkeypatch.setattr(ha_build, "_is_git_repo", lambda p: (False, True))
    plan = _make_plan()

    # info() 는 stderr 로 출력 — redirect 로 캡처해 git init 힌트 단언
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        ha_build._run_security_gate(tmp_path, plan)
    assert "git init" in buf.getvalue()


def test_security_gate_proceeds_normally_in_git_repo(ha_build, tmp_path, monkeypatch) -> None:
    """git repo 이면 _is_git_repo 이후 정상 diff 흐름 진입 (빈 diff → 빈 리스트)."""
    monkeypatch.setattr(ha_build, "_is_git_repo", lambda p: (True, True))
    # git diff 는 rc=0, 빈 출력
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: CompletedProcess(args=a[0], returncode=0, stdout="", stderr=""),
    )
    plan = _make_plan()

    result = ha_build._run_security_gate(tmp_path, plan)

    assert result == []


def test_security_gate_no_warn_in_git_repo(ha_build, tmp_path, monkeypatch, capsys) -> None:
    """정상 git repo 에서는 WARN 없음."""
    monkeypatch.setattr(ha_build, "_is_git_repo", lambda p: (True, True))
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: CompletedProcess(args=a[0], returncode=0, stdout="", stderr=""),
    )
    plan = _make_plan()

    ha_build._run_security_gate(tmp_path, plan)

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "[WARN]" not in combined


# ── LESSON-030: 문서 diff 제외 + 자기 패키지 import ──────────────────────


_MD_EVAL_DIFF = (
    "diff --git a/backend/docs/harness-plan.md b/backend/docs/harness-plan.md\n"
    "--- a/backend/docs/harness-plan.md\n"
    "+++ b/backend/docs/harness-plan.md\n"
    "+  rationale: external eval (matching rate 50%) remains manual\n"
)

_PY_EVAL_DIFF = (
    "diff --git a/backend/src/app.py b/backend/src/app.py\n"
    "--- a/backend/src/app.py\n"
    "+++ b/backend/src/app.py\n"
    "+result = eval(user_input)\n"
)


def _mock_git_diff(stdout: str):
    def _run(*a, **kw):
        return CompletedProcess(args=a[0], returncode=0, stdout=stdout, stderr="")

    return _run


def test_security_gate_ignores_md_prose_eval(ha_build, tmp_path, monkeypatch) -> None:
    """실전 FP 재현 (code-hijack Phase 4): harness-plan.md 산문 'eval (' → BLOCK 0."""
    monkeypatch.setattr(ha_build, "_is_git_repo", lambda p: (True, True))
    monkeypatch.setattr("subprocess.run", _mock_git_diff(_MD_EVAL_DIFF))

    assert ha_build._run_security_gate(tmp_path, _make_plan()) == []


def test_security_gate_still_blocks_py_eval(ha_build, tmp_path, monkeypatch) -> None:
    """문서 제외가 코드 검사까지 무력화하지 않음 — .py 의 eval() 은 여전히 BLOCK."""
    monkeypatch.setattr(ha_build, "_is_git_repo", lambda p: (True, True))
    monkeypatch.setattr("subprocess.run", _mock_git_diff(_MD_EVAL_DIFF + _PY_EVAL_DIFF))

    failures = ha_build._run_security_gate(tmp_path, _make_plan())
    assert any("eval" in f for f in failures)
    assert all("harness-plan.md" not in f for f in failures)


# ── dogfood P1: untracked 신규 파일 게이트 합류 ───────────────────────────


def _init_real_repo(path: Path) -> None:
    import subprocess as sp

    sp.run(["git", "init", "-q"], cwd=path, check=True)
    sp.run(
        [
            "git", "-c", "user.email=t@example.com", "-c", "user.name=t",
            "commit", "--allow-empty", "-m", "init", "-q",
        ],
        cwd=path, check=True,
    )


def test_security_gate_blocks_untracked_py_eval(ha_build, tmp_path) -> None:
    """방금 생성된 (아직 add 안 된) .py 의 eval() 도 BLOCK — 기존엔 게이트 우회."""
    _init_real_repo(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "service.py").write_text("eval(user_input)\n", encoding="utf-8")

    failures = ha_build._run_security_gate(tmp_path, _make_plan())

    assert any("eval" in f for f in failures)


def test_security_gate_untracked_md_only_passes(ha_build, tmp_path) -> None:
    """untracked 가 문서뿐이면 게이트 통과 (LESSON-030 제외 규칙 그대로 적용)."""
    _init_real_repo(tmp_path)
    (tmp_path / "notes.md").write_text("external eval ( prose\n", encoding="utf-8")

    assert ha_build._run_security_gate(tmp_path, _make_plan()) == []
