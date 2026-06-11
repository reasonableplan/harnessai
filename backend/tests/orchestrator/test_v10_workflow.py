"""HarnessAI v0.10.0 HITL gate end-to-end integration 테스트.

frozen_status 게이트의 실제 흐름을 검증:
  1. drafting plan → ha-build prepare BLOCK → ha-design freeze → ha-build prepare 통과
  2. drafting plan → ha-build prepare --skip-frozen-gate → 통과 (마이그레이션 escape hatch)

ha-build/run.py 를 subprocess 로 호출해 exit code 검증.
plan_manager 를 직접 사용해 freeze 시뮬레이션.

모든 픽스처는 tmp_path 기반 — 사용자 환경 비의존.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

from src.orchestrator.plan_manager import (
    PlanManager,
    ProfileRef,
    ScaleAxes,
    SkeletonSpec,
)

# ha-build/run.py 경로 (레포 기준)
_REPO_ROOT = Path(__file__).resolve().parents[3]
_HA_BUILD_RUN = _REPO_ROOT / "skills" / "ha-build" / "run.py"


# ── 픽스처 헬퍼 ──────────────────────────────────────────────────────────


def _create_minimal_plan(tmp_path: Path, *, frozen: bool = False) -> tuple[Path, Path]:
    """최소 plan/tasks/skeleton 생성.

    Args:
        tmp_path: pytest 임시 디렉토리.
        frozen: True 면 plan.freeze() 호출 (frozen_status='frozen').

    Returns:
        (project_root, plan_path) 튜플.
    """
    project = tmp_path / "myproject"
    docs_dir = project / "docs"
    docs_dir.mkdir(parents=True)

    pm = PlanManager()
    plan = pm.create(
        project_name="E2E 테스트 프로젝트",
        project_type="web",
        scale="small",
        user_description_original="E2E 테스트용",
        profiles=[ProfileRef(id="fastapi", path=".", status="confirmed")],
        skeleton_sections=SkeletonSpec(
            required=("requirements", "user_journey", "view.screens"),
            optional=(),
            included=("requirements", "user_journey", "view.screens"),
        ),
        pipeline_steps=["ha-init", "ha-design", "ha-plan"],
        scale_axes=ScaleAxes(),
    )
    # planned 상태로 전이 (ha-build prepare 가 planned/building 을 허용)
    pm.transition(plan, "designed", completed_step="ha-init")
    pm.transition(plan, "planned", completed_step="ha-design")

    if frozen:
        pm.freeze(
            plan,
            locked_sections=["requirements", "user_journey", "view.screens"],
        )

    plan_path = docs_dir / "harness-plan.md"
    pm.save(plan, plan_path)

    # tasks.md 최소 생성 (ha-build prepare 가 요구)
    tasks_path = docs_dir / "tasks.md"
    tasks_path.write_text(
        dedent("""\
            # Tasks

            | ID | Agent | Depends On | Description | Status |
            |----|-------|------------|-------------|--------|
            | T-001 | backend_coder | - | 기본 API 구현 | todo |
        """),
        encoding="utf-8",
    )

    # skeleton.md 최소 생성
    skeleton_path = docs_dir / "skeleton.md"
    skeleton_path.write_text(
        dedent("""\
            # Skeleton

            ## 1. Requirements

            요구사항.

            ## 2. User Journey

            사용자 여정.

            ## 3. View Screens

            화면 목록.
        """),
        encoding="utf-8",
    )

    return project, plan_path


def _run_ha_build_prepare(
    project: Path,
    task_id: str,
    *,
    skip_frozen_gate: bool = False,
) -> subprocess.CompletedProcess:
    """ha-build prepare 를 subprocess 로 실행.

    HARNESS_AI_HOME 을 레포 루트로 설정해 utils.py 가 올바르게 로드되도록 한다.
    """
    cmd = [sys.executable, str(_HA_BUILD_RUN), "prepare", "--task", task_id]
    if skip_frozen_gate:
        cmd.append("--skip-frozen-gate")

    env = os.environ.copy()
    env["HARNESS_AI_HOME"] = str(_REPO_ROOT)
    # ha-build/run.py 는 cwd 에서 git root 를 찾으므로 project 로 설정
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(project),
        env=env,
    )


# ── 테스트 1: drafting → BLOCK → freeze → 통과 ──────────────────────────


def test_drafting_blocks_ha_build_then_freeze_unblocks(tmp_path: Path) -> None:
    """E2E: drafting plan → ha-build prepare BLOCK → freeze → ha-build prepare 통과."""
    # Step 1: drafting plan 생성 (frozen=False)
    project, plan_path = _create_minimal_plan(tmp_path, frozen=False)

    # Step 2: ha-build prepare 호출 → exit 1 (frozen_status BLOCK)
    result_blocked = _run_ha_build_prepare(project, "T-001")
    assert result_blocked.returncode == 1, (
        f"drafting plan 에서 ha-build prepare 가 BLOCK(exit 1) 해야 함.\n"
        f"stdout={result_blocked.stdout!r}\nstderr={result_blocked.stderr!r}"
    )
    # BLOCK 메시지 포함 확인
    combined = result_blocked.stdout + result_blocked.stderr
    assert "BLOCK" in combined or "frozen_status" in combined, (
        f"BLOCK 또는 frozen_status 메시지가 출력에 없음: {combined!r}"
    )

    # Step 3: plan.freeze() 로 frozen 상태로 전이 (ha-design commit 시뮬레이션)
    pm = PlanManager()
    plan = pm.load(plan_path)
    pm.freeze(plan, locked_sections=["requirements", "user_journey", "view.screens"])
    pm.save(plan, plan_path)

    # Step 4: 재로드 후 frozen_status='frozen' 확인
    plan_after = pm.load(plan_path)
    assert plan_after.frozen_status == "frozen"

    # Step 5: ha-build prepare 재호출 → exit 0 (정상 진행)
    result_unblocked = _run_ha_build_prepare(project, "T-001")
    assert result_unblocked.returncode == 0, (
        f"frozen plan 에서 ha-build prepare 가 통과(exit 0) 해야 함.\n"
        f"stdout={result_unblocked.stdout!r}\nstderr={result_unblocked.stderr!r}"
    )


# ── 테스트 2: --skip-frozen-gate 우회 ────────────────────────────────────


def test_skip_frozen_gate_bypasses_for_migration(tmp_path: Path) -> None:
    """E2E: drafting plan → ha-build prepare --skip-frozen-gate → 통과 (escape hatch)."""
    # drafting plan (frozen=False)
    project, plan_path = _create_minimal_plan(tmp_path, frozen=False)

    # --skip-frozen-gate 없이 → BLOCK 확인 (전제 조건)
    result_blocked = _run_ha_build_prepare(project, "T-001")
    assert result_blocked.returncode == 1, (
        "전제 조건: --skip-frozen-gate 없이 drafting plan 은 BLOCK 해야 함"
    )

    # --skip-frozen-gate 붙이면 → 통과
    result_bypassed = _run_ha_build_prepare(project, "T-001", skip_frozen_gate=True)
    assert result_bypassed.returncode == 0, (
        f"--skip-frozen-gate 시 drafting plan 도 통과해야 함.\n"
        f"stdout={result_bypassed.stdout!r}\nstderr={result_bypassed.stderr!r}"
    )
