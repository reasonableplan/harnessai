"""HarnessAI v2 — `/ha-*` 스킬 공유 유틸.

각 ha-* 스킬의 run.py 가 import:
    sys.path.insert(0, str(Path(__file__).parent.parent / "_ha_shared"))
    from utils import (
        load_plan, save_plan, transition,
        get_active_profiles, get_docs_dir, project_root,
    )
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# UTF-8 stdout (Windows cp949 호환)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

# v2 모듈 import — HARNESS_AI_HOME 환경변수 (필수).
#
# dev 모드 (repo 내 직접 실행) 시에는 이 파일 경로로부터 자동 탐지:
#   <repo>/skills/_ha_shared/utils.py → parents[2] = <repo>
# 설치된 상태 (~/.claude/skills/...) 에서는 env 가 반드시 설정돼야 함.
_ENV_HOME = os.environ.get("HARNESS_AI_HOME")
if _ENV_HOME:
    HARNESS_HOME = Path(_ENV_HOME)
else:
    _repo_candidate = Path(__file__).resolve().parents[2]
    HARNESS_HOME = _repo_candidate if (_repo_candidate / "backend").is_dir() else None  # type: ignore[assignment]

if HARNESS_HOME is None or not (HARNESS_HOME / "backend").is_dir():
    print(
        "[FAIL] HARNESS_AI_HOME 환경변수 필요 — HarnessAI 레포 절대 경로를 가리켜야 함.\n"
        "  예: export HARNESS_AI_HOME=/path/to/harnessai  (bash/zsh)\n"
        "      $env:HARNESS_AI_HOME = 'C:\\path\\to\\harnessai'  (PowerShell)\n"
        "  설치 후 자동 설정은 install.sh/ps1 README 참조.",
        file=sys.stderr,
    )
    sys.exit(3)
_BACKEND = HARNESS_HOME / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from src.orchestrator.plan_manager import (  # noqa: E402
    HarnessPlan,
    PlanManager,
    PlanNotFoundError,
)
from src.orchestrator.profile_loader import Profile, ProfileLoader  # noqa: E402


def project_root() -> Path:
    """git root 또는 cwd."""
    import subprocess
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        )
        return Path(out.stdout.strip()).resolve()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path.cwd().resolve()


def get_docs_dir(plan: HarnessPlan, project: Path) -> Path:
    """plan 의 첫 프로파일 path + docs/."""
    if plan.profiles:
        primary_path = plan.profiles[0].path
        base = project if primary_path == "." else (project / primary_path)
        return base / "docs" if base.exists() else project / "docs"
    return project / "docs"


def find_plan_path(project: Path) -> Path:
    """프로젝트의 harness-plan.md 위치 탐색.

    우선순위: backend/docs/, docs/, frontend/docs/, apps/*/docs/ (루트 인접)
    """
    candidates = [
        project / "backend" / "docs" / "harness-plan.md",
        project / "docs" / "harness-plan.md",
        project / "frontend" / "docs" / "harness-plan.md",
    ]
    for c in candidates:
        if c.exists():
            return c
    # 못 찾으면 backend/docs 우선 반환 (없으면 PlanNotFoundError 자연 발생)
    return candidates[0]


def load_plan(project: Path | None = None) -> tuple[HarnessPlan, Path, Path]:
    """플랜 로드. 반환: (plan, plan_path, project_root)."""
    proj = project or project_root()
    plan_path = find_plan_path(proj)
    pm = PlanManager()
    try:
        plan = pm.load(plan_path)
    except PlanNotFoundError:
        print(
            f"[FAIL] harness-plan.md 없음: {plan_path}\n"
            f"       먼저 /ha-init 을 실행하세요.",
            file=sys.stderr,
        )
        sys.exit(1)
    return plan, plan_path, proj


def save_plan(plan: HarnessPlan, plan_path: Path) -> None:
    PlanManager().save(plan, plan_path)


def transition(
    plan: HarnessPlan,
    target_state: str,
    *,
    completed_step: str | None = None,
) -> HarnessPlan:
    """상태 전이 + 검증."""
    return PlanManager().transition(plan, target_state, completed_step=completed_step)


def record_verify(
    plan: HarnessPlan,
    *,
    step: str,
    passed: bool,
    summary: str,
) -> HarnessPlan:
    return PlanManager().record_verify(
        plan, step=step, passed=passed, summary=summary
    )


def get_active_profiles(plan: HarnessPlan, project: Path) -> list[Profile]:
    """plan 에 기록된 프로파일들을 ProfileLoader 로 로드."""
    loader = ProfileLoader(project_dir=project)
    profiles = []
    for ref in plan.profiles:
        profiles.append(loader.load(ref.id))
    return profiles


def assert_state(plan: HarnessPlan, allowed: list[str], skill_name: str) -> None:
    """현재 상태가 allowed 에 있는지 확인. 아니면 에러."""
    if plan.pipeline.current_step not in allowed:
        print(
            f"[FAIL] {skill_name} 사전 조건 위반.\n"
            f"       현재 상태: {plan.pipeline.current_step}\n"
            f"       허용 상태: {allowed}\n"
            f"       해당 상태로 가려면 적절한 이전 /ha-* 를 먼저 실행.",
            file=sys.stderr,
        )
        sys.exit(2)


def info(*args: Any) -> None:
    """stderr 로 안내 메시지 출력 (stdout 은 JSON 결과용)."""
    print(*args, file=sys.stderr)
