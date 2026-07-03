"""E2E: verify FAIL 자동회수 루프 통합 검증.

단계:
  1. ha-verify FAIL + rework-tasks T-003 → plan=building, tasks T-003=needs_rebuild
  2. pipeline_advisor.advise(plan) → action=build, args=--resume, reason contains T-003
  3. select_ready_tasks(tasks) → T-003(needs_rebuild) 가 pending 보다 먼저 반환
결론: 무전이 3회 정지 없이 rework 루프 회귀 성공
"""

from __future__ import annotations

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType

import pytest

from src.orchestrator.pipeline_advisor import advise
from src.orchestrator.plan_manager import PlanManager, SkeletonSpec

REPO_ROOT = Path(__file__).resolve().parents[3]

_TASKS = (
    "# Tasks\n"
    "| ID    | Agent         | Depends On | Description | Status     |\n"
    "|-------|---------------|------------|-------------|------------|\n"
    "| T-001 | backend_coder |            | 기능 A      | 대기       |\n"
    "| T-002 | backend_coder |            | 기능 B      | 대기       |\n"
    "| T-003 | backend_coder |            | 기능 C      | done       |\n"
)


@pytest.fixture(scope="module")
def ha_build() -> ModuleType:
    loader = SourceFileLoader("_ha_build_e2e", str(REPO_ROOT / "skills" / "ha-build" / "run.py"))
    spec = importlib.util.spec_from_loader("_ha_build_e2e", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_ha_build_e2e"] = mod
    loader.exec_module(mod)
    return mod


def test_rework_loop_end_to_end(tmp_path: Path, ha_build: ModuleType) -> None:
    """verify FAIL → building 회귀 → needs_rebuild 재구현 루프가 무전이 정지 없이 작동."""
    pm = PlanManager()
    plan = pm.create(
        project_name="test",
        project_type="python-cli",
        scale="small",
        user_description_original="",
        profiles=[],
        skeleton_sections=SkeletonSpec((), (), ("interface.cli",)),
        pipeline_steps=["build"],
    )
    for state in ("designed", "planned", "building", "built"):
        pm.transition(plan, state)

    tasks_path = tmp_path / "docs" / "tasks.md"
    tasks_path.parent.mkdir(parents=True)
    tasks_path.write_text(_TASKS, encoding="utf-8")

    # ── 단계 1: ha-verify record --passed false --rework-tasks T-003 ──────
    pm.record_verify(plan, step="ha-verify", passed=False, summary="pytest fail [rework: T-003]")
    pm.regress(plan, "building")
    pm.mark_for_rebuild(tasks_path, ["T-003"])

    assert "needs_rebuild" in tasks_path.read_text(encoding="utf-8")  # T-001
    assert plan.pipeline.current_step == "building"

    # ── 단계 2: pipeline_advisor.advise(plan) ─────────────────────────────
    advice = advise(plan)
    assert advice.action == "build" and advice.args == "--resume"  # T-002(action/args)
    assert "T-003" in advice.reason                                # T-003(reason)

    # ── 단계 3: select_ready_tasks(tasks) ────────────────────────────────
    tasks = ha_build._parse_tasks(tasks_path.read_text(encoding="utf-8"))
    ready = ha_build.select_ready_tasks(tasks)
    assert "T-003" in ready                                        # T-002(needs_rebuild 우선)
    assert ready.index("T-003") < ready.index("T-001")
