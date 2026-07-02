"""ha-run 스킬 CLI 테스트 — `next` 서브커맨드의 JSON 계약.

결정 로직 자체는 backend/tests/orchestrator/test_pipeline_advisor.py 가 전수 커버.
여기는 배선(플랜 탐색/로드 → advise → JSON 출력)만 검증한다.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.orchestrator.plan_manager import PlanManager, SkeletonSpec


def _write_plan(tmp_path: Path, step: str) -> None:
    pm = PlanManager()
    plan = pm.create(
        project_name="t",
        project_type="python-cli",
        scale="small",
        user_description_original="",
        profiles=[],
        skeleton_sections=SkeletonSpec((), (), ()),
        pipeline_steps=["init"],
    )
    order = ["designed", "planned", "building", "built", "verified", "reviewed", "shipped"]
    if step != "init":
        for s in order[: order.index(step) + 1]:
            pm.transition(plan, s)
    plan.frozen_status = "frozen"
    plan.frozen_at = "2026-07-02T00:00:00+00:00"
    plan.locked_sections = ["requirements"]
    pm.save(plan, tmp_path / "docs" / "harness-plan.md")


def test_next_without_plan_returns_init(ha_run_module, tmp_path: Path, capsys) -> None:
    rc = ha_run_module.cmd_next(argparse.Namespace(project=str(tmp_path)))
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["action"] == "init"
    assert out["mode"] == "hitl"
    assert out["current_step"] is None


def test_next_planned_returns_build_resume(ha_run_module, tmp_path: Path, capsys) -> None:
    _write_plan(tmp_path, "planned")
    rc = ha_run_module.cmd_next(argparse.Namespace(project=str(tmp_path)))
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["action"] == "build"
    assert out["args"] == "--resume"
    assert out["current_step"] == "planned"


def test_next_schema_error_exits_3(ha_run_module, tmp_path: Path, capsys) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "harness-plan.md").write_text(
        "---\nproject_name: t\npipeline: {current_step: bogus}\n---\n",
        encoding="utf-8",
    )
    rc = ha_run_module.cmd_next(argparse.Namespace(project=str(tmp_path)))
    assert rc == 3
    assert "스키마 오류" in capsys.readouterr().err
