#!/usr/bin/env python3
"""HarnessAI v2 — `/ha-build` 백엔드."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "_ha_shared"))
from utils import (  # noqa: E402, I001
    BACKEND_PROFILE_IDS,
    FRONTEND_PROFILE_IDS,
    HARNESS_HOME,
    MOBILE_PROFILE_IDS,
    TASK_ROW_RE,
    assert_state,
    get_active_profiles,
    info,
    load_plan,
    reenter_or_assert,
    resolve_guideline_paths,
    save_plan,
    transition,
    untracked_pseudo_diff,
    validate_task_id,
)

from src.orchestrator.skeleton_hash import check_skeleton_hash  # noqa: E402


_AGENT_TO_PROFILE: dict[str, str] = {
    "mobile_coder_rn": "react-native-expo",
    "mobile_coder_flutter": "flutter",
    "mobile_coder_android": "android-kotlin",
    "mobile_coder_ios": "ios-swift",
}


def _agent_to_guideline_paths(agent: str, plan) -> list[str]:
    """agent 이름 → guideline_paths 문자열 리스트.

    모바일 코더: 고정 매핑.
    backend_coder: plan 의 profiles 중 첫 번째 backend 프로파일.
    frontend_coder: plan 의 profiles 중 첫 번째 frontend 프로파일.
    qa: plan 의 모든 프로파일 가이드라인 합집합 (정렬).
    기타: 빈 리스트.
    """
    if agent in _AGENT_TO_PROFILE:
        return [str(g) for g in resolve_guideline_paths(_AGENT_TO_PROFILE[agent])]

    profile_ids = [ref.id for ref in plan.profiles]

    if agent == "backend_coder":
        for pid in profile_ids:
            if pid in BACKEND_PROFILE_IDS:
                return [str(g) for g in resolve_guideline_paths(pid)]
        return []

    if agent == "frontend_coder":
        for pid in profile_ids:
            if pid in FRONTEND_PROFILE_IDS:
                return [str(g) for g in resolve_guideline_paths(pid)]
        return []

    if agent == "qa":
        seen: set[str] = set()
        paths: list[str] = []
        for pid in profile_ids:
            for g in resolve_guideline_paths(pid):
                s = str(g)
                if s not in seen:
                    seen.add(s)
                    paths.append(s)
        return sorted(paths)

    return []


def _parse_tasks(tasks_text: str) -> dict[str, dict[str, str]]:
    """tasks.md 에서 태스크 dict 파싱: {T-001: {agent, depends_on, description, status}}.

    TASK_ROW_RE is shared with ha-redesign and consistency_checker so all three
    enforce the same strict ID contract — malformed IDs simply fail to match the
    row and fall through to the "task not found" branch. User-supplied --task
    arguments are gated upstream by validate_task_id in cmd_prepare.
    """
    out: dict[str, dict[str, str]] = {}
    for m in TASK_ROW_RE.finditer(tasks_text):
        tid = m.group(1)
        agent = m.group(2).strip()
        deps_raw = m.group(3).strip()
        depends_on = (
            [d.strip() for d in deps_raw.split(",") if d.strip() and d.strip() != "-"]
        )
        desc = m.group(4).strip()
        status = m.group(5).strip()
        out[tid] = {
            "agent": agent,
            "depends_on": depends_on,
            "description": desc,
            "status": status,
        }
    return out


# ── 부분 완료 복구 (issue #7) ────────────────────────────────────────────
# 서브에이전트가 태스크 도중 죽으면 status 가 '대기' 로 남고 부분 산출물이 추적되지
# 않는다. prepare 가 착수 시 in-progress 로 마킹 → 죽으면 그 상태가 보이고, 재진입 시
# 선언 산출 파일 존재 여부로 부분 완료를 알려 "이어서/처음부터" 판단을 돕는다.
_INPROGRESS_STATES = ("in-progress", "진행중")
_PENDING_STATES = ("대기", "pending", "")

_SPEC_BLOCK_RE = re.compile(
    r"^###\s+(T-\d+)\b(.*?)(?=^###\s+T-\d+\b|\Z)", re.MULTILINE | re.DOTALL
)


def _declared_files(tasks_text: str, tid: str) -> list[str]:
    """tid 의 spec 블록에서 선언된 산출 파일 경로 (backtick + '/' 포함 토큰).

    skeleton 참조(`persistence.users` 등 '/' 없음)·§ 섹션 ref 는 제외 — 실제 경로만.
    """
    for m in _SPEC_BLOCK_RE.finditer(tasks_text):
        if m.group(1) != tid:
            continue
        files = [
            tok.strip()
            for tok in re.findall(r"`([^`]+)`", m.group(2))
            if "/" in tok and " " not in tok.strip() and not tok.strip().startswith("§")
        ]
        return list(dict.fromkeys(files))
    return []


def _mark_in_progress(tasks_text: str, tid: str) -> str:
    """tid 행이 대기/pending 이면 status 컬럼을 in-progress 로 교체 (그 외 상태 무변경)."""

    def repl(m: re.Match[str]) -> str:
        if m.group(2).strip().lower() in _PENDING_STATES:
            return f"{m.group(1)}{'in-progress':<10}{m.group(3)}"
        return m.group(0)

    return re.sub(
        rf"(\|\s*{re.escape(tid)}\s*\|.*?\|.*?\|.*?\|\s*)([^|]+)(\|\s*$)",
        repl,
        tasks_text,
        count=1,
        flags=re.MULTILINE,
    )


def _enter_build_state(plan, plan_path) -> None:
    """빌드 사전 조건(상태) 확인 + Phase 추가 빌드 시 building 회귀.

    공유 유틸 reenter_or_assert 로 일원화 (issue #9 + 축A 패턴1). planned 이상이면
    진입, built/verified/reviewed 등 이후 상태는 building 으로 회귀시켜 새 코드가
    verify/review 게이트를 다시 거치게 한다.
    """
    reenter_or_assert(
        plan,
        plan_path,
        prerequisite_state="planned",
        working_state="building",
        skill_name="/ha-build",
    )


def cmd_prepare(args: argparse.Namespace) -> int:
    plan, plan_path, project = load_plan()
    _enter_build_state(plan, plan_path)

    # v0.10.0 HITL gate — frozen_status="drafting" 이면 /ha-build 진입 차단.
    # /ha-design 의 LOCKED 섹션 (requirements/user_journey/view.screens) 인터뷰 통과 필수.
    if plan.frozen_status != "frozen" and not args.skip_frozen_gate:
        info(
            "[BLOCK] /ha-build 진입 거부 — frozen_status=drafting (HITL 미완료).\n"
            "  · /ha-design 의 LOCKED 섹션 (requirements/user_journey/view.screens) "
            "인터뷰 채우기 필요.\n"
            "  · 채운 후: /ha-design commit 시 plan.freeze() 가 호출되어 frozen 으로 전이.\n"
            "  · 개발/마이그레이션용 우회: --skip-frozen-gate (의도적 사용 — 비추천)."
        )
        return 1

    # skeleton drift 게이트 — freeze 이후 외부 수정 감지 (architecture review F2).
    # skeleton_hash 는 ha-design/ha-redesign/ha-plan 이 갱신한다 (ha-plan 은 §태스크
    # 분해 sync 후 baseline refresh — issue #1/#5). 따라서 mismatch = 미감사 외부 수정.
    # 구현 단계가 skeleton 을 가장 많이 소비하는데 기존엔 이 검사가 없었다.
    skel_path = plan_path.parent / "skeleton.md"
    hash_check = check_skeleton_hash(plan.skeleton_hash or "", skel_path)
    if not hash_check.skeleton_missing and not hash_check.is_legacy and not hash_check.is_match:
        if not getattr(args, "accept_skeleton_drift", False):
            info(
                "[BLOCK] skeleton.md 가 마지막 ha-design/ha-redesign 이후 외부에서 수정됨 "
                "(hash mismatch).\n"
                "  · 변경을 추적하려면: /ha-redesign 으로 결정 반영 (권장 — audit trail 보존)\n"
                "  · 의도적 수동 편집이면: --accept-skeleton-drift 로 재실행"
            )
            return 1
        info("[WARN] skeleton hash mismatch — --accept-skeleton-drift 로 진행 (audit trail 누락)")

    tasks_path = plan_path.parent / "tasks.md"
    if not tasks_path.exists():
        info(f"[FAIL] tasks.md 없음: {tasks_path}")
        return 1
    tasks_text = tasks_path.read_text(encoding="utf-8")
    tasks = _parse_tasks(tasks_text)

    target_ids = args.task.split(",") if args.task else []
    if not target_ids:
        info("[FAIL] --task <T-ID> 또는 --task T-001,T-002 필요")
        return 2

    # Validate ID format up front so a malformed --task arg surfaces as a
    # specific format error instead of the generic "task not found" message.
    for tid in target_ids:
        try:
            validate_task_id(tid)
        except ValueError as e:
            info(f"[FAIL] {e}")
            return 2

    # depends_on 만족 검사
    issues: list[str] = []
    for tid in target_ids:
        if tid not in tasks:
            issues.append(f"태스크 '{tid}' 없음 in tasks.md")
            continue
        for dep in tasks[tid]["depends_on"]:
            if dep not in tasks:
                issues.append(f"{tid} depends_on '{dep}' 가 tasks.md 에 없음")
            elif tasks[dep]["status"].lower() not in ("done", "완료", "completed"):
                issues.append(f"{tid} depends_on '{dep}' 가 미완료 (status={tasks[dep]['status']})")

    if issues:
        for i in issues:
            info(f"[BLOCK] {i}")
        return 1

    # 병렬 모드 검증 — 같은 그룹 내 서로 depends_on X
    if len(target_ids) > 1:
        targets_set = set(target_ids)
        for tid in target_ids:
            for dep in tasks[tid]["depends_on"]:
                if dep in targets_set:
                    info(f"[FAIL] 병렬 그룹 내 의존: {tid} → {dep}. 직렬 실행 필요.")
                    return 1

    # ── 부분 완료 복구 (issue #7) — 재진입 감지 + 착수 in-progress 마킹 ────
    # 이미 in-progress 면 이전 착수가 끝나지 않은 것 (서브에이전트 중단) → 선언 산출
    # 파일 존재로 부분 완료를 알린다. 대기 면 착수 마킹해 다음 중단 시 보이게 한다.
    reentry_info: dict[str, dict] = {}
    new_tasks_text = tasks_text
    for tid in target_ids:
        declared = _declared_files(tasks_text, tid)
        existing = [f for f in declared if (project / f).exists()]
        is_reentry = tasks[tid]["status"].strip().lower() in _INPROGRESS_STATES
        reentry_info[tid] = {
            "reentry": is_reentry,
            "declared_files": declared,
            "existing_files": existing,
        }
        if is_reentry:
            info(
                f"[WARN] {tid} 이전에 착수됨 (status=in-progress) — 서브에이전트 중단 후 재진입 가능성.\n"
                f"  · 선언 산출 파일 {len(declared)}개 중 {len(existing)}개 존재"
                + (f": {', '.join(existing)}" if existing else "")
                + "\n  · 부분 산출물을 점검하고 '이어서' 또는 '처음부터' 결정하세요 (덮어쓰기 주의)."
            )
        else:
            new_tasks_text = _mark_in_progress(new_tasks_text, tid)
            tasks[tid]["status"] = "in-progress"
    if new_tasks_text != tasks_text:
        try:
            tasks_path.write_text(new_tasks_text, encoding="utf-8")
        except OSError as e:
            info(f"[WARN] in-progress 착수 마킹 실패 (계속 진행): {e}")

    profiles = get_active_profiles(plan, project)

    output = {
        "project": str(project),
        "plan_path": str(plan_path),
        "tasks_path": str(tasks_path),
        "tasks": [
            {
                "id": tid,
                **tasks[tid],
                **reentry_info[tid],
                "agent_prompt": str(HARNESS_HOME / "backend" / "agents" / tasks[tid]["agent"] / "CLAUDE.md"),
                "guideline_paths": _agent_to_guideline_paths(tasks[tid]["agent"], plan),
            }
            for tid in target_ids
        ],
        "profiles": [
            {
                "id": p.id,
                "path": str(plan.profiles[i].path) if i < len(plan.profiles) else ".",
                "toolchain_test": p.toolchain.test,
                "whitelist_runtime": list(p.whitelist.runtime),
            }
            for i, p in enumerate(profiles)
        ],
        "parallel": len(target_ids) > 1,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def _is_git_repo(project: Path) -> tuple[bool, bool]:
    """git repo 여부 + git 설치 여부 확인.

    반환: (is_repo, git_installed)
    - (True, True): 정상 git repo
    - (False, True): git 있지만 repo 아님
    - (False, False): git 미설치
    """
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=str(project),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        return r.returncode == 0, True
    except FileNotFoundError:
        return False, False
    except subprocess.TimeoutExpired:
        return False, True


def _run_security_gate(project: Path, plan) -> list[str]:
    """Security hooks gate on git diff — BLOCK findings → done 거부.

    git diff HEAD (uncommitted changes) 또는 --cached (staged) 에서 diff 추출.
    security_hooks.SecurityHooks 로 BLOCK 패턴 검사.
    not-git repo 는 WARN 출력 후 silent pass → visible pass 로 변경.
    ImportError 시 조용히 skip (CI 환경 등).
    """
    # G3: not-git repo 에서 silent pass → visible WARN
    is_repo, git_installed = _is_git_repo(project)
    if not git_installed:
        info(
            "[WARN] /ha-build security_gate skipped — git 명령 미설치.\n"
            "       보안 훅이 git diff 로 변경분을 추출하므로 git 없이는 검사 불가.\n"
            "       권장: git 설치 후 재실행."
        )
        return []
    if not is_repo:
        info(
            "[WARN] /ha-build security_gate skipped — git 저장소 아님.\n"
            "       보안 훅이 git diff 로 변경분을 추출하므로 git repo 없이는 검사 불가.\n"
            f"       project: {project}\n"
            "       권장: git init && git add -A && git commit -m \"initial\" 후 재실행."
        )
        return []

    diff_text = ""
    for git_args in (["git", "diff", "HEAD"], ["git", "diff", "--cached"]):
        try:
            r = subprocess.run(
                git_args, cwd=str(project),
                capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=30,
            )
            if r.returncode != 0:
                continue
            diff_text = r.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []
        if diff_text.strip():
            break

    # dogfood P1: 방금 생성된 untracked 파일은 git diff 에 없음 — 의사 diff 합류
    diff_text += untracked_pseudo_diff(project)

    if not diff_text.strip():
        return []

    security_src = HARNESS_HOME / "backend" / "src"
    if str(security_src) not in sys.path:
        sys.path.insert(0, str(security_src))
    try:
        from orchestrator.security_hooks import (  # noqa: PLC0415
            SecurityHooks,
            Severity,
            detect_local_packages,
            strip_doc_files_from_diff,
        )
    except ImportError:
        return []

    # LESSON-030: 문서 diff (.md 산문/인라인 예시) 는 코드 패턴 훅 대상 아님.
    diff_text = strip_doc_files_from_diff(diff_text)

    # Scan added lines only — deleted code (- prefix) must not trigger findings.
    added_text = "\n".join(
        line[1:] for line in diff_text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    if not added_text.strip():
        return []

    # 자기 패키지 import 는 외부 의존성 아님 (LESSON-030)
    local_pkgs = detect_local_packages(project)

    failures: list[str] = []
    seen_modes: set[str] = set()
    for p in get_active_profiles(plan, project):
        if p.id in MOBILE_PROFILE_IDS:
            mode = "mobile"
        elif p.id in FRONTEND_PROFILE_IDS:
            mode = "frontend"
        else:
            mode = "backend"
        if mode in seen_modes:
            continue
        seen_modes.add(mode)
        result = SecurityHooks(extra_python_allowed=local_pkgs).run_all(
            added_text,
            is_frontend=(mode == "frontend"),
            is_mobile=(mode == "mobile"),
        )
        for f in result.findings:
            if f.severity == Severity.BLOCK:
                detail = f" — {f.snippet}" if f.snippet else ""
                failures.append(f"[security:{f.hook}]{detail} {f.message}")
    return failures


_NO_TESTS_PATTERNS: list[re.Pattern[str]] = [
    # pytest: "no tests ran", "no tests found"
    re.compile(r"\bno tests? (found|ran)\b", re.IGNORECASE),
    # jest/vitest: --passWithNoTests, passWithNoTests flag in output
    re.compile(r"pass.{0,5}with.{0,5}no.{0,5}tests", re.IGNORECASE),
    # "0 tests" standalone — but NOT "0 passed, 5 failed" (that has other counts)
    re.compile(r"\b0 tests?\b", re.IGNORECASE),
    # "0 passed" standalone — false-positive guard: skip if digits follow "failed"
    re.compile(r"\b0 passed\b(?!.*\b[1-9]\d* (failed|error))", re.IGNORECASE),
]


def _detect_no_tests_signal(stdout: str) -> bool:
    """stdout 에서 '실제 테스트가 실행되지 않음' 신호 패턴 탐지.

    반환: True 면 no-tests 신호 발견. stdout 만 검사 (stderr 는 빌드 경고 노이즈 제외).
    """
    return any(pattern.search(stdout) for pattern in _NO_TESTS_PATTERNS)


def _run_toolchain_gate(project: Path, plan) -> list[str]:
    """LESSON-021: done 마킹 전 프로파일의 toolchain.test + .lint + .type 전부 실행.

    반환: 실패한 체크 설명 리스트. 비어있으면 통과.
    """
    failures: list[str] = []
    profiles = get_active_profiles(plan, project)
    for i, p in enumerate(profiles):
        path = str(plan.profiles[i].path) if i < len(plan.profiles) else "."
        cwd = str((project / path).resolve()) if path != "." else str(project)
        checks = [
            ("test", p.toolchain.test),
            ("lint", p.toolchain.lint),
            ("type", p.toolchain.type),
        ]
        for name, cmd in checks:
            if not cmd:
                continue
            try:
                # shell=True 근거: 프로파일 toolchain 은 `uv run pytest tests/` 식
                # 여러 토큰 + 옵션 조합이라 shell 해석 필요.
                # 신뢰 소스: `harness/profiles/*.md` frontmatter (레포 내 관리).
                # 사용자 입력이 아니므로 command injection 위험 없음.
                r = subprocess.run(
                    cmd, shell=True, cwd=cwd,
                    capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=300,
                )
                if r.returncode != 0:
                    failures.append(
                        f"[{p.id} @ {path}] {name} 실패 (rc={r.returncode}): {cmd}"
                    )
                # LESSON-021 강화: test 명령에서 no-tests 신호 탐지 (exit 0 이어도 WARN)
                elif name == "test" and _detect_no_tests_signal(
                    r.stdout if isinstance(r.stdout, str) else (r.stdout or b"").decode("utf-8", errors="replace")
                ):
                    info(
                        f"[WARN] LESSON-021 강화: '{cmd}' 출력에 'no tests found' 신호. "
                        f"실제 테스트가 실행되지 않을 가능성 — toolchain.test 검토 필요."
                    )
            except subprocess.TimeoutExpired:
                failures.append(f"[{p.id} @ {path}] {name} 타임아웃 (>5분): {cmd}")
            except FileNotFoundError:
                # shell not found 등 극단 케이스
                failures.append(f"[{p.id} @ {path}] {name} 실행 불가: {cmd}")
    return failures


def cmd_complete(args: argparse.Namespace) -> int:
    plan, plan_path, project = load_plan()
    assert_state(plan, ["planned", "building"], "/ha-build")

    # v0.10.0 HITL gate — frozen_status="drafting" 이면 /ha-build 진입 차단.
    if plan.frozen_status != "frozen" and not args.skip_frozen_gate:
        info(
            "[BLOCK] /ha-build 진입 거부 — frozen_status=drafting (HITL 미완료).\n"
            "  · /ha-design 의 LOCKED 섹션 (requirements/user_journey/view.screens) "
            "인터뷰 채우기 필요.\n"
            "  · 채운 후: /ha-design commit 시 plan.freeze() 가 호출되어 frozen 으로 전이.\n"
            "  · 개발/마이그레이션용 우회: --skip-frozen-gate (의도적 사용 — 비추천)."
        )
        return 1

    try:
        validate_task_id(args.task)
    except ValueError as e:
        info(f"[FAIL] {e}")
        return 2

    if args.status not in ("done", "blocked", "in-progress", "skipped"):
        info(f"[FAIL] --status: done|blocked|in-progress|skipped, 현재 '{args.status}'")
        return 2

    # LESSON-021: done 마킹 전 toolchain 전체 강제 (test + lint + type)
    # skipped/blocked 는 게이트 불필요 — 빌드 안 한 태스크에 검증 무의미.
    # --skip-toolchain 로 opt-out (문서/설계 태스크 등).
    if args.status == "done" and not args.skip_toolchain:
        info("[gate] LESSON-021: toolchain (test/lint/type) 검증 중 …")
        failures = _run_toolchain_gate(project, plan)
        if failures:
            info(f"[BLOCK] toolchain 실패 {len(failures)}건 — done 마킹 거부:")
            for f in failures:
                info(f"  · {f}")
            info("수정 후 재시도하거나, 의도적 skip 이면 --skip-toolchain 명시.")
            return 1
        info("[gate] toolchain 전부 통과")

    if args.status == "done" and not args.skip_security:  # skipped/blocked 는 security gate 불필요
        info("[gate] security_hooks: BLOCK 패턴 검사 중 …")
        sec_failures = _run_security_gate(project, plan)
        if sec_failures:
            info(f"[BLOCK] security_hooks {len(sec_failures)}건 — done 마킹 거부:")
            for f in sec_failures:
                info(f"  · {f}")
            info("위반 수정 후 재시도. 의도적 skip 이면 --skip-security 명시.")
            return 1
        info("[gate] security_hooks 통과 — done 마킹 진행")

    tasks_path = plan_path.parent / "tasks.md"
    text = tasks_path.read_text(encoding="utf-8")

    # 해당 태스크 행의 상태 컬럼만 교체 (B1: 매칭 실패 시 즉시 종료 — plan 갱신 안 함)
    new_text = re.sub(
        rf"(\|\s*{re.escape(args.task)}\s*\|.*?\|.*?\|.*?\|\s*)([^|]+)(\|\s*$)",
        lambda m: f"{m.group(1)}{args.status:<10}{m.group(3)}",
        text, count=1, flags=re.MULTILINE,
    )
    if new_text == text:
        # new_text == text 는 두 경우다: (1) 행이 실제로 없음, (2) 행이 이미
        # args.status 라 re.sub 가 동일 결과 — 멱등 재실행 (이슈 #16). 후자를
        # "행 못 찾음" 으로 오진하면 부분 실패(tasks.md 만 갱신되고 plan/worklog
        # 미기록)에서 복구 경로가 없다. 행 존재 + 상태 일치면 fall-through 해
        # 아래 transition 로직이 plan/worklog 정합을 보충하게 둔다 (write 는 no-op).
        existing = _parse_tasks(text)
        cur = existing.get(args.task)
        if cur is not None and cur["status"].strip().lower() == args.status.strip().lower():
            info(
                f"[idempotent] '{args.task}' 행이 이미 '{args.status}' — "
                "tasks.md 변경 없음, plan/worklog 정합만 보충합니다."
            )
        else:
            info(
                f"[FAIL] tasks.md 에서 태스크 '{args.task}' 행을 찾지 못했습니다.\n"
                f"  · tasks.md 가 수동 편집으로 깨졌거나, T-ID 철자가 다를 수 있습니다.\n"
                f"  · tasks.md 열어 '{args.task}' 행이 올바른 마크다운 테이블 형식인지 확인하세요.\n"
                f"  · tasks.md 경로: {tasks_path}"
            )
            return 1

    try:
        tasks_path.write_text(new_text, encoding="utf-8")
    except OSError as e:
        info(f"[FAIL] tasks.md 쓰기 실패 — plan 갱신 중단: {e}")
        return 1

    # B5: done|완료|completed|skipped → all resolved (built 전이 인정)
    # blocked|in-progress 는 미완료 → building 유지
    tasks = _parse_tasks(new_text)
    statuses = {tid: t["status"].lower() for tid, t in tasks.items()}
    _resolved = {"done", "완료", "completed", "skipped"}
    all_resolved = statuses and all(s in _resolved for s in statuses.values())
    any_done = any(s in ("done", "완료", "completed") for s in statuses.values())

    skipped_ids = sorted(tid for tid, s in statuses.items() if s == "skipped")

    if plan.pipeline.current_step == "planned" and any_done:
        transition(plan, "building", completed_step=f"ha-build:{args.task}")
    if plan.pipeline.current_step == "building" and all_resolved:
        transition(plan, "built", completed_step="ha-build:all-done")
        if skipped_ids:
            # skipped tasks bypass the toolchain/security gates entirely —
            # surface them at the built transition so a skipped core component
            # cannot slip through silently (architecture review F5).
            info(
                f"[WARN] built 전이 — skipped {len(skipped_ids)}개 포함: "
                f"{', '.join(skipped_ids)}\n"
                "  · skipped 태스크는 toolchain/security 게이트를 거치지 않았습니다. "
                "MVP 필수 컴포넌트가 아닌지 확인하세요."
            )
    elif plan.pipeline.current_step == "building":
        # building 유지, completed_steps 만 업데이트 — transition 우회
        completed = list(plan.pipeline.completed_steps)
        step_id = f"ha-build:{args.task}"
        if step_id not in completed:
            completed.append(step_id)
        from src.orchestrator.plan_manager import Pipeline
        plan.pipeline = Pipeline(
            steps=plan.pipeline.steps,
            current_step=plan.pipeline.current_step,
            completed_steps=tuple(completed),
            skipped_steps=plan.pipeline.skipped_steps,
            gstack_mode=plan.pipeline.gstack_mode,
        )

    save_plan(plan, plan_path)

    # v0.10.0 -- worklog 자동 append (done 만, change 카테고리)
    if args.status == "done":
        _log_msg = f"/ha-build complete -- task={args.task}, status=done"
        try:
            subprocess.run(
                [
                    sys.executable,
                    str(Path.home() / ".claude" / "skills" / "ha-log" / "run.py"),
                    "append",
                    "--category", "change",
                    "--message", _log_msg,
                    "--project", str(plan_path.parent.parent),
                ],
                capture_output=True,
                timeout=5,
                check=False,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as _worklog_err:
            info(f"[WARN] worklog append failed (commit 진행): {_worklog_err}")

    output = {
        "task": args.task,
        "new_status": args.status,
        "all_tasks_resolved": all_resolved,
        "skipped_tasks": skipped_ids,
        "current_step": plan.pipeline.current_step,
        "next": "/ha-verify" if all_resolved else "/ha-build <next T-ID>",
    }
    if args.reason:
        output["reason"] = args.reason
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="ha-build")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prepare")
    p.add_argument("--task", required=True, help="T-001 또는 T-001,T-002 (병렬)")
    p.add_argument(
        "--accept-skeleton-drift",
        action="store_true",
        help="skeleton hash mismatch 를 의도적 수동 편집으로 인정하고 진행 (audit trail 누락 감수)",
    )
    p.add_argument(
        "--skip-frozen-gate",
        action="store_true",
        help="HITL frozen_status 게이트 우회 (v0.10.0 — 마이그레이션/개발용. 정상 흐름은 /ha-design freeze 후 진입).",
    )

    c = sub.add_parser("complete")
    c.add_argument("--task", required=True)
    c.add_argument("--status", required=True, choices=["done", "blocked", "in-progress", "skipped"])
    c.add_argument("--reason", default="")
    c.add_argument(
        "--skip-toolchain",
        action="store_true",
        help="LESSON-021 toolchain 게이트 스킵 (문서/설계 태스크 등 의도적일 때만)",
    )
    c.add_argument(
        "--skip-security",
        action="store_true",
        help="security_hooks 게이트 스킵 (의도적 보안 패턴 우회 시에만, toolchain 과 독립)",
    )
    c.add_argument(
        "--skip-frozen-gate",
        action="store_true",
        help="HITL frozen_status 게이트 우회 (v0.10.0 — 마이그레이션/개발용).",
    )

    args = parser.parse_args()
    if args.cmd == "prepare":
        return cmd_prepare(args)
    return cmd_complete(args)


if __name__ == "__main__":
    sys.exit(main())
