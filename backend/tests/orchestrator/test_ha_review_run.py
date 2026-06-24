"""ha-review/run.py cmd_record 의 #8 vacuous-APPROVE 가드 회귀 테스트.

패턴: subprocess 로 글로벌 run.py 실행 (test_ha_plan_run.py 와 동일).
PlanManager / HarnessPlan 을 직접 import 해 픽스처 구성,
subprocess 를 통해 cmd_record 를 호출 — stdout/stderr 분리 수집.

테스트 커버리지:
  1. vacuous 차단: 빈 diff + --allow-empty 없음 → exit 1, stderr 에 에러 메시지
  2. --allow-empty 우회: 빈 diff + --allow-empty → #8 가드 통과, exit 0
  3. 비어있지 않은 diff → #8 가드 무관, approve 가 빈-diff 이유로 차단되지 않음
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

# ha-review/run.py 절대 경로 — 글로벌 설치본 사용
_RUN_PY = Path.home() / ".claude" / "skills" / "ha-review" / "run.py"

# HARNESS_AI_HOME: agent/ 디렉토리 (backend/ 의 부모)
# __file__ = backend/tests/orchestrator/test_ha_review_run.py
# parents[0]=orchestrator, [1]=tests, [2]=backend, [3]=agent
_HARNESS_HOME = Path(__file__).resolve().parents[3]


def _make_env() -> dict[str, str]:
    """subprocess 용 환경변수. HARNESS_AI_HOME 을 이 레포로 명시 설정."""
    env = os.environ.copy()
    env["HARNESS_AI_HOME"] = str(_HARNESS_HOME)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _make_verified_plan() -> HarnessPlan:
    """state="verified" HarnessPlan 생성. init→designed→planned→building→built→verified."""
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
        pipeline_steps=["ha-init", "ha-design", "ha-plan", "ha-build", "ha-verify", "ha-review"],
        scale_axes=ScaleAxes(),
        activation_trace=None,
    )
    plan = pm.transition(plan, "designed", completed_step="ha-design")
    plan = pm.transition(plan, "planned", completed_step="ha-plan")
    plan = pm.transition(plan, "building", completed_step="ha-build")
    plan = pm.transition(plan, "built", completed_step="ha-build")
    plan = pm.transition(plan, "verified", completed_step="ha-verify")
    return plan


def _write_plan(tmp_path: Path, plan: HarnessPlan) -> Path:
    """tmp_path/docs/harness-plan.md 에 plan 저장 후 plan_path 반환."""
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    plan_path = docs / "harness-plan.md"
    PlanManager().save(plan, plan_path)
    return plan_path


def _write_skeleton(tmp_path: Path) -> Path:
    """docs/skeleton.md 최소 구조 생성."""
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    skel = docs / "skeleton.md"
    skel.write_text(
        "## 1. 개요\n\n테스트 프로젝트.\n\n## 18. 태스크 분해\n\n",
        encoding="utf-8",
    )
    return skel


def _git_init_empty_commit(project: Path) -> None:
    """git init + 빈 커밋 — _extract_diff 가 빈 diff 를 반환하도록 구성.

    docs/ 를 .git/info/exclude 로 제외해 harness-plan.md/skeleton.md 가
    untracked pseudo diff 에 잡히지 않도록 한다.
    빈 커밋(--allow-empty)이면 트래킹 파일 없음 →
      git diff _EMPTY_TREE HEAD = ""  (full-source 폴백도 빔)
      git diff HEAD = ""  (worktree clean)
      git ls-files --others --exclude-standard = ""  (untracked 없음)
    → combined = "" → 빈 diff 반환.
    """
    subprocess.run(["git", "init", "-q"], cwd=str(project), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(project),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(project),
        check=True,
        capture_output=True,
    )
    # docs/ 를 .git/info/exclude 에 추가 — harness-plan.md/skeleton.md 가
    # untracked pseudo diff 에 잡히지 않도록 (git 이미 초기화됨)
    exclude_file = project / ".git" / "info" / "exclude"
    with exclude_file.open("a", encoding="utf-8") as f:
        f.write("\ndocs/\n")
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "initial"],
        cwd=str(project),
        check=True,
        capture_output=True,
    )


def _run_record(
    project_dir: Path,
    *,
    verdict: str = "approve",
    allow_empty: bool = False,
    allow_block: bool = False,
    summary: str = "",
) -> tuple[int, dict | None, str]:
    """cmd_record 실행. (returncode, parsed_json_or_None, stderr) 반환."""
    cmd = [
        sys.executable,
        str(_RUN_PY),
        "record",
        "--verdict",
        verdict,
    ]
    if summary:
        cmd.extend(["--summary", summary])
    if allow_empty:
        cmd.append("--allow-empty")
    if allow_block:
        cmd.append("--allow-block")
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


# ── Test 1: vacuous 차단 ──────────────────────────────────────────────────────


def test_record_approve_blocked_when_diff_empty_without_allow_empty(tmp_path: Path) -> None:
    """빈 diff + --allow-empty 없음 → exit 1, stderr 에 에러 메시지 (#8 가드)."""
    plan = _make_verified_plan()
    _write_plan(tmp_path, plan)
    _write_skeleton(tmp_path)
    _git_init_empty_commit(tmp_path)

    returncode, out, stderr = _run_record(tmp_path, verdict="approve")

    assert returncode == 1, (
        f"빈 diff 임에도 exit 1 아님. returncode={returncode}\nstderr={stderr!r}\nstdout={out!r}"
    )
    # stderr + stdout 합쳐서 에러 메시지 확인
    full_output = stderr + (json.dumps(out) if out else "")
    assert (
        "비어있습니다" in full_output or "vacuous" in full_output or "allow-empty" in full_output
    ), f"예상 에러 메시지 없음. full_output={full_output!r}"


# ── Test 2: --allow-empty 우회 ───────────────────────────────────────────────


def test_record_approve_passes_with_allow_empty_on_empty_diff(tmp_path: Path) -> None:
    """빈 diff + --allow-empty → #8 가드 통과 → exit 0."""
    plan = _make_verified_plan()
    _write_plan(tmp_path, plan)
    _write_skeleton(tmp_path)
    _git_init_empty_commit(tmp_path)

    returncode, out, stderr = _run_record(
        tmp_path, verdict="approve", allow_empty=True, allow_block=True
    )

    assert returncode == 0, (
        f"--allow-empty 우회임에도 exit 0 아님. returncode={returncode}\nstderr={stderr!r}\nstdout={out!r}"
    )
    assert out is not None, "stdout JSON 없음"
    assert out.get("verdict") == "approve", f"verdict 가 approve 아님: {out!r}"


# ── Test 3: 비어있지 않은 diff → #8 가드 무관 ────────────────────────────────


def test_record_approve_not_blocked_by_empty_guard_when_diff_nonempty(tmp_path: Path) -> None:
    """변경이 있는 diff → #8 빈-diff 가드 무관 — 빈-diff 이유로 차단되지 않음."""
    plan = _make_verified_plan()
    _write_plan(tmp_path, plan)
    _write_skeleton(tmp_path)

    # git init + 파일 추가 후 커밋 → diff _EMPTY_TREE HEAD 에 내용 있음
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    # 소스 파일 추가
    src = tmp_path / "main.py"
    src.write_text("def hello():\n    return 'hello'\n", encoding="utf-8")
    subprocess.run(["git", "add", "main.py"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "add main.py"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )

    # BLOCK 없는 코드이므로 --allow-block 불필요; 단 BLOCK 가드가 따로 막을 수 있으므로 우회
    returncode, out, stderr = _run_record(tmp_path, verdict="approve", allow_block=True)

    # #8 빈-diff 차단 메시지가 없어야 함 (returncode 는 0 또는 다른 이유로 1 가능)
    full_output = stderr + (json.dumps(out) if out else "")
    assert "비어있습니다" not in full_output, (
        f"비어있지 않은 diff 인데 #8 빈-diff 에러 발생. full_output={full_output!r}"
    )
    # 빈-diff 이유로 exit 1 이 아님 확인
    if returncode != 0:
        assert "비어있습니다" not in full_output, (
            f"#8 가드가 비어있지 않은 diff 를 차단함. stderr={stderr!r}"
        )
