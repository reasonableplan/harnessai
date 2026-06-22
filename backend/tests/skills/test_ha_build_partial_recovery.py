"""ha-build 부분 완료 복구 (issue #7) 회귀 테스트.

서브에이전트가 태스크 도중 죽으면 status 가 '대기' 로 남고 부분 산출물이 추적되지
않는다. prepare 가 (a) 착수 시 대기→in-progress 마킹, (b) 이미 in-progress 면 재진입
으로 감지하고 선언 산출 파일 존재 여부를 보고해야 한다.
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


def _load_ha_build() -> ModuleType:
    loader = SourceFileLoader(
        "ha_build_run_partial", str(REPO_ROOT / "skills" / "ha-build" / "run.py")
    )
    spec = importlib.util.spec_from_loader("ha_build_run_partial", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_build_run_partial"] = mod
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ha_build() -> ModuleType:
    return _load_ha_build()


def _plan():
    return SimpleNamespace(
        pipeline=SimpleNamespace(
            current_step="planned",
            completed_steps=(),
            skipped_steps=(),
            steps=("planned", "building", "built"),
            gstack_mode="manual",
        ),
        profiles=[],
        skeleton_hash=None,
        frozen_status="frozen",
    )


def _tasks_md(status: str) -> str:
    return (
        "### Phase 1 — MVP\n"
        "| ID    | Agent         | Depends On | Description | Status     |\n"
        "|-------|---------------|------------|-------------|------------|\n"
        f"| T-001 | backend_coder | -          | 모델 구현   | {status:<10} |\n"
        "\n"
        "### T-001 — 모델 (users)\n"
        "- **생성/수정 파일**:\n"
        "  - NEW `src/models/user.py`\n"
        "  - NEW `tests/test_user.py`\n"
        "- **skeleton 참조**: `persistence.users`\n"
    )


def _patch(ha_build, monkeypatch, plan, tmp_path: Path) -> Path:
    plan_path = tmp_path / "docs" / "harness-plan.md"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(ha_build, "load_plan", lambda: (plan, plan_path, tmp_path))
    monkeypatch.setattr(ha_build, "assert_state", lambda *a, **k: None)
    monkeypatch.setattr(ha_build, "get_active_profiles", lambda p, pr: [])
    return plan_path


def _args():
    return SimpleNamespace(task="T-001", skip_frozen_gate=False, accept_skeleton_drift=False)


def _run(ha_build, capsys):
    rc = ha_build.cmd_prepare(_args())
    cap = capsys.readouterr()
    out = json.loads(cap.out) if cap.out.strip() else None
    return rc, out, cap.err


def test_prepare_marks_pending_task_in_progress(ha_build, tmp_path, monkeypatch, capsys) -> None:
    """대기 태스크에 prepare → tasks.md 가 in-progress 로 마킹 (착수 선언)."""
    plan = _plan()
    plan_path = _patch(ha_build, monkeypatch, plan, tmp_path)
    tasks_path = plan_path.parent / "tasks.md"
    tasks_path.write_text(_tasks_md("대기"), encoding="utf-8")

    rc, out, _err = _run(ha_build, capsys)

    assert rc == 0
    marked = ha_build._parse_tasks(tasks_path.read_text(encoding="utf-8"))
    assert marked["T-001"]["status"] == "in-progress", "대기→in-progress 마킹 안 됨"
    task = out["tasks"][0]
    assert task["reentry"] is False
    assert task["status"] == "in-progress"


def test_prepare_detects_reentry_with_partial_output(
    ha_build, tmp_path, monkeypatch, capsys
) -> None:
    """이미 in-progress + 선언 파일 일부 존재 → 재진입 감지 + 부분 산출 보고."""
    plan = _plan()
    plan_path = _patch(ha_build, monkeypatch, plan, tmp_path)
    tasks_path = plan_path.parent / "tasks.md"
    tasks_path.write_text(_tasks_md("in-progress"), encoding="utf-8")
    # 부분 산출물: 선언된 2개 중 1개만 생성된 채 죽은 상황.
    (tmp_path / "src" / "models").mkdir(parents=True)
    (tmp_path / "src" / "models" / "user.py").write_text("# partial\n", encoding="utf-8")

    rc, out, err = _run(ha_build, capsys)

    assert rc == 0
    task = out["tasks"][0]
    assert task["reentry"] is True
    assert "src/models/user.py" in task["existing_files"]
    assert "tests/test_user.py" not in task["existing_files"]
    assert set(task["declared_files"]) == {"src/models/user.py", "tests/test_user.py"}
    assert "[WARN]" in err and "재진입" in err


def test_prepare_reentry_is_idempotent(ha_build, tmp_path, monkeypatch, capsys) -> None:
    """in-progress 태스크 재-prepare 는 상태를 바꾸지 않는다 (멱등, 에러 없음)."""
    plan = _plan()
    plan_path = _patch(ha_build, monkeypatch, plan, tmp_path)
    tasks_path = plan_path.parent / "tasks.md"
    tasks_path.write_text(_tasks_md("in-progress"), encoding="utf-8")

    rc, out, _err = _run(ha_build, capsys)

    assert rc == 0
    assert "| in-progress |" in tasks_path.read_text(encoding="utf-8")
    assert out["tasks"][0]["reentry"] is True
