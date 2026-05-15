"""B5 + B1 회귀 테스트 — ha-build state machine.

B5: skipped 마킹 → built 전이 / blocked 는 building 유지
B1: tasks.md 미매칭 T-ID → exit 1 + plan 갱신 없음
"""

from __future__ import annotations

import importlib.util
import json
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from subprocess import CompletedProcess
from types import ModuleType, SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_ha_build() -> ModuleType:
    loader = SourceFileLoader("ha_build_run_sm", str(REPO_ROOT / "skills" / "ha-build" / "run.py"))
    spec = importlib.util.spec_from_loader("ha_build_run_sm", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_build_run_sm"] = mod
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ha_build() -> ModuleType:
    return _load_ha_build()


# ---------------------------------------------------------------------------
# 공통 픽스처 헬퍼
# ---------------------------------------------------------------------------

_TASKS_TABLE_HEADER = (
    "| ID    | Agent         | Depends On | Description | Status     |\n"
    "|-------|---------------|------------|-------------|------------|\n"
)


def _tasks_md(rows: list[tuple[str, str]]) -> str:
    """(T-ID, status) 리스트로 tasks.md 마크다운 테이블 생성."""
    lines = [_TASKS_TABLE_HEADER]
    for tid, status in rows:
        lines.append(f"| {tid:<5} | backend_coder | -          | desc        | {status:<10} |\n")
    return "".join(lines)


def _make_pipeline(current_step: str, completed: tuple[str, ...] = ()):
    return SimpleNamespace(
        current_step=current_step,
        completed_steps=completed,
        skipped_steps=(),
        steps=("planned", "building", "built"),
        gstack_mode="manual",
    )


def _make_plan(current_step: str, completed: tuple[str, ...] = ()):
    return SimpleNamespace(
        pipeline=_make_pipeline(current_step, completed),
        profiles=[SimpleNamespace(id="fastapi", path=".")],
        skeleton_hash=None,
        frozen_status="frozen",  # v0.10.0 HITL gate: 기존 테스트는 게이트 통과 상태로 고정
    )


def _args(task: str, status: str, reason: str = "", skip_toolchain: bool = False, skip_security: bool = False):
    return SimpleNamespace(
        task=task,
        status=status,
        reason=reason,
        skip_toolchain=skip_toolchain,
        skip_security=skip_security,
        skip_frozen_gate=False,  # v0.10.0: frozen_status="frozen" 이므로 게이트 통과
    )


def _patch_load_plan(ha_build, monkeypatch, plan, tmp_path: Path, tasks_text: str):
    """load_plan, save_plan, validate_task_id, transition 을 패치."""
    tasks_path = tmp_path / "tasks.md"
    tasks_path.write_text(tasks_text, encoding="utf-8")
    plan_path = tmp_path / "harness-plan.md"
    plan_path.write_text("", encoding="utf-8")

    saved: list = []

    monkeypatch.setattr(ha_build, "load_plan", lambda: (plan, plan_path, tmp_path))
    monkeypatch.setattr(ha_build, "save_plan", lambda p, pp: saved.append(p))
    monkeypatch.setattr(ha_build, "validate_task_id", lambda tid: None)

    transitions: list[tuple] = []

    def _fake_transition(p, target, completed_step=None):
        transitions.append((target, completed_step))
        p.pipeline = SimpleNamespace(
            current_step=target,
            completed_steps=(*p.pipeline.completed_steps, completed_step) if completed_step else p.pipeline.completed_steps,
            skipped_steps=p.pipeline.skipped_steps,
            steps=p.pipeline.steps,
            gstack_mode=p.pipeline.gstack_mode,
        )

    monkeypatch.setattr(ha_build, "transition", _fake_transition)

    return tasks_path, saved, transitions


# ---------------------------------------------------------------------------
# B5 — skipped 마킹 테스트
# ---------------------------------------------------------------------------

def test_skipped_status_updates_tasks_md(ha_build, tmp_path, monkeypatch, capsys) -> None:
    """skipped 마킹 → tasks.md 상태 컬럼이 'skipped' 로 바뀐다."""
    plan = _make_plan("building")
    tasks_text = _tasks_md([("T-001", "done      "), ("T-002", "대기      ")])
    tasks_path, saved, transitions = _patch_load_plan(ha_build, monkeypatch, plan, tmp_path, tasks_text)

    rc = ha_build.cmd_complete(_args("T-002", "skipped"))

    assert rc == 0
    content = tasks_path.read_text(encoding="utf-8")
    assert "skipped" in content


def test_skipped_does_not_run_toolchain_gate(ha_build, tmp_path, monkeypatch) -> None:
    """skipped 마킹 시 toolchain gate 호출 안 됨."""
    plan = _make_plan("building")
    tasks_text = _tasks_md([("T-001", "done      "), ("T-002", "대기      ")])
    _patch_load_plan(ha_build, monkeypatch, plan, tmp_path, tasks_text)

    gate_called: list[bool] = []
    monkeypatch.setattr(ha_build, "_run_toolchain_gate", lambda *a, **kw: gate_called.append(True) or [])
    monkeypatch.setattr(ha_build, "_run_security_gate", lambda *a, **kw: [])

    rc = ha_build.cmd_complete(_args("T-002", "skipped"))

    assert rc == 0
    assert not gate_called, "skipped 는 toolchain gate 를 호출하면 안 됨"


def test_skipped_does_not_run_security_gate(ha_build, tmp_path, monkeypatch) -> None:
    """skipped 마킹 시 security gate 호출 안 됨."""
    plan = _make_plan("building")
    tasks_text = _tasks_md([("T-001", "done      "), ("T-002", "대기      ")])
    _patch_load_plan(ha_build, monkeypatch, plan, tmp_path, tasks_text)

    sec_called: list[bool] = []
    monkeypatch.setattr(ha_build, "_run_toolchain_gate", lambda *a, **kw: [])
    monkeypatch.setattr(ha_build, "_run_security_gate", lambda *a, **kw: sec_called.append(True) or [])

    rc = ha_build.cmd_complete(_args("T-002", "skipped"))

    assert rc == 0
    assert not sec_called, "skipped 는 security gate 를 호출하면 안 됨"


def test_phase1_done_phase2_skipped_transitions_to_built(ha_build, tmp_path, monkeypatch) -> None:
    """Phase 1 done + Phase 2 skipped → current_step == 'built'."""
    plan = _make_plan("building")
    tasks_text = _tasks_md([("T-001", "done      "), ("T-102", "대기      ")])
    _, saved, transitions = _patch_load_plan(ha_build, monkeypatch, plan, tmp_path, tasks_text)

    rc = ha_build.cmd_complete(_args("T-102", "skipped"))

    assert rc == 0
    assert any(t[0] == "built" for t in transitions), f"built 전이 없음: {transitions}"


def test_all_done_transitions_to_built(ha_build, tmp_path, monkeypatch) -> None:
    """모든 태스크 done → built 전이."""
    plan = _make_plan("building")
    tasks_text = _tasks_md([("T-001", "done      "), ("T-002", "대기      ")])
    _, saved, transitions = _patch_load_plan(ha_build, monkeypatch, plan, tmp_path, tasks_text)

    rc = ha_build.cmd_complete(_args("T-002", "done", skip_toolchain=True, skip_security=True))

    assert rc == 0
    assert any(t[0] == "built" for t in transitions), f"built 전이 없음: {transitions}"


def test_blocked_keeps_building(ha_build, tmp_path, monkeypatch) -> None:
    """blocked 마킹 → building 유지 (built 전이 없음). 회귀 방지."""
    plan = _make_plan("building")
    tasks_text = _tasks_md([("T-001", "done      "), ("T-002", "대기      ")])
    _, saved, transitions = _patch_load_plan(ha_build, monkeypatch, plan, tmp_path, tasks_text)

    rc = ha_build.cmd_complete(_args("T-002", "blocked"))

    assert rc == 0
    assert not any(t[0] == "built" for t in transitions), "blocked 는 built 전이하면 안 됨"


def test_output_json_uses_all_tasks_resolved_key(ha_build, tmp_path, monkeypatch, capsys) -> None:
    """출력 JSON 에 all_tasks_resolved 키 존재 확인."""
    plan = _make_plan("building")
    tasks_text = _tasks_md([("T-001", "done      ")])
    _patch_load_plan(ha_build, monkeypatch, plan, tmp_path, tasks_text)

    rc = ha_build.cmd_complete(_args("T-001", "skipped", skip_toolchain=True, skip_security=True))

    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert "all_tasks_resolved" in data
    assert "all_tasks_done" not in data, "구 키 all_tasks_done 은 제거됨"


# ---------------------------------------------------------------------------
# B1 — atomic 보장 테스트
# ---------------------------------------------------------------------------

def test_missing_task_id_returns_exit1(ha_build, tmp_path, monkeypatch, capsys) -> None:
    """tasks.md 에 없는 T-ID → exit 1, plan 갱신 안 됨."""
    plan = _make_plan("building")
    tasks_text = _tasks_md([("T-001", "done      ")])
    _, saved, transitions = _patch_load_plan(ha_build, monkeypatch, plan, tmp_path, tasks_text)

    rc = ha_build.cmd_complete(_args("T-999", "done", skip_toolchain=True, skip_security=True))

    assert rc == 1, f"exit code 는 1 이어야 함, got {rc}"


def test_missing_task_id_no_plan_update(ha_build, tmp_path, monkeypatch, capsys) -> None:
    """tasks.md 에 없는 T-ID → save_plan 호출 안 됨 (plan 갱신 없음)."""
    plan = _make_plan("building")
    tasks_text = _tasks_md([("T-001", "done      ")])
    _, saved, transitions = _patch_load_plan(ha_build, monkeypatch, plan, tmp_path, tasks_text)

    ha_build.cmd_complete(_args("T-999", "done", skip_toolchain=True, skip_security=True))

    assert not saved, "plan 이 갱신되면 안 됨 — tasks.md 쓰기 실패 시 atomic 깨짐"
    assert not transitions, "transition 이 발생하면 안 됨"


def test_missing_task_id_error_message_contains_tid(ha_build, tmp_path, monkeypatch, capsys) -> None:
    """에러 메시지에 T-ID 포함 확인."""
    plan = _make_plan("building")
    tasks_text = _tasks_md([("T-001", "done      ")])
    _patch_load_plan(ha_build, monkeypatch, plan, tmp_path, tasks_text)

    ha_build.cmd_complete(_args("T-999", "done", skip_toolchain=True, skip_security=True))

    err = capsys.readouterr().err
    assert "T-999" in err, f"에러 메시지에 T-ID 없음: {err!r}"


def test_missing_task_id_tasks_md_unchanged(ha_build, tmp_path, monkeypatch) -> None:
    """tasks.md 에 없는 T-ID → tasks.md 파일 내용 변경 없음."""
    plan = _make_plan("building")
    original = _tasks_md([("T-001", "done      ")])
    tasks_path, _, _ = _patch_load_plan(ha_build, monkeypatch, plan, tmp_path, original)

    ha_build.cmd_complete(_args("T-999", "done", skip_toolchain=True, skip_security=True))

    assert tasks_path.read_text(encoding="utf-8") == original


def test_write_failure_returns_exit1(ha_build, tmp_path, monkeypatch) -> None:
    """tasks.md 쓰기 OSError → exit 1, plan 갱신 안 됨."""
    plan = _make_plan("building")
    tasks_text = _tasks_md([("T-001", "대기      ")])
    _, saved, transitions = _patch_load_plan(ha_build, monkeypatch, plan, tmp_path, tasks_text)

    # write_text 를 OSError 로 패치
    original_write = Path.write_text

    def _failing_write(self, *a, **kw):
        if self.name == "tasks.md":
            raise OSError("disk full")
        return original_write(self, *a, **kw)

    monkeypatch.setattr(Path, "write_text", _failing_write)

    rc = ha_build.cmd_complete(_args("T-001", "done", skip_toolchain=True, skip_security=True))

    assert rc == 1
    assert not saved, "OSError 시 plan 갱신 없어야 함"
