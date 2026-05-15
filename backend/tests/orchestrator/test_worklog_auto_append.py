"""worklog 자동 append 통합 테스트 (3개).

대상: skills/ha-design/run.py::cmd_commit,
      skills/ha-build/run.py::cmd_complete,
      worklog append 실패 시 commit 자체는 통과하는지.

전략:
- ha-log/run.py::append_entry 를 monkeypatch 로 대체해 실제 파일 I/O 없이 호출 추적.
- subprocess.run 을 monkeypatch 해 ha-log subprocess 호출을 가로채어 검증.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_module(name: str, path: Path) -> ModuleType:
    loader = SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec is not None, f"spec load failed: {path}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ha_design() -> ModuleType:
    return _load_module("ha_design_worklog", REPO_ROOT / "skills" / "ha-design" / "run.py")


@pytest.fixture(scope="module")
def ha_build() -> ModuleType:
    return _load_module("ha_build_worklog", REPO_ROOT / "skills" / "ha-build" / "run.py")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_plan_design(frozen_status: str = "frozen") -> SimpleNamespace:
    return SimpleNamespace(
        pipeline=SimpleNamespace(
            current_step="designed",
            completed_steps=("ha-design",),
            skipped_steps=(),
            steps=("init", "designed", "planned"),
            gstack_mode="manual",
        ),
        frozen_status=frozen_status,
        locked_sections=["requirements", "user_journey"],
        ai_drafted_sections=[],
        skeleton_hash=None,
        skeleton_sections=SimpleNamespace(included=["requirements"]),
        profiles=[],
        activation_trace={},
    )


def _make_plan_build(frozen_status: str = "frozen") -> SimpleNamespace:
    return SimpleNamespace(
        pipeline=SimpleNamespace(
            current_step="building",
            completed_steps=("ha-build:T-001",),
            skipped_steps=(),
            steps=("planned", "building", "built"),
            gstack_mode="manual",
        ),
        frozen_status=frozen_status,
        profiles=[SimpleNamespace(id="fastapi", path=".")],
        skeleton_hash=None,
    )


_TASKS_ALL_DONE = (
    "| ID    | Agent         | Depends On | Description | Status     |\n"
    "|-------|---------------|------------|-------------|------------|\n"
    "| T-001 | backend_coder | -          | desc        | done       |\n"
)


# ---------------------------------------------------------------------------
# T1: ha-design commit 후 worklog append 호출 확인
# ---------------------------------------------------------------------------

def test_ha_design_commit_appends_worklog(ha_design, tmp_path: Path, monkeypatch) -> None:
    """ha-design cmd_commit 성공 시 subprocess.run 으로 ha-log 가 호출됨."""
    plan = _make_plan_design()
    plan_path = tmp_path / "docs" / "harness-plan.md"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("", encoding="utf-8")

    skeleton_path = tmp_path / "docs" / "skeleton.md"
    skeleton_path.write_text("# skeleton\n", encoding="utf-8")

    subprocess_calls: list[list[str]] = []

    def fake_subprocess_run(cmd, **kwargs):
        subprocess_calls.append(list(cmd))
        result = MagicMock()
        result.returncode = 0
        return result

    monkeypatch.setattr(ha_design, "load_plan", lambda: (plan, plan_path, tmp_path))
    monkeypatch.setattr(ha_design, "save_plan", lambda p, pp: None)
    monkeypatch.setattr(ha_design, "transition", lambda p, s, completed_step=None: None)
    monkeypatch.setattr(ha_design, "assert_state", lambda p, states, cmd: None)
    # LESSON ref 검증 skip
    monkeypatch.setattr(ha_design, "extract_known_lessons", lambda path: set())
    monkeypatch.setattr(ha_design, "find_unknown_lesson_references", lambda text, known: [])
    monkeypatch.setattr(ha_design, "compute_skeleton_hash", lambda path: "abc123")

    import subprocess as sp_mod
    monkeypatch.setattr(sp_mod, "run", fake_subprocess_run)

    args = SimpleNamespace(
        skeleton_path=str(skeleton_path),
        allow_unknown_lessons=True,
        locked_sections=["requirements", "user_journey"],
        ai_drafted_sections=[],
        ai_draft=False,
    )

    rc = ha_design.cmd_commit(args)
    assert rc == 0

    # ha-log subprocess 호출됐는지 확인
    ha_log_calls = [c for c in subprocess_calls if "ha-log" in " ".join(c)]
    assert len(ha_log_calls) >= 1, f"ha-log not called. all calls: {subprocess_calls}"
    joined = " ".join(ha_log_calls[0])
    assert "append" in joined
    assert "--category" in joined
    assert "change" in joined
    assert "/ha-design commit" in joined


# ---------------------------------------------------------------------------
# T2: ha-build done 시 append, skipped 는 append 안 함
# ---------------------------------------------------------------------------

def test_ha_build_done_appends_worklog_skipped_does_not(
    ha_build, tmp_path: Path, monkeypatch
) -> None:
    """ha-build complete --status done 시 ha-log subprocess 호출.
    --status skipped 는 호출 안 함.
    """
    plan = _make_plan_build()
    plan_path = tmp_path / "docs" / "harness-plan.md"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("", encoding="utf-8")

    tasks_path = tmp_path / "docs" / "tasks.md"
    tasks_path.write_text(_TASKS_ALL_DONE, encoding="utf-8")

    subprocess_calls: list[list[str]] = []

    def fake_subprocess_run(cmd, **kwargs):
        subprocess_calls.append(list(cmd) if not isinstance(cmd, str) else [cmd])
        result = MagicMock()
        result.returncode = 0
        result.stdout = "1 passed"
        result.stderr = ""
        return result

    monkeypatch.setattr(ha_build, "load_plan", lambda: (plan, plan_path, tmp_path))
    monkeypatch.setattr(ha_build, "save_plan", lambda p, pp: None)
    monkeypatch.setattr(ha_build, "transition", lambda p, s, completed_step=None: None)
    monkeypatch.setattr(ha_build, "assert_state", lambda p, states, cmd: None)
    monkeypatch.setattr(ha_build, "validate_task_id", lambda tid: None)
    monkeypatch.setattr(ha_build, "_run_toolchain_gate", lambda project, plan: [])
    monkeypatch.setattr(ha_build, "_run_security_gate", lambda project, plan: [])

    import subprocess as sp_mod
    monkeypatch.setattr(sp_mod, "run", fake_subprocess_run)

    # -- done 케이스
    subprocess_calls.clear()
    args_done = SimpleNamespace(
        task="T-001",
        status="done",
        reason="",
        skip_toolchain=True,
        skip_security=True,
        skip_frozen_gate=False,
    )
    rc = ha_build.cmd_complete(args_done)
    assert rc == 0
    ha_log_done_calls = [c for c in subprocess_calls if "ha-log" in " ".join(c)]
    assert len(ha_log_done_calls) >= 1, f"ha-log not called for done. calls: {subprocess_calls}"
    assert "T-001" in " ".join(ha_log_done_calls[0])

    # -- skipped 케이스
    subprocess_calls.clear()
    tasks_path.write_text(_TASKS_ALL_DONE, encoding="utf-8")
    args_skip = SimpleNamespace(
        task="T-001",
        status="skipped",
        reason="",
        skip_toolchain=True,
        skip_security=True,
        skip_frozen_gate=False,
    )
    rc2 = ha_build.cmd_complete(args_skip)
    assert rc2 == 0
    ha_log_skip_calls = [c for c in subprocess_calls if "ha-log" in " ".join(c)]
    assert len(ha_log_skip_calls) == 0, f"ha-log should NOT be called for skipped. calls: {subprocess_calls}"


# ---------------------------------------------------------------------------
# T3: worklog append 실패해도 commit 자체는 통과
# ---------------------------------------------------------------------------

def test_worklog_append_failure_does_not_block_commit(
    ha_design, tmp_path: Path, monkeypatch
) -> None:
    """subprocess.run 이 OSError 를 던져도 ha-design commit 은 rc=0 으로 완료."""
    plan = _make_plan_design()
    plan_path = tmp_path / "docs" / "harness-plan.md"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("", encoding="utf-8")

    skeleton_path = tmp_path / "docs" / "skeleton.md"
    skeleton_path.write_text("# skeleton\n", encoding="utf-8")

    def raise_oserror(cmd, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(ha_design, "load_plan", lambda: (plan, plan_path, tmp_path))
    monkeypatch.setattr(ha_design, "save_plan", lambda p, pp: None)
    monkeypatch.setattr(ha_design, "transition", lambda p, s, completed_step=None: None)
    monkeypatch.setattr(ha_design, "assert_state", lambda p, states, cmd: None)
    monkeypatch.setattr(ha_design, "extract_known_lessons", lambda path: set())
    monkeypatch.setattr(ha_design, "find_unknown_lesson_references", lambda text, known: [])
    monkeypatch.setattr(ha_design, "compute_skeleton_hash", lambda path: "abc123")

    import subprocess as sp_mod
    monkeypatch.setattr(sp_mod, "run", raise_oserror)

    args = SimpleNamespace(
        skeleton_path=str(skeleton_path),
        allow_unknown_lessons=True,
        locked_sections=["requirements"],
        ai_drafted_sections=[],
        ai_draft=False,
    )

    rc = ha_design.cmd_commit(args)
    # worklog 실패에도 commit 자체는 성공
    assert rc == 0
