#!/usr/bin/env python3
"""HarnessAI v2 — `/ha-build` 백엔드."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "_ha_shared"))
from utils import (  # noqa: E402, I001
    BACKEND_PROFILE_IDS,
    FRONTEND_PROFILE_IDS,
    HARNESS_HOME,
    MOBILE_PROFILE_IDS,
    SCAFFOLD_AGENT,
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

from src.orchestrator.plan_manager import requires_hitl_freeze  # noqa: E402

# _matches_detect is module-private in profile_loader but the scaffold
# subcommand needs the exact same detect evaluation ha-plan's T-000 injection
# and deepinit already rely on — same codebase, so importing the private
# helper directly is preferred over duplicating the logic.
from src.orchestrator.profile_loader import _matches_detect  # noqa: E402
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


def _scaffold_commands_for_task(plan, project: Path) -> list[dict[str, str]]:
    """활성 프로파일 중 toolchain.scaffold 보유분의 {profile, path, command} 목록.

    prepare 출력용 (scaffolding-design.md §4) — 실제 detect 재확인/실행은
    `scaffold` 서브커맨드(§3)의 책임이다.
    """
    commands: list[dict[str, str]] = []
    for i, p in enumerate(get_active_profiles(plan, project)):
        if not p.toolchain.scaffold:
            continue
        path = str(plan.profiles[i].path) if i < len(plan.profiles) else "."
        commands.append({"profile": p.id, "path": path, "command": p.toolchain.scaffold})
    return commands


_SCAFFOLD_MERGE_SKIP_DIRS = frozenset({".git", "node_modules"})


def _merge_no_overwrite(src_dir: Path, dst_dir: Path) -> tuple[int, list[str]]:
    """src_dir 산출물을 dst_dir 로 무덮어쓰기 병합 (scaffolding-design.md §3-3).

    - 파일이 dst_dir 에 이미 존재하면 절대 덮지 않고 skipped 에 상대경로 기록.
    - 디렉토리는 재귀 병합 (shutil.move 는 기존 디렉토리를 서브디렉토리로 옮겨버려 사용 불가).
    - `.git`/`node_modules` 는 어느 깊이에서든 이동 대상에서 제외.

    반환: (이동된 파일 수, dst_dir 에 이미 존재해 건너뛴 상대경로 목록 — '/' 구분).
    """
    moved = 0
    skipped: list[str] = []

    def _walk(src: Path, dst: Path, rel: str) -> None:
        nonlocal moved
        dst.mkdir(parents=True, exist_ok=True)
        for entry in sorted(src.iterdir()):
            if entry.name in _SCAFFOLD_MERGE_SKIP_DIRS:
                continue
            entry_rel = f"{rel}/{entry.name}" if rel else entry.name
            target = dst / entry.name
            if entry.is_dir():
                if target.exists() and not target.is_dir():
                    skipped.append(entry_rel)
                    continue
                _walk(entry, target, entry_rel)
            else:
                if target.exists():
                    skipped.append(entry_rel)
                    continue
                shutil.move(str(entry), str(target))
                moved += 1

    _walk(src_dir, dst_dir, "")
    return moved, skipped


# ── 스캐폴드 산출물 결정론 후처리 (subtrack dogfood D-1/D-2) ─────────────────
_SCAFFOLD_SANDBOX_PREFIX = "ha-scaffold-"
_ALLOWBUILDS_PLACEHOLDER = "set this to true or false"


def _npm_safe_name(name: str) -> str:
    """디렉토리명 → npm package name (소문자·허용 문자만·선행 구두점 제거)."""
    safe = re.sub(r"[^a-z0-9._-]+", "-", name.lower()).lstrip("._-").rstrip("-")
    return safe or "app"


def _fix_scaffold_package_name(target: Path) -> None:
    """병합된 package.json 의 샌드박스 임시명(ha-scaffold-*)을 프로젝트 디렉토리명으로 재작성.

    create-next-app 류는 cwd 디렉토리명으로 package name 을 짓는다 — 샌드박스에서
    실행하므로 임시명이 산출물로 샌다 (D-1).
    """
    pkg_path = target / "package.json"
    if not pkg_path.exists():
        return
    try:
        pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        info(f"[WARN] package.json name 재작성 건너뜀 (파싱 실패): {exc}")
        return
    if not isinstance(pkg, dict) or not str(pkg.get("name", "")).startswith(
        _SCAFFOLD_SANDBOX_PREFIX
    ):
        return
    pkg["name"] = _npm_safe_name(target.resolve().name)
    try:
        pkg_path.write_text(
            json.dumps(pkg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        info(f"[INFO] package.json name 재작성: {pkg['name']} (샌드박스 임시명 제거)")
    except OSError as exc:
        info(f"[WARN] package.json name 재작성 실패: {exc}")


def _approve_scaffold_builds(target: Path) -> None:
    """create-next-app 이 남긴 pnpm-workspace.yaml allowBuilds 플레이스홀더를 true 로 승인.

    플레이스홀더가 남으면 pnpm 10+ 이 비대화형 install 을 ERR_PNPM_IGNORED_BUILDS 로
    실패시킨다 (D-2). 갓 생성된 템플릿(플레이스홀더 존재)에만 적용하며, allowBuilds 와
    중복 선언인 ignoredBuiltDependencies 블록은 함께 제거한다.
    """
    ws_path = target / "pnpm-workspace.yaml"
    if not ws_path.exists():
        return
    try:
        text = ws_path.read_text(encoding="utf-8")
    except OSError as exc:
        info(f"[WARN] pnpm-workspace.yaml 읽기 실패 — allowBuilds 승인 건너뜀: {exc}")
        return
    if _ALLOWBUILDS_PLACEHOLDER not in text:
        return
    lines: list[str] = []
    in_ignored = False
    for line in text.splitlines():
        if line.startswith("ignoredBuiltDependencies:"):
            in_ignored = True
            continue
        if in_ignored and (not line.strip() or line.lstrip() != line or line.startswith("-")):
            continue
        in_ignored = False
        lines.append(line.replace(_ALLOWBUILDS_PLACEHOLDER, "true"))
    try:
        ws_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        info("[INFO] pnpm-workspace.yaml allowBuilds 플레이스홀더 승인(true) — 비대화형 install 차단 해제")
    except OSError as exc:
        info(f"[WARN] pnpm-workspace.yaml 쓰기 실패: {exc}")


def _proc_detail(r: subprocess.CompletedProcess[str]) -> str:
    """실패 프로세스의 원인 텍스트 — stderr 와 stdout 둘 다 (pnpm 은 stdout 에 에러를 쓴다, D-3)."""
    return "\n".join(s for s in ((r.stderr or "").strip(), (r.stdout or "").strip()) if s)[-2000:]


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


# Statuses that satisfy a dependency and count as build-complete.
# skipped is terminal (intentionally bypassed) — satisfies dependency + counts as
# build-complete; skipped tasks do NOT re-enter the toolchain/security gates.
_RESOLVED_STATES = ("done", "완료", "completed", "skipped")

# Statuses `ha-build record --status` may write into tasks.md.
# Must stay a subset of tasks_schema.VALID_STATUSES, otherwise a status this
# command writes would be rejected by `ha-plan commit` schema validation.
# A cross-consistency test (test_tasks_schema) guards that invariant.
_RECORD_STATUS_CHOICES = ("done", "blocked", "in-progress", "skipped")


def select_ready_tasks(tasks: dict[str, dict[str, str]]) -> list[str]:
    """지금 빌드 가능한 태스크 ID 목록 (A5 / `--resume`).

    조건: status 가 재구축/대기/in-progress 이고 depends_on 이 전부 resolved.
    정렬: needs_rebuild 먼저(skeleton 변경 반영 우선) → in-progress(부분복구 우선, #7) → 대기,
    각 그룹 내 T-ID 오름차순.
    blocked/skipped/done 은 제외.
    """

    def deps_done(tid: str) -> bool:
        return all(
            tasks.get(dep, {}).get("status", "").strip().lower() in _RESOLVED_STATES
            for dep in tasks[tid]["depends_on"]
        )

    def tid_num(tid: str) -> int:
        return int(tid.split("-")[1])

    needs_rebuild = sorted(
        (t for t in tasks if tasks[t]["status"].strip().lower() in _NEEDS_REBUILD_STATES and deps_done(t)),
        key=tid_num,
    )
    inprogress = sorted(
        (t for t in tasks if tasks[t]["status"].strip().lower() in _INPROGRESS_STATES and deps_done(t)),
        key=tid_num,
    )
    pending = sorted(
        (t for t in tasks if tasks[t]["status"].strip().lower() in _PENDING_STATES and deps_done(t)),
        key=tid_num,
    )
    return needs_rebuild + inprogress + pending


# ── 부분 완료 복구 (issue #7) ────────────────────────────────────────────
# 서브에이전트가 태스크 도중 죽으면 status 가 '대기' 로 남고 부분 산출물이 추적되지
# 않는다. prepare 가 착수 시 in-progress 로 마킹 → 죽으면 그 상태가 보이고, 재진입 시
# 선언 산출 파일 존재 여부로 부분 완료를 알려 "이어서/처음부터" 판단을 돕는다.
_INPROGRESS_STATES = ("in-progress", "진행중")
_PENDING_STATES = ("대기", "pending", "")
_NEEDS_REBUILD_STATES = ("needs_rebuild",)

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


# ── 스텁 스탬퍼 (scaffolding-design.md §5~§6) ────────────────────────────────
# declared_files 경로/네이밍을 LLM 이 놓치는 실수를 "프롬프트 준수 문제"에서
# "물리적으로 불가능"으로 격상 — prepare 가 부재 파일을 마커 스텁으로 선생성한다.
_STUB_MARKER = "HARNESS-STUB"

_COMMENT_SYNTAX: dict[str, tuple[str, str]] = {
    **{ext: ("# ", "") for ext in (".py", ".yml", ".yaml", ".sh")},
    **{
        ext: ("// ", "")
        for ext in (
            ".ts", ".tsx", ".js", ".jsx", ".mjs", ".kt", ".swift", ".dart", ".go", ".rs", ".java",
        )
    },
    **{ext: ("/* ", " */") for ext in (".css", ".scss")},
    **{ext: ("<!-- ", " -->") for ext in (".md", ".html")},
    ".sql": ("-- ", ""),
}


def _stub_content(rel_path: str, tid: str) -> str | None:
    """rel_path 확장자의 주석 문법으로 감싼 스텁 1줄 내용. 스탬프 불가하면 None.

    제외: '/' 로 끝나는 토큰(디렉토리), '*'/'?' 포함(글롭), 매핑에 없는 확장자.
    """
    if rel_path.endswith("/") or "*" in rel_path or "?" in rel_path:
        return None
    syntax = _COMMENT_SYNTAX.get(Path(rel_path).suffix)
    if syntax is None:
        return None
    prefix, suffix = syntax
    return f"{prefix}{_STUB_MARKER} {tid}: ha-build prepare 선생성 스텁 — 구현 시 이 줄 제거{suffix}\n"


def _stamp_declared_files(
    project: Path, declared: list[str], tid: str
) -> tuple[list[str], list[str]]:
    """declared 중 부재 파일을 스텁으로 선생성. 반환: (stamped, unstamped).

    이미 존재하는 파일은 건드리지 않는다 (둘 중 어디에도 포함되지 않음). 부모
    디렉토리는 자동 생성. 개별 파일 OSError 는 in-progress 마킹 실패 처리와
    동일하게 WARN 후 계속.
    """
    stamped: list[str] = []
    unstamped: list[str] = []
    for rel in declared:
        target = project / rel
        if target.exists():
            continue
        content = _stub_content(rel, tid)
        if content is None:
            unstamped.append(rel)
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            stamped.append(rel)
        except OSError as e:
            info(f"[WARN] {tid} 스텁 생성 실패 ({rel}): {e}")
            unstamped.append(rel)
    return stamped, unstamped


def _declared_stub_files(project: Path, declared: list[str]) -> list[str]:
    """declared 중 실존 파일이면서 첫 3줄에 HARNESS-STUB 마커가 남은 상대경로 목록.

    prepare 의 reentry stub_files 보고(§5)와 complete 의 스텁 미구현 게이트(§6) 공용.
    읽기 실패(OSError)는 WARN 후 대상에서 제외 (fail-open — 일시적 FS 오류로 무관한
    태스크까지 막지 않기 위함).
    """
    out: list[str] = []
    for rel in declared:
        target = project / rel
        if not target.exists():
            continue
        try:
            with target.open("r", encoding="utf-8", errors="replace") as f:
                first_lines = [next(f, "") for _ in range(3)]
        except OSError as e:
            info(f"[WARN] 스텁 마커 확인 실패 ({rel}): {e}")
            continue
        if any(_STUB_MARKER in line for line in first_lines):
            out.append(rel)
    return out


def _mark_in_progress(tasks_text: str, tid: str) -> str:
    """tid 행의 status 를 in-progress 로 교체 (착수 마킹). blocked 등은 무변경.

    대상: 대기/pending · needs_rebuild · 이미 완료된 상태(done/skipped).
    완료 태스크의 재진입은 rework (ha-review REJECT 후 재빌드 등) 인데, 상태를
    되돌리지 않으면 all_resolved 가 계속 참이라 배치의 첫 complete 가 곧바로 built
    로 전이하고 나머지 태스크의 complete 가 상태 게이트에 막힌다 — 스텁/toolchain/
    security 게이트를 통과할 기회 자체가 사라진다 (dogfood D-9).
    """
    startable = (*_PENDING_STATES, *_NEEDS_REBUILD_STATES, *_RESOLVED_STATES)

    def repl(m: re.Match[str]) -> str:
        if m.group(2).strip().lower() in startable:
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

    # --resume (A5): --task 미지정 시 다음 ready 태스크 자동 선택. _enter_build_state
    # (상태 회귀 가능) 호출 전에 처리해, ready 가 없을 때 built/verified/reviewed 플랜을
    # 불필요하게 building 으로 회귀시키지 않는다.
    if not args.task and getattr(args, "resume", False):
        _tasks_path = plan_path.parent / "tasks.md"
        if not _tasks_path.exists():
            info(f"[FAIL] tasks.md 없음: {_tasks_path}")
            return 1
        _resume_tasks = _parse_tasks(_tasks_path.read_text(encoding="utf-8"))
        _ready = select_ready_tasks(_resume_tasks)
        if not _ready:
            info("[OK] /ha-build --resume — 빌드할 ready 태스크 없음 (전부 done 또는 의존성 미충족).")
            return 0
        args.task = _ready[0]
        _selected_label = (
            " (재구축)"
            if _resume_tasks[_ready[0]]["status"].strip().lower() in _NEEDS_REBUILD_STATES
            else ""
        )
        info(
            f"[OK] /ha-build --resume — 다음 태스크 자동 선택: {_ready[0]}{_selected_label}\n"
            f"  · ready 큐: {', '.join(_ready)}"
        )

    _enter_build_state(plan, plan_path)

    # v0.10.0 HITL gate — frozen_status="drafting" 이면 /ha-build 진입 차단.
    # /ha-design 의 LOCKED 섹션 (requirements/user_journey/view.screens) 인터뷰 통과 필수.
    if plan.frozen_status != "frozen" and requires_hitl_freeze(plan) and not args.skip_frozen_gate:
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
                "  · 의도적 수동 편집(해시만 재동기)이면: /ha-resync 로 해시 갱신 후 재실행\n"
                "  · 이번만 우회하려면: --accept-skeleton-drift 로 재실행 (해시는 stale 유지)"
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
        info("[FAIL] --task <T-ID> 또는 --task T-001,T-002 필요 (또는 --resume 로 다음 ready 태스크 자동 선택)")
        return 2

    # Validate ID format up front so a malformed --task arg surfaces as a
    # specific format error instead of the generic "task not found" message.
    for tid in target_ids:
        try:
            validate_task_id(tid)
        except ValueError as e:
            info(f"[FAIL] {e}")
            return 2

    # ── scaffold 선행 게이트 (scaffolding-design.md §4) ─────────────────────
    # 미해결 scaffold(T-000) 태스크가 있는데 이번 --task 대상이 아니면 다른 태스크를
    # 먼저 빌드하지 못하게 차단 — 결정론 부트스트랩 없이 코드를 얹으면 file_structure
    # 규약이 어긋난다. --task 로 scaffold 태스크 자신을 지정했으면 통과 (지금 하는 중).
    if not getattr(args, "skip_scaffold_gate", False):
        unresolved_scaffold = [
            tid
            for tid, t in tasks.items()
            if t["agent"] == SCAFFOLD_AGENT
            and t["status"].strip().lower() not in _RESOLVED_STATES
            and tid not in target_ids
        ]
        if unresolved_scaffold:
            info(
                "[BLOCK] T-000 부트스트랩 선행 필요 — 미해결 scaffold 태스크: "
                f"{', '.join(unresolved_scaffold)}\n"
                "  · 먼저 실행: python ~/.claude/skills/ha-build/run.py prepare --task "
                f"{unresolved_scaffold[0]} 후 scaffold --task {unresolved_scaffold[0]}\n"
                "  · 우회하려면(의도적): --skip-scaffold-gate"
            )
            return 1

    # depends_on 만족 검사
    issues: list[str] = []
    for tid in target_ids:
        if tid not in tasks:
            issues.append(f"태스크 '{tid}' 없음 in tasks.md")
            continue
        for dep in tasks[tid]["depends_on"]:
            if dep not in tasks:
                issues.append(f"{tid} depends_on '{dep}' 가 tasks.md 에 없음")
            elif tasks[dep]["status"].lower() not in _RESOLVED_STATES:
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
    no_stamp = getattr(args, "no_stamp", False)
    for tid in target_ids:
        declared = _declared_files(tasks_text, tid)
        existing = [f for f in declared if (project / f).exists()]
        is_reentry = tasks[tid]["status"].strip().lower() in _INPROGRESS_STATES
        is_scaffold = tasks[tid]["agent"] == SCAFFOLD_AGENT
        stamped: list[str] = []
        unstamped: list[str] = []
        stub_files: list[str] = []
        # ── 스텁 스탬퍼 (scaffolding-design.md §5) — 비-reentry·비-scaffold 만 ──
        if is_reentry:
            stub_files = _declared_stub_files(project, declared)
        elif not is_scaffold and not no_stamp:
            stamped, unstamped = _stamp_declared_files(project, declared, tid)
        reentry_info[tid] = {
            "reentry": is_reentry,
            "declared_files": declared,
            "existing_files": existing,
            "stamped_files": stamped,
            "unstamped": unstamped,
            "stub_files": stub_files,
        }
        if is_reentry:
            info(
                f"[WARN] {tid} 이전에 착수됨 (status=in-progress) — 서브에이전트 중단 후 재진입 가능성.\n"
                f"  · 선언 산출 파일 {len(declared)}개 중 {len(existing)}개 존재"
                + (f": {', '.join(existing)}" if existing else "")
                + f"\n  · 스텁 미구현 {len(stub_files)}개"
                + (f": {', '.join(stub_files)}" if stub_files else "")
                + "\n  · 부분 산출물을 점검하고 '이어서' 또는 '처음부터' 결정하세요 (덮어쓰기 주의)."
            )
        else:
            prior = tasks[tid]["status"].strip().lower()
            if prior in _RESOLVED_STATES:
                info(
                    f"[WARN] {tid} 이미 완료됨 (status={prior}) — rework 재진입으로 보고 "
                    "in-progress 로 되돌립니다. 기존 산출 파일은 덮어쓰지 않습니다."
                )
            new_tasks_text = _mark_in_progress(new_tasks_text, tid)
            tasks[tid]["status"] = "in-progress"
    if new_tasks_text != tasks_text:
        try:
            tasks_path.write_text(new_tasks_text, encoding="utf-8")
        except OSError as e:
            info(f"[WARN] in-progress 착수 마킹 실패 (계속 진행): {e}")

    profiles = get_active_profiles(plan, project)

    def _task_entry(tid: str) -> dict:
        entry = {"id": tid, **tasks[tid], **reentry_info[tid]}
        if tasks[tid]["agent"] == SCAFFOLD_AGENT:
            # scaffold 는 Agent 위임 없는 결정론 태스크 — 존재하지 않는
            # agents/scaffold/CLAUDE.md 경로 대신 scaffold_commands 를 제공.
            entry["scaffold"] = True
            entry["scaffold_commands"] = _scaffold_commands_for_task(plan, project)
            entry["guideline_paths"] = []
        else:
            entry["agent_prompt"] = str(
                HARNESS_HOME / "backend" / "agents" / tasks[tid]["agent"] / "CLAUDE.md"
            )
            entry["guideline_paths"] = _agent_to_guideline_paths(tasks[tid]["agent"], plan)
        return entry

    output = {
        "project": str(project),
        "plan_path": str(plan_path),
        "tasks_path": str(tasks_path),
        "tasks": [_task_entry(tid) for tid in target_ids],
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
    not-git repo 는 done 차단 (P0: WARN skip 이면 전체 빌드 기간 보안 훅이
    무력화됨 — workout-app dogfood 에서 13개 태스크 내내 미검사 확인).
    git 미설치는 환경 문제로 WARN 유지. ImportError 시 조용히 skip (CI 환경 등).
    """
    is_repo, git_installed = _is_git_repo(project)
    if not git_installed:
        info(
            "[WARN] /ha-build security_gate skipped — git 명령 미설치.\n"
            "       보안 훅이 git diff 로 변경분을 추출하므로 git 없이는 검사 불가.\n"
            "       권장: git 설치 후 재실행. 의도적 skip 은 --skip-security."
        )
        return []
    if not is_repo:
        # P0: silent/WARN pass → 차단. /ha-init 이 git baseline 을 보장하므로
        # 정상 흐름에서는 도달하지 않음. 의도적 우회는 --skip-security.
        return [
            "[security:gate] git 저장소 아님 — 보안 훅이 git diff 기반이라 검사 불가. "
            f"(project: {project}) "
            '조치: git init && git add -A && git commit -m "initial" 후 재시도, '
            "또는 의도적 skip 이면 --skip-security 명시."
        ]

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
            strip_test_files_from_diff,
        )
    except ImportError:
        return []

    # LESSON-030: 문서 diff (.md 산문/인라인 예시) 는 코드 패턴 훅 대상 아님.
    # LESSON-041: 테스트 픽스처 (파괴적 SQL 시뮬 등) 도 훅 스캔 제외.
    diff_text = strip_doc_files_from_diff(diff_text)
    diff_text = strip_test_files_from_diff(diff_text)

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
    if plan.frozen_status != "frozen" and requires_hitl_freeze(plan) and not args.skip_frozen_gate:
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

    if args.status not in _RECORD_STATUS_CHOICES:
        info(f"[FAIL] --status: {'|'.join(_RECORD_STATUS_CHOICES)}, 현재 '{args.status}'")
        return 2

    tasks_path = plan_path.parent / "tasks.md"
    text = tasks_path.read_text(encoding="utf-8")

    # 스텁 미구현 게이트 (scaffolding-design.md §6) — LESSON-021 toolchain 게이트 앞.
    # skipped/blocked 는 게이트 불필요. 우회 플래그 없음(설계 §6 명시) — 조치는
    # 구현 완료 또는 (스펙상 불필요해진 파일이면) 삭제뿐.
    if args.status == "done":
        stub_remaining = _declared_stub_files(project, _declared_files(text, args.task))
        if stub_remaining:
            info(f"[BLOCK] 스텁 미구현 잔존 {len(stub_remaining)}건 — done 마킹 거부:")
            for f in stub_remaining:
                info(f"  · {f}")
            info("구현 완료 또는 스펙상 불필요해진 파일이면 삭제 후 재시도.")
            return 1
        info("[gate] 스텁 미구현 게이트 통과")

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
    all_resolved = statuses and all(s in set(_RESOLVED_STATES) for s in statuses.values())
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
                    str(Path(__file__).resolve().parent.parent / "ha-log" / "run.py"),
                    "append",
                    "--category", "change",
                    "--message", _log_msg,
                    "--project", str(plan_path.parent.parent),
                ],
                capture_output=True,
                # Windows python 콜드스타트만으로 5s 를 넘겨 일지가 유실됐다 (dogfood D-10).
                timeout=20,
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


