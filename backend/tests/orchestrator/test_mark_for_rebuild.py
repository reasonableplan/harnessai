"""cmd_record → mark_for_rebuild 통합 테스트.

ha-verify record (passed=false, rework_tasks) 가 tasks.md 의 done 태스크를
needs_rebuild 로 전이하는지 검증.

4가지 시나리오:
  1. done 태스크 → needs_rebuild 전이
  2. pending/in-progress 상태 → unchanged
  3. T-ID CSV 파싱 "T-001,T-002" → 두 항목 모두 처리
  4. 존재 안 하는 T-ID → silently ignored, exit 0
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
    """ha-verify/run.py 를 모듈로 로드 (mark_for_rebuild 통합 테스트용)."""
    loader = SourceFileLoader("ha_verify_mark_rebuild", str(HA_VERIFY_RUN))
    spec = importlib.util.spec_from_loader("ha_verify_mark_rebuild", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_verify_mark_rebuild"] = mod
    loader.exec_module(mod)
    return mod


def _make_tasks_md(tmp_path: Path, rows: list[tuple[str, str]]) -> Path:
    """tasks.md 픽스처 생성. rows: [(task_id, status), ...]."""
    lines = [
        "# Tasks\n",
        "\n",
        "| ID    | Agent          | Depends | Description       | Status     |\n",
        "|-------|----------------|---------|-------------------|------------|\n",
    ]
    for tid, status in rows:
        lines.append(
            f"| {tid:<5} | backend_coder  |         | some work         | {status:<10} |\n"
        )
    path = tmp_path / "tasks.md"
    path.write_text("".join(lines), encoding="utf-8")
    return path


def _run_record(
    ha_verify: ModuleType,
    *,
    tmp_path: Path,
    rework_tasks: str,
) -> dict:
    """cmd_record 실행 헬퍼. plan_path.parent == tmp_path 이므로 tasks.md 자동 탐색."""
    plan_path = tmp_path / "harness-plan.md"
    mock_plan = MagicMock()
    mock_plan.pipeline.current_step = "built"
    mock_plan.verify_history = []
    captured: list[str] = []

    with (
        patch.object(
            ha_verify,
            "load_plan",
            return_value=(mock_plan, plan_path, tmp_path),
        ),
        patch.object(ha_verify, "assert_state"),
        patch.object(ha_verify, "record_verify"),
        patch.object(ha_verify, "regress"),
        patch.object(ha_verify, "save_plan"),
        patch("builtins.print", side_effect=lambda d, **kw: captured.append(d)),
    ):
        args = MagicMock()
        args.passed = "false"
        args.summary = "pytest 2 failed"
        args.rework_tasks = rework_tasks
        args.no_rework = False
        args.force_continue = False
        exit_code = ha_verify.cmd_record(args)

    output = json.loads(captured[0]) if captured else {}
    return {"exit_code": exit_code, "output": output}


# ── 1: done 태스크 → needs_rebuild 전이 ─────────────────────────────


def test_record_transitions_done_task_to_needs_rebuild(
    ha_verify: ModuleType, tmp_path: Path
) -> None:
    """cmd_record passed=false + T-001(done) → tasks.md 에 needs_rebuild 반영."""
    _make_tasks_md(tmp_path, [("T-001", "done"), ("T-002", "pending")])

    result = _run_record(ha_verify, tmp_path=tmp_path, rework_tasks="T-001")

    assert result["exit_code"] == 0
    text = (tmp_path / "tasks.md").read_text(encoding="utf-8")
    assert "needs_rebuild" in text


# ── 2: pending/in-progress 상태 → unchanged ─────────────────────────


def test_record_leaves_non_done_tasks_unchanged(ha_verify: ModuleType, tmp_path: Path) -> None:
    """T-001(pending), T-002(in-progress) → needs_rebuild 없음, 상태 유지."""
    _make_tasks_md(tmp_path, [("T-001", "pending"), ("T-002", "in-progress")])

    result = _run_record(ha_verify, tmp_path=tmp_path, rework_tasks="T-001,T-002")

    assert result["exit_code"] == 0
    text = (tmp_path / "tasks.md").read_text(encoding="utf-8")
    assert "needs_rebuild" not in text
    assert "pending" in text
    assert "in-progress" in text


# ── 3: CSV T-ID 파싱 "T-001,T-002" ──────────────────────────────────


def test_record_parses_csv_rework_tasks(ha_verify: ModuleType, tmp_path: Path) -> None:
    """rework_tasks CSV "T-001,T-002" → 두 done 태스크 모두 needs_rebuild 전이."""
    _make_tasks_md(
        tmp_path,
        [("T-001", "done"), ("T-002", "done"), ("T-003", "pending")],
    )

    result = _run_record(ha_verify, tmp_path=tmp_path, rework_tasks="T-001,T-002")

    assert result["exit_code"] == 0
    assert result["output"].get("rework_tasks") == ["T-001", "T-002"]
    text = (tmp_path / "tasks.md").read_text(encoding="utf-8")
    assert text.count("needs_rebuild") == 2


# ── 4: 존재 안 하는 T-ID → silently ignored ──────────────────────────


def test_record_ignores_nonexistent_task_id(ha_verify: ModuleType, tmp_path: Path) -> None:
    """T-999 는 tasks.md 에 없음 → 무시, T-001 은 정상 전이, exit 0."""
    _make_tasks_md(tmp_path, [("T-001", "done")])

    result = _run_record(ha_verify, tmp_path=tmp_path, rework_tasks="T-001,T-999")

    assert result["exit_code"] == 0
    text = (tmp_path / "tasks.md").read_text(encoding="utf-8")
    assert "needs_rebuild" in text
