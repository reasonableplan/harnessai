"""ha-resync/run.py 기능 검증 테스트.

패턴: subprocess 로 run.py 실행 (test_ha_plan_run.py 와 동일).
PlanManager / HarnessPlan 을 직접 import 해 픽스처 구성,
subprocess 를 통해 run.py 를 호출 — stdout/stderr 분리 수집.

테스트 커버리지:
  1. --dry-run → exit 0, plan 파일 미수정, JSON "applied": false + new_skeleton_hash 존재
  2. apply (stale 상태) → exit 0, skeleton_hash/section_hashes 갱신, 백업 생성, "applied": true
  3. 무조건 덮어쓰기 → 기존 해시 있어도 갱신 (old≠new 확인)
  4. skeleton.md 없음 → exit 3, stderr 에 안내
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from src.orchestrator.plan_manager import (
    HarnessPlan,
    PlanManager,
    ProfileRef,
    ScaleAxes,
    SkeletonSpec,
)
from src.orchestrator.skeleton_hash import compute_section_hashes, compute_skeleton_hash

# ha-resync/run.py 절대 경로 (글로벌 사본 사용)
_RUN_PY = Path.home() / ".claude" / "skills" / "ha-resync" / "run.py"

# HARNESS_AI_HOME: agent/ 디렉토리 (backend/ 의 부모)
# __file__ = backend/tests/orchestrator/test_ha_resync_run.py
# parents[0]=orchestrator, [1]=tests, [2]=backend, [3]=agent
_HARNESS_HOME = Path(__file__).resolve().parents[3]


def _make_env() -> dict[str, str]:
    """subprocess 용 환경변수. HARNESS_AI_HOME 을 이 레포로 명시 설정."""
    env = os.environ.copy()
    env["HARNESS_AI_HOME"] = str(_HARNESS_HOME)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _write_plan(tmp_path: Path, plan: HarnessPlan) -> Path:
    """tmp_path/docs/harness-plan.md 에 plan 저장 후 plan_path 반환."""
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    plan_path = docs / "harness-plan.md"
    PlanManager().save(plan, plan_path)
    return plan_path


def _write_skeleton(tmp_path: Path, content: str | None = None) -> Path:
    """docs/skeleton.md 생성. content 미지정 시 기본 최소 구조 사용."""
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    skel = docs / "skeleton.md"
    skel.write_text(
        content
        if content is not None
        else "## 1. 개요\n\n테스트 프로젝트.\n\n## 18. 태스크 분해\n\n",
        encoding="utf-8",
    )
    return skel


def _make_plan(
    *, skeleton_hash: str = "", section_hashes: dict[str, str] | None = None
) -> HarnessPlan:
    """designed 상태 HarnessPlan 생성 헬퍼."""
    pm = PlanManager()
    plan = pm.create(
        project_name="TestProject",
        project_type="app",
        scale="small",
        user_description_original="테스트 프로젝트",
        profiles=[ProfileRef(id="fastapi", path=".")],
        skeleton_sections=SkeletonSpec(
            required=("overview", "stack"),
            optional=(),
            included=("overview", "stack"),
        ),
        pipeline_steps=["ha-init", "ha-design", "ha-plan", "ha-build", "ha-verify"],
        scale_axes=ScaleAxes(),
        activation_trace=None,
    )
    plan = pm.transition(plan, "designed", completed_step="ha-design")
    plan.skeleton_hash = skeleton_hash
    if section_hashes is not None:
        plan.section_hashes = section_hashes
    return plan


def _run_resync(project_dir: Path, *, dry_run: bool = False) -> tuple[int, dict | None, str]:
    """run.py 실행. (returncode, parsed_json_or_None, stderr) 반환."""
    cmd = [sys.executable, str(_RUN_PY)]
    if dry_run:
        cmd.append("--dry-run")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(project_dir),
        env=_make_env(),
    )
    try:
        parsed = json.loads(result.stdout) if result.stdout.strip() else None
    except json.JSONDecodeError:
        parsed = None
    return result.returncode, parsed, result.stderr


# ── Test 1: --dry-run → exit 0, plan 미수정, JSON applied=false + new_skeleton_hash ──


def test_dry_run_does_not_modify_plan(tmp_path: Path) -> None:
    """--dry-run: exit 0, plan 파일 해시 그대로, JSON "applied": false + new_skeleton_hash 존재."""
    skel_path = _write_skeleton(tmp_path)
    # plan 에 의도적으로 빈 해시 기록 (stale 상태)
    plan = _make_plan(skeleton_hash="")
    plan_path = _write_plan(tmp_path, plan)

    plan_mtime_before = plan_path.stat().st_mtime

    returncode, out, stderr = _run_resync(tmp_path, dry_run=True)

    assert returncode == 0, (
        f"--dry-run 에서 exit code != 0. returncode={returncode}\nstderr={stderr!r}"
    )
    assert out is not None, "stdout JSON 없음"
    assert out.get("applied") is False, f'"applied" 가 False 여야 함: {out.get("applied")}'
    assert "new_skeleton_hash" in out, '"new_skeleton_hash" 키 누락'
    assert out["new_skeleton_hash"], '"new_skeleton_hash" 가 빈 문자열'

    # plan 파일이 수정되지 않아야 함
    plan_mtime_after = plan_path.stat().st_mtime
    assert plan_mtime_before == plan_mtime_after, "dry-run 인데 plan 파일이 수정됨"

    # 독립 계산값과 일치 확인
    expected_hash = compute_skeleton_hash(skel_path)[:12]
    assert out["new_skeleton_hash"] == expected_hash, (
        f"new_skeleton_hash 불일치: got={out['new_skeleton_hash']!r}, expected={expected_hash!r}"
    )


# ── Test 2: apply (stale 상태) → exit 0, 해시 갱신, 백업 생성, applied=true ─────


def test_apply_updates_hashes_and_creates_backup(tmp_path: Path) -> None:
    """skeleton.md 손수정 후 인자 없이 실행 → skeleton_hash/section_hashes 갱신 + 백업 생성."""
    # 초기 skeleton 으로 plan 기록
    skel_path = _write_skeleton(tmp_path, "## 1. 개요\n\n원본 내용.\n\n## 18. 태스크 분해\n\n")
    original_hash = compute_skeleton_hash(skel_path)
    original_sections = compute_section_hashes(skel_path)

    plan = _make_plan(skeleton_hash=original_hash, section_hashes=dict(original_sections))
    plan_path = _write_plan(tmp_path, plan)

    # skeleton.md 손수정 → stale 상태
    skel_path.write_text(
        "## 1. 개요\n\n수정된 내용.\n\n## 2. 스택\n\nFastAPI.\n\n## 18. 태스크 분해\n\n",
        encoding="utf-8",
    )
    new_expected_hash = compute_skeleton_hash(skel_path)
    new_expected_sections = compute_section_hashes(skel_path)

    returncode, out, stderr = _run_resync(tmp_path)

    assert returncode == 0, f"apply 실패. returncode={returncode}\nstderr={stderr!r}"
    assert out is not None, "stdout JSON 없음"
    assert out.get("applied") is True, f'"applied" 가 True 여야 함: {out.get("applied")}'

    # 백업 생성 확인
    assert out.get("backup_path") is not None, '"backup_path" 누락'
    backup = Path(out["backup_path"])
    assert backup.exists(), f"백업 파일 없음: {backup}"

    # plan 재로드 후 해시 확인
    reloaded = PlanManager().load(plan_path)
    assert reloaded.skeleton_hash == new_expected_hash, (
        f"skeleton_hash 갱신 안 됨: got={reloaded.skeleton_hash!r}, expected={new_expected_hash!r}"
    )
    assert reloaded.section_hashes == new_expected_sections, (
        f"section_hashes 갱신 안 됨: got={reloaded.section_hashes}, expected={new_expected_sections}"
    )

    # JSON 의 new_skeleton_hash(12자리 prefix) 확인
    assert out["new_skeleton_hash"] == new_expected_hash[:12], (
        f"JSON new_skeleton_hash 불일치: {out['new_skeleton_hash']!r} vs {new_expected_hash[:12]!r}"
    )


# ── Test 3: 무조건 덮어쓰기 → 기존 해시 있어도 갱신 (old≠new 확인) ───────────


def test_apply_overwrites_existing_hash_unconditionally(tmp_path: Path) -> None:
    """기존 skeleton_hash 가 있어도 거부 없이 무조건 덮어쓴다."""
    skel_path = _write_skeleton(tmp_path, "## 1. 개요\n\n초기 내용.\n\n")
    old_hash = "deadbeef" * 8  # 64자 임의 해시 (실제 파일과 다름)

    plan = _make_plan(skeleton_hash=old_hash, section_hashes={"overview": "aabbcc"})
    plan_path = _write_plan(tmp_path, plan)

    returncode, out, stderr = _run_resync(tmp_path)

    assert returncode == 0, f"기존 해시 있을 때 실패. returncode={returncode}\nstderr={stderr!r}"
    assert out is not None, "stdout JSON 없음"
    assert out.get("applied") is True, '"applied" 가 True 여야 함'

    reloaded = PlanManager().load(plan_path)
    new_real_hash = compute_skeleton_hash(skel_path)

    # 갱신됐는지 확인
    assert reloaded.skeleton_hash == new_real_hash, (
        f"skeleton_hash 갱신 안 됨: got={reloaded.skeleton_hash!r}"
    )
    # 기존 임의 해시와 달라야 함
    assert reloaded.skeleton_hash != old_hash, (
        "old≠new 조건 불충족 — 임의 해시가 우연히 일치하거나 덮어쓰기 안 됨"
    )

    # old_skeleton_hash 가 JSON 에 포함돼야 함
    assert out.get("old_skeleton_hash") == old_hash[:12], (
        f"JSON old_skeleton_hash 불일치: {out.get('old_skeleton_hash')!r} vs {old_hash[:12]!r}"
    )


# ── Test 4: skeleton.md 없음 → exit 3, stderr 에 안내 ───────────────────────


def test_exit3_when_skeleton_missing(tmp_path: Path) -> None:
    """skeleton.md 없으면 exit 3, stderr 에 안내 메시지."""
    plan = _make_plan(skeleton_hash="")
    _write_plan(tmp_path, plan)
    # skeleton.md 를 생성하지 않음

    returncode, _out, stderr = _run_resync(tmp_path)

    assert returncode == 3, (
        f"skeleton 없을 때 exit code 3 기대. 실제={returncode}\nstderr={stderr!r}"
    )
    assert stderr.strip(), "stderr 가 비어있음 — 안내 메시지 없음"