def cmd_scaffold(args: argparse.Namespace) -> int:
    """T-000 결정론 스캐폴드 실행 (scaffolding-design.md §3). Agent 위임 없음.

    프로파일별 (toolchain.scaffold 보유 + detect 불일치인 것만):
    샌드박스에서 scaffold 명령 실행 → 무덮어쓰기 병합 → install → detect 재평가.
    이미 detect 를 만족하는 프로파일은 멱등 skip.
    """
    plan, plan_path, project = load_plan()

    try:
        validate_task_id(args.task)
    except ValueError as e:
        info(f"[FAIL] {e}")
        return 2

    tasks_path = plan_path.parent / "tasks.md"
    if not tasks_path.exists():
        info(f"[FAIL] tasks.md 없음: {tasks_path}")
        return 1
    tasks = _parse_tasks(tasks_path.read_text(encoding="utf-8"))
    if args.task not in tasks:
        info(f"[FAIL] 태스크 '{args.task}' 없음 in tasks.md")
        return 1
    if tasks[args.task]["agent"] != SCAFFOLD_AGENT:
        info(
            f"[FAIL] '{args.task}' 는 scaffold 태스크가 아님 "
            f"(agent={tasks[args.task]['agent']!r}, 기대값={SCAFFOLD_AGENT!r})"
        )
        return 2

    results: list[dict[str, object]] = []
    overall_ok = True

    for i, p in enumerate(get_active_profiles(plan, project)):
        if not p.toolchain.scaffold:
            continue
        path = str(plan.profiles[i].path) if i < len(plan.profiles) else "."
        target = project if path == "." else (project / path)
        target.mkdir(parents=True, exist_ok=True)

        if _matches_detect(target, p.detect):
            # 이미 부트스트랩됨 — 멱등 skip (재실행 안전성).
            results.append(
                {"id": p.id, "path": path, "scaffolded": False, "moved": 0, "skipped": [], "install_ok": True}
            )
            continue

        sandbox = Path(tempfile.mkdtemp(prefix=_SCAFFOLD_SANDBOX_PREFIX))
        try:
            try:
                r = subprocess.run(
                    # shell=True 근거: toolchain gate 와 동일 — 프로파일 frontmatter 는
                    # 레포 내 신뢰 소스 (scaffolding-design.md §3).
                    p.toolchain.scaffold, shell=True, cwd=str(sandbox),
                    capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=600,
                )
            except subprocess.TimeoutExpired:
                info(f"[FAIL] {p.id} scaffold 명령 타임아웃 (>10분): {p.toolchain.scaffold}")
                overall_ok = False
                results.append(
                    {"id": p.id, "path": path, "scaffolded": False, "moved": 0, "skipped": [], "install_ok": False}
                )
                continue
            if r.returncode != 0:
                info(
                    f"[FAIL] {p.id} scaffold 명령 실패 (rc={r.returncode}): "
                    f"{p.toolchain.scaffold}\n{_proc_detail(r)}"
                )
                overall_ok = False
                results.append(
                    {"id": p.id, "path": path, "scaffolded": False, "moved": 0, "skipped": [], "install_ok": False}
                )
                continue

            moved, skipped = _merge_no_overwrite(sandbox, target)
            # 결정론 후처리 (D-1/D-2) — 병합 직후, install 전.
            _fix_scaffold_package_name(target)
            _approve_scaffold_builds(target)

            install_ok = True
            if p.toolchain.install:
                try:
                    ir = subprocess.run(
                        p.toolchain.install, shell=True, cwd=str(target),
                        capture_output=True, text=True,
                        encoding="utf-8", errors="replace", timeout=900,
                    )
                    install_ok = ir.returncode == 0
                    if not install_ok:
                        info(
                            f"[FAIL] {p.id} install 실패 (rc={ir.returncode}): "
                            f"{p.toolchain.install}\n{_proc_detail(ir)}"
                        )
                        overall_ok = False
                except subprocess.TimeoutExpired:
                    info(f"[FAIL] {p.id} install 타임아웃 (>15분): {p.toolchain.install}")
                    install_ok = False
                    overall_ok = False

            if not _matches_detect(target, p.detect):
                info(f"[FAIL] {p.id} 스캐폴드 산출물이 profile detect 를 만족하지 않음: {path}")
                overall_ok = False

            results.append(
                {
                    "id": p.id,
                    "path": path,
                    "scaffolded": True,
                    "moved": moved,
                    "skipped": skipped,
                    "install_ok": install_ok,
                }
            )
        finally:
            shutil.rmtree(sandbox, ignore_errors=True)

    output = {
        "task": args.task,
        "profiles": results,
        # 실패 시 done 유도 금지 (D-4) — SKILL 의 "실패면 blocked 처리" 와 정합.
        "next": (
            f"complete --task {args.task} --status done --skip-toolchain"
            if overall_ok
            else "위 [FAIL] 원인 해결 후 scaffold 재실행 (성공 프로파일은 멱등 skip)"
        ),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if overall_ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(prog="ha-build")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prepare")
    p.add_argument("--task", help="T-001 또는 T-001,T-002 (병렬). 생략 시 --resume 필요")
    p.add_argument(
        "--resume",
        action="store_true",
        default=False,
        help="--task 생략 시 다음 ready 태스크(대기/in-progress + depends_on done) 자동 선택",
    )
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
    p.add_argument(
        "--skip-scaffold-gate",
        action="store_true",
        help="T-000 결정론 스캐폴드 선행 게이트 우회 (의도적 사용 — 비추천).",
    )
    p.add_argument(
        "--no-stamp",
        action="store_true",
        help="declared_files 스텁 선생성 건너뛰기 (opt-out — 기본은 스탬프함).",
    )

    s = sub.add_parser("scaffold")
    s.add_argument("--task", required=True, help="scaffold agent 로 배정된 태스크 ID (보통 T-000)")

    c = sub.add_parser("complete")
    c.add_argument("--task", required=True)
    c.add_argument("--status", required=True, choices=list(_RECORD_STATUS_CHOICES))
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
    if args.cmd == "scaffold":
        return cmd_scaffold(args)
    return cmd_complete(args)


if __name__ == "__main__":
    sys.exit(main())
