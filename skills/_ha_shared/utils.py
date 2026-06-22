"""HarnessAI v2 — `/ha-*` 스킬 공유 유틸.

각 ha-* 스킬의 run.py 가 import:
    sys.path.insert(0, str(Path(__file__).parent.parent / "_ha_shared"))
    from utils import (
        load_plan, save_plan, transition,
        get_active_profiles, get_docs_dir, project_root,
        TASK_ID_RE, TASK_ROW_RE, SKELETON_HEADING_RE, validate_task_id,
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
    STATE_ORDER,
    HarnessPlan,
    PlanManager,
    PlanNotFoundError,
)
from src.orchestrator.profile_loader import Profile, ProfileLoader  # noqa: E402
from src.orchestrator.task_id import (  # noqa: E402, F401
    SKELETON_HEADING_RE,
    TASK_ID_RE,
    TASK_ROW_RE,
    validate_task_id,
)


def project_root() -> Path:
    """git root 또는 cwd."""
    import subprocess
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            check=True,
        )
        return Path(out.stdout.strip()).resolve()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path.cwd().resolve()


# untracked 의사 diff — 벤더/생성물 디렉토리는 .gitignore 없어도 제외
_UNTRACKED_SKIP_SEGMENTS = frozenset({
    "node_modules", "dist", "build", "__pycache__", ".venv", "venv",
    ".git", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".next", "coverage",
})
UNTRACKED_FILE_MAX_BYTES = 200_000
UNTRACKED_TOTAL_MAX_BYTES = 2_000_000


def untracked_pseudo_diff(project: Path, timeout: int = 60) -> str:
    """untracked 신규 파일을 `diff --git` 형식 의사 diff 로 합성 (dogfood P1).

    git diff (HEAD / main...HEAD / --cached) 는 미추적 파일을 포함하지 않아
    방금 생성된 모듈이 보안/슬롭/LESSON 스캔을 통째로 우회한다. 합성 헤더는
    strip_doc_files_from_diff 가 인식하는 `diff --git a/.. b/..` 형식을
    그대로 따라 문서 파일 제외 규칙이 동일하게 적용된다.

    바이너리(NUL 포함)/크기 상한 초과/벤더 디렉토리는 제외. git 미설치·
    repo 아님·timeout 은 빈 문자열 (호출처의 기존 not-git 처리 유지).
    """
    import subprocess
    try:
        out = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=str(project), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    if out.returncode != 0:
        return ""

    blocks: list[str] = []
    budget = UNTRACKED_TOTAL_MAX_BYTES
    for rel in out.stdout.splitlines():
        rel = rel.strip()
        if not rel:
            continue
        posix = Path(rel).as_posix()
        if any(seg in _UNTRACKED_SKIP_SEGMENTS for seg in posix.split("/")):
            continue
        f = project / rel
        try:
            if not f.is_file():
                continue
            size = f.stat().st_size
            if size > UNTRACKED_FILE_MAX_BYTES or size > budget:
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "\x00" in text:
            continue
        budget -= size
        added = "".join(f"+{line}\n" for line in text.splitlines())
        blocks.append(
            f"diff --git a/{posix} b/{posix}\n"
            "new file mode 100644\n"
            "--- /dev/null\n"
            f"+++ b/{posix}\n" + added
        )
    return "".join(blocks)


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


def regress(plan: HarnessPlan, target_state: str) -> HarnessPlan:
    """상태 역행 — verify/review 실패 시 building 회귀 등."""
    return PlanManager().regress(plan, target_state)


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


def reenter_or_assert(
    plan: HarnessPlan,
    plan_path: Path,
    *,
    prerequisite_state: str,
    working_state: str,
    skill_name: str,
) -> bool:
    """phase 스킬의 상태 게이트 + 1급 반복(iteration/재진입).

    forward-only 상태머신이 "리뷰/검증 이후 이전 phase 재실행"(re-plan / 추가 빌드 /
    재설계)을 막아 같은 클래스의 버그(#2/#9/#12)를 반복 생산하던 것을, 재진입을
    명시 허용해 해소한다. #2(--replan)·#9(_enter_build_state) 의 ad-hoc 수정을 일원화.

    상태별 동작 (STATE_ORDER 기준):
    - current < prerequisite_state  → 차단 (exit 2). 선행 phase 미완료.
    - prerequisite_state <= current <= working_state → 그대로 진행 (정상 forward).
    - current > working_state  → 재진입: working_state 로 regress(+save) 하여 새 작업이
      downstream 게이트(verify/review)를 다시 거치게 한다. info 로 표면화.

    Returns: regress 가 일어났으면 True (재진입), 아니면 False.
    """
    cur = plan.pipeline.current_step
    ci = STATE_ORDER.index(cur)
    pi = STATE_ORDER.index(prerequisite_state)
    wi = STATE_ORDER.index(working_state)

    if ci < pi:
        print(
            f"[FAIL] {skill_name} 사전 조건 위반.\n"
            f"       현재 상태: {cur}\n"
            f"       필요: {prerequisite_state} 이상.\n"
            f"       선행 /ha-* 를 먼저 실행하세요.",
            file=sys.stderr,
        )
        sys.exit(2)

    if ci > wi:
        regress(plan, working_state)
        save_plan(plan, plan_path)
        info(
            f"[INFO] {cur} -> {working_state} 회귀 ({skill_name} 재진입). "
            "이후 단계(verify/review 등)를 다시 거쳐야 합니다."
        )
        return True
    return False


MOBILE_PROFILE_IDS: frozenset[str] = frozenset(
    {"react-native-expo", "flutter", "android-kotlin", "ios-swift"}
)
FRONTEND_PROFILE_IDS: frozenset[str] = frozenset({"react-vite", "nextjs", "electron"})
BACKEND_PROFILE_IDS: frozenset[str] = frozenset({"fastapi", "nestjs", "python-cli", "python-lib"})


def resolve_guideline_paths(profile_id: str) -> list[Path]:
    """profile_id 의 templates/guidelines/<profile_id>/*.md 정렬된 절대 경로 리스트.

    - HARNESS_HOME / "harness" / "templates" / "guidelines" / profile_id 검색
    - *.md 파일 정렬(sorted) 해서 Path 리스트 반환
    - 디렉토리 없거나 *.md 없으면 빈 리스트 반환 (silent skip — 비-모바일/비-web 프로파일 호환)
    """
    if HARNESS_HOME is None:
        return []
    guidelines_dir = HARNESS_HOME / "harness" / "templates" / "guidelines" / profile_id
    if not guidelines_dir.is_dir():
        return []
    return sorted(guidelines_dir.glob("*.md"))


def info(*args: Any) -> None:
    """stderr 로 안내 메시지 출력 (stdout 은 JSON 결과용)."""
    print(*args, file=sys.stderr)
