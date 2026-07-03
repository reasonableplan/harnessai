"""select_ready_tasks — needs_rebuild 큐 편입 회귀 테스트 (T-002).

needs_rebuild 상태 태스크가 in-progress/대기보다 먼저 선택되는지 검증한다.
의존성 미충족 시 제외, 비어있는 큐 케이스도 포함.
"""

from __future__ import annotations

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def ha_build() -> ModuleType:
    loader = SourceFileLoader(
        "ha_build_run_select", str(REPO_ROOT / "skills" / "ha-build" / "run.py")
    )
    spec = importlib.util.spec_from_loader("ha_build_run_select", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_build_run_select"] = mod
    loader.exec_module(mod)
    return mod


def _task(
    agent: str = "backend_coder",
    deps: list[str] | None = None,
    status: str = "대기",
) -> dict:
    return {"agent": agent, "depends_on": deps or [], "description": "x", "status": status}


class TestSelectReadyTasksNeedsRebuild:
    def test_needs_rebuild_before_inprogress(self, ha_build) -> None:
        """needs_rebuild 태스크가 in-progress보다 앞에 나온다."""
        tasks = {
            "T-001": _task(status="in-progress"),
            "T-002": _task(status="needs_rebuild"),
        }
        result = ha_build.select_ready_tasks(tasks)
        assert result == ["T-002", "T-001"]

    def test_needs_rebuild_and_pending_mixed_order(self, ha_build) -> None:
        """needs_rebuild 그룹이 pending 그룹보다 앞에, 각 그룹 내 tid 오름차순."""
        tasks = {
            "T-001": _task(status="대기"),
            "T-002": _task(status="pending"),
            "T-003": _task(status="needs_rebuild"),
            "T-004": _task(status="needs_rebuild"),
        }
        result = ha_build.select_ready_tasks(tasks)
        assert result == ["T-003", "T-004", "T-001", "T-002"]

    def test_needs_rebuild_with_unmet_deps_excluded(self, ha_build) -> None:
        """의존성이 충족되지 않은 needs_rebuild 태스크는 제외된다."""
        tasks = {
            "T-001": _task(status="대기"),
            "T-002": _task(deps=["T-001"], status="needs_rebuild"),  # T-001 미완료 → 제외
            "T-003": _task(status="needs_rebuild"),  # 의존성 없음 → 포함
        }
        result = ha_build.select_ready_tasks(tasks)
        assert result == ["T-003", "T-001"]

    def test_empty_queue_no_needs_rebuild(self, ha_build) -> None:
        """done/blocked/skipped 만 있고 needs_rebuild 도 없으면 빈 리스트."""
        tasks = {
            "T-001": _task(status="done"),
            "T-002": _task(status="blocked"),
            "T-003": _task(status="skipped"),
        }
        result = ha_build.select_ready_tasks(tasks)
        assert result == []
