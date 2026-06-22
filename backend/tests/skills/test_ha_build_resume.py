"""ha-build --resume (A5 / 패턴2 — `[X]` resume) 회귀 테스트.

`--task` 를 명시하지 않아도 다음 ready 태스크(대기/in-progress + depends_on done)를
자동 선택한다. 부분복구(#7)·iteration 후 "다음 뭘 빌드?" 를 tasks.md 수동 독해 없이 해결.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def ha_build() -> ModuleType:
    loader = SourceFileLoader(
        "ha_build_run_resume", str(REPO_ROOT / "skills" / "ha-build" / "run.py")
    )
    spec = importlib.util.spec_from_loader("ha_build_run_resume", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_build_run_resume"] = mod
    loader.exec_module(mod)
    return mod


def _task(
    agent: str = "backend_coder", deps: list[str] | None = None, status: str = "대기"
) -> dict:
    return {"agent": agent, "depends_on": deps or [], "description": "x", "status": status}


# ---------------------------------------------------------------------------
# select_ready_tasks (pure)
# ---------------------------------------------------------------------------


class TestSelectReadyTasks:
    def test_pending_with_deps_done_is_ready(self, ha_build) -> None:
        tasks = {
            "T-001": _task(status="done"),
            "T-002": _task(deps=["T-001"], status="대기"),
        }
        assert ha_build.select_ready_tasks(tasks) == ["T-002"]

    def test_pending_with_unmet_deps_excluded(self, ha_build) -> None:
        tasks = {
            "T-001": _task(status="대기"),
            "T-002": _task(deps=["T-001"], status="대기"),
        }
        # only T-001 ready (no deps); T-002 blocked
        assert ha_build.select_ready_tasks(tasks) == ["T-001"]

    def test_done_tasks_excluded(self, ha_build) -> None:
        tasks = {"T-001": _task(status="done"), "T-002": _task(status="완료")}
        assert ha_build.select_ready_tasks(tasks) == []

    def test_inprogress_ordered_before_pending(self, ha_build) -> None:
        tasks = {
            "T-001": _task(status="대기"),
            "T-002": _task(status="in-progress"),
        }
        # in-progress (resume partial work) comes first
        assert ha_build.select_ready_tasks(tasks) == ["T-002", "T-001"]

    def test_ordered_by_task_id_within_group(self, ha_build) -> None:
        tasks = {
            "T-003": _task(status="대기"),
            "T-001": _task(status="대기"),
            "T-002": _task(status="대기"),
        }
        assert ha_build.select_ready_tasks(tasks) == ["T-001", "T-002", "T-003"]

    def test_skipped_and_blocked_excluded(self, ha_build) -> None:
        tasks = {
            "T-001": _task(status="skipped"),
            "T-002": _task(status="blocked"),
            "T-003": _task(status="대기"),
        }
        assert ha_build.select_ready_tasks(tasks) == ["T-003"]


# ---------------------------------------------------------------------------
# cmd_prepare --resume integration
# ---------------------------------------------------------------------------


def _plan(step: str = "planned"):
    return SimpleNamespace(
        pipeline=SimpleNamespace(
            current_step=step,
            completed_steps=(),
            skipped_steps=(),
            steps=("planned", "building", "built"),
            gstack_mode="manual",
        ),
        profiles=[],
        skeleton_hash=None,
        frozen_status="frozen",
    )


def _tasks_md(t001_status: str, t002_status: str) -> str:
    return (
        "### Phase 1 — MVP\n"
        "| ID    | Agent         | Depends On | Description | Status     |\n"
        "|-------|---------------|------------|-------------|------------|\n"
        f"| T-001 | backend_coder | -          | 모델        | {t001_status:<10} |\n"
        f"| T-002 | backend_coder | T-001      | API         | {t002_status:<10} |\n"
        "\n"
        "### T-002 — API\n"
        "- **생성/수정 파일**:\n"
        "  - NEW `src/api.py`\n"
    )


def _patch(ha_build, monkeypatch, plan, tmp_path: Path) -> Path:
    plan_path = tmp_path / "docs" / "harness-plan.md"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(ha_build, "load_plan", lambda: (plan, plan_path, tmp_path))
    monkeypatch.setattr(ha_build, "assert_state", lambda *a, **k: None)
    monkeypatch.setattr(ha_build, "get_active_profiles", lambda p, pr: [])
    return plan_path


def _resume_args():
    return SimpleNamespace(
        task=None, resume=True, skip_frozen_gate=False, accept_skeleton_drift=False
    )


def test_resume_selects_next_ready_task(ha_build, tmp_path, monkeypatch, capsys) -> None:
    """T-001 done → --resume 가 T-002 자동 선택."""
    plan = _plan()
    plan_path = _patch(ha_build, monkeypatch, plan, tmp_path)
    (plan_path.parent / "tasks.md").write_text(_tasks_md("done", "대기"), encoding="utf-8")

    rc = ha_build.cmd_prepare(_resume_args())
    cap = capsys.readouterr()

    assert rc == 0
    out = json.loads(cap.out)
    assert [t["id"] for t in out["tasks"]] == ["T-002"]
    assert "자동 선택: T-002" in cap.err


def test_resume_nothing_ready_exits_zero_without_state_change(
    ha_build, tmp_path, monkeypatch, capsys
) -> None:
    """전부 done → exit 0, 빌드 진입(상태 회귀) 없음."""
    plan = _plan(step="reviewed")
    plan_path = _patch(ha_build, monkeypatch, plan, tmp_path)
    (plan_path.parent / "tasks.md").write_text(_tasks_md("done", "done"), encoding="utf-8")

    rc = ha_build.cmd_prepare(_resume_args())
    cap = capsys.readouterr()

    assert rc == 0
    assert "ready 태스크 없음" in cap.err
    # 상태 회귀 안 됨 — _enter_build_state 호출 전에 종료
    assert plan.pipeline.current_step == "reviewed"


def test_neither_task_nor_resume_fails(ha_build, tmp_path, monkeypatch, capsys) -> None:
    """--task 도 --resume 도 없으면 FAIL (exit 2) + 안내."""
    plan = _plan()
    plan_path = _patch(ha_build, monkeypatch, plan, tmp_path)
    (plan_path.parent / "tasks.md").write_text(_tasks_md("대기", "대기"), encoding="utf-8")

    rc = ha_build.cmd_prepare(
        SimpleNamespace(
            task=None, resume=False, skip_frozen_gate=False, accept_skeleton_drift=False
        )
    )
    cap = capsys.readouterr()

    assert rc == 2
    assert "--resume" in cap.err
