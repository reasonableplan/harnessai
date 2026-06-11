#!/usr/bin/env python3
"""HarnessAI v2 — `/ha-verify` 백엔드."""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "_ha_shared"))
from utils import (  # noqa: E402, I001
    HARNESS_HOME,
    MOBILE_PROFILE_IDS as _MOBILE_PROFILE_IDS,
    assert_state,
    get_active_profiles,
    info,
    load_plan,
    record_verify,
    regress,
    resolve_guideline_paths,
    save_plan,
    transition,
)

# backend src import — utils.py 가 backend/ 를 sys.path 에 추가 보장
from src.orchestrator.skeleton_hash import check_skeleton_hash  # noqa: E402

# toolchain 핵심 명령 → 사전 점검할 실행파일
_PROFILE_REQUIRED_CMDS: dict[str, list[tuple[str, str]]] = {
    "flutter": [
        ("flutter", "Flutter SDK 미설치 — https://docs.flutter.dev/get-started/install"),
        ("dart", "Dart SDK 미설치 — Flutter SDK 에 포함됨"),
    ],
    "android-kotlin": [
        ("gradle", "Gradle 미설치 — ./gradlew wrapper 사용 또는 https://gradle.org/install"),
    ],
    "ios-swift": [
        ("swift", "Swift 미설치 — Xcode 설치 필요 (macOS 전용)"),
        ("xcodebuild", "Xcode 미설치 — https://developer.apple.com/xcode"),
    ],
    "react-native-expo": [
        ("node", "Node.js 미설치 — https://nodejs.org"),
    ],
}


def _detect_platform() -> str:
    """현재 플랫폼 문자열 반환. _HA_VERIFY_PLATFORM env 로 테스트 override 가능."""
    override = os.environ.get("_HA_VERIFY_PLATFORM", "").lower()
    if override:
        return override
    return platform.system().lower()  # 'windows', 'darwin', 'linux'


def _check_platform_warnings(profile_id: str, current_platform: str) -> list[str]:
    """profile + platform 조합의 platform_warnings 생성."""
    warnings: list[str] = []

    if profile_id not in _MOBILE_PROFILE_IDS:
        return warnings

    # 1. toolchain 실행파일 존재 여부 점검 (shutil.which)
    for cmd, install_guide in _PROFILE_REQUIRED_CMDS.get(profile_id, []):
        if shutil.which(cmd) is None:
            warnings.append(f"'{cmd}' 명령 미발견 — {install_guide}")
            info(f"[INFO] {profile_id}: '{cmd}' 없음 — {install_guide}")

    # 2. ios-swift on Windows → xcodebuild/swift build 제한 안내
    if profile_id == "ios-swift" and current_platform == "windows":
        warnings.append(
            "Windows host: SwiftLint + swift build dry-run only. "
            "xcodebuild test 는 macOS CI 후속 (GitHub Actions macOS runner 권장)"
        )

    # 3. android-kotlin + JAVA_HOME 없음
    if profile_id == "android-kotlin":
        java_home = os.environ.get("JAVA_HOME", "").strip()
        if not java_home:
            warnings.append(
                "JAVA_HOME 환경변수 필요 — JDK 17+ 설치 후 "
                "JAVA_HOME 을 JDK 경로로 설정 (Gradle 빌드 필수)"
            )

    return warnings


def _run_integrity_check(project: Path) -> dict:
    """G2: harness integrity 를 subprocess 로 실행해 advisory 결과 반환.

    SKILL.md §1.5 가이드: "실패 (exit ≠ 0) 시 중단" — LLM 행동 지침 유지.
    run.py 는 WARN + 결과 정보를 prepare 출력에 포함 (fail-fast 아닌 advisory).
    harness 명령이 없거나 타임아웃 시 skipped=True 로 처리.
    """
    harness_bin = HARNESS_HOME / "harness" / "bin" / "harness"
    if not harness_bin.exists():
        return {"passed": None, "skipped": True, "reason": f"harness 바이너리 없음: {harness_bin}", "output": ""}

    try:
        r = subprocess.run(
            [sys.executable, str(harness_bin), "integrity", "--project", str(project), "--quiet"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        passed = r.returncode == 0
        # Windows + capture_output=True 에서 자식 프로세스가 stderr 를 close 하면
        # r.stdout/r.stderr 가 None 으로 들어오는 케이스 가드 (회귀: 빈 fixture 통합 테스트)
        output = ((r.stdout or "") + (r.stderr or "")).strip()
        if not passed:
            info(
                f"[WARN] harness integrity 실패 (exit {r.returncode}) — skeleton ↔ 실재 FS 불일치 또는 placeholder 잔존.\n"
                "       SKILL.md 가이드: /ha-design 으로 복귀해 skeleton 보완 후 재시도 권장.\n"
                f"       출력:\n{output}"
            )
        return {"passed": passed, "skipped": False, "reason": "", "output": output}
    except subprocess.TimeoutExpired:
        info("[WARN] harness integrity 타임아웃 (>60s) — skeleton 정합성 검사 skip.")
        return {"passed": None, "skipped": True, "reason": "timeout", "output": ""}
    except FileNotFoundError:
        return {"passed": None, "skipped": True, "reason": "python 실행 불가", "output": ""}


def cmd_prepare(args: argparse.Namespace) -> int:
    plan, plan_path, project = load_plan()
    assert_state(plan, ["built"], "/ha-verify")

    profiles = get_active_profiles(plan, project)
    current_platform = _detect_platform()

    # skeleton hash 비교 — 외부 수정 감지 (advisory only)
    skel_path = plan_path.parent / "skeleton.md"
    hash_check = check_skeleton_hash(plan.skeleton_hash, skel_path)
    if not hash_check.skeleton_missing and not hash_check.is_legacy and not hash_check.is_match:
        info(
            "[WARN] skeleton.md 가 마지막 ha-design/ha-redesign 이후 외부에서 수정된 듯합니다 "
            "(hash mismatch). redesign_history 에 audit trail 누락 가능 — "
            "/ha-redesign 으로 변경 사항 추적 권장."
        )

    # G2: harness integrity 게이트 — SKILL.md §1.5 가이드 강제
    integrity_result = _run_integrity_check(project)

    output = {
        "project": str(project),
        "plan_path": str(plan_path),
        "integrity_passed": integrity_result["passed"],
        "integrity_check": integrity_result,
        "profiles": [
            {
                "id": p.id,
                "path": plan.profiles[i].path if i < len(plan.profiles) else ".",
                "cwd": str(project / plan.profiles[i].path) if i < len(plan.profiles) and plan.profiles[i].path != "." else str(project),
                "toolchain": {
                    "install": p.toolchain.install,
                    "test": p.toolchain.test,
                    "lint": p.toolchain.lint,
                    "type": p.toolchain.type,
                    "format": p.toolchain.format,
                },
                "guideline_paths": [str(g) for g in resolve_guideline_paths(p.id)],
                "platform_warnings": _check_platform_warnings(p.id, current_platform),
                "test_dir_warning": _missing_test_dir_warning(
                    (project / plan.profiles[i].path)
                    if i < len(plan.profiles) and plan.profiles[i].path != "."
                    else project,
                    p.toolchain.test,
                ),
            }
            for i, p in enumerate(profiles)
        ],
        "platform_warnings": [
            w
            for i, p in enumerate(profiles)
            for w in _check_platform_warnings(p.id, current_platform)
        ],
        "skeleton_hash_check": {
            "is_match": hash_check.is_match,
            "is_legacy": hash_check.is_legacy,
            "skeleton_missing": hash_check.skeleton_missing,
        },
    }
    for prof in output["profiles"]:
        if prof.get("test_dir_warning"):
            info(f"[WARN] {prof['id']}: {prof['test_dir_warning']}")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def _missing_test_dir_warning(cwd: Path, test_cmd: str | None) -> str | None:
    """toolchain.test 가 가리키는 테스트 디렉토리가 cwd 에 없으면 경고 문자열.

    profile 의 detect path 가 잘못 매칭되면 (예: 루트에 tests/ 를 둔 CLI 프로젝트가
    backend/ 에서 매칭) cwd 에 tests/ 가 없어 'no tests ran' 류 **가짜 FAIL** 이
    verify_history 에 남는다 — 실행 전에 결정론으로 표면화한다.
    """
    if not test_cmd:
        return None
    m = re.search(r"(?:^|[\s=])((?:[\w.-]+/)*tests?)/", test_cmd)
    if m is None:
        return None
    rel = m.group(1)
    if (cwd / rel).exists():
        return None
    parent_candidate = cwd.parent / rel
    hint = (
        f" (상위 {parent_candidate} 에는 존재 — plan 의 profile path 오매칭 가능성)"
        if parent_candidate.exists()
        else ""
    )
    return (
        f"toolchain.test 의 '{rel}/' 디렉토리가 cwd({cwd}) 에 없습니다{hint}. "
        "그대로 실행하면 가짜 FAIL 이 verify_history 에 남습니다 — "
        "harness-plan.md 의 profiles[].path 를 수정하거나 올바른 cwd 에서 실행 후 record 하세요."
    )


def cmd_record(args: argparse.Namespace) -> int:
    plan, plan_path, project = load_plan()
    assert_state(plan, ["built", "verified"], "/ha-verify record")

    passed = args.passed.lower() in ("true", "1", "yes", "y")

    # ── V6: passed=false 시 재작업 T-ID 또는 --no-rework 필수 ───────────
    if not passed:
        rework_tasks_raw = (getattr(args, "rework_tasks", None) or "").strip()
        no_rework: bool = getattr(args, "no_rework", False)
        if not rework_tasks_raw and not no_rework:
            info(
                "[FAIL] /ha-verify record passed=false 거부 — 재작업 T-ID 누락.\n"
                "       SKILL.md 가드레일: passed=false 시 재작업 T-ID 필수.\n"
                '       --rework-tasks "T-001,T-002" 또는 환경 문제로 task 재작업 아니면 --no-rework'
            )
            return 1
        rework_tasks: list[str] = (
            [t.strip() for t in rework_tasks_raw.split(",") if t.strip()]
            if rework_tasks_raw
            else []
        )
    else:
        rework_tasks = []

    # ── 루프 탈출 가드: 동일 T-ID 3회째 FAIL 차단 (architecture review ④) ──
    # "동일 T-ID 2회+ FAIL → /ha-redesign 검토" 가드레일을 결정론으로 강제.
    # build↔verify 무한 왕복(토큰 소모)을 막고 설계 결함 신호를 표면화한다.
    if not passed and rework_tasks and not getattr(args, "force_continue", False):
        prior_fail_counts: dict[str, int] = {}
        for rec in plan.verify_history:
            if getattr(rec, "passed", True) or getattr(rec, "step", "") != "ha-verify":
                continue
            m = re.search(r"\[rework: ([^\]]+)\]", getattr(rec, "summary", "") or "")
            if not m:
                continue
            for tid in (t.strip() for t in m.group(1).split(",")):
                prior_fail_counts[tid] = prior_fail_counts.get(tid, 0) + 1
        third_timers = sorted(
            t for t in rework_tasks if prior_fail_counts.get(t, 0) >= 2
        )
        if third_timers:
            info(
                f"[BLOCK] 동일 태스크 3회째 FAIL: {', '.join(third_timers)} — "
                "구현 재시도가 아니라 설계 결함 신호일 가능성이 높습니다.\n"
                "  · 권장: /ha-redesign 으로 해당 섹션 설계 재검토\n"
                "  · 그래도 재시도하려면: --force-continue 명시"
            )
            return 1

    # summary 에 rework tasks 자동 포함
    summary = args.summary
    if rework_tasks:
        summary = f"{summary} [rework: {', '.join(rework_tasks)}]"

    record_verify(plan, step="ha-verify", passed=passed, summary=summary)

    if passed:
        if plan.pipeline.current_step in ("built",):
            transition(plan, "verified", completed_step="ha-verify")
        # 이미 verified 면 verify_history 에만 추가하고 상태 유지
    else:
        if plan.pipeline.current_step != "building":
            regress(plan, "building")

    save_plan(plan, plan_path)

    output = {
        "passed": passed,
        "summary": summary,
        "current_step": plan.pipeline.current_step,
        "verify_history_count": len(plan.verify_history),
        "rework_tasks": rework_tasks,
        "next": "/ha-review" if passed else f"/ha-build {rework_tasks[0] if rework_tasks else '<T-ID>'} (실패 원인 수정 후)",
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="ha-verify")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prepare")
    r = sub.add_parser("record")
    r.add_argument("--passed", required=True)
    r.add_argument("--summary", required=True)
    r.add_argument(
        "--rework-tasks",
        default="",
        help="재작업 T-ID CSV (예: T-001,T-002). passed=false 시 --no-rework 없으면 필수.",
    )
    r.add_argument(
        "--no-rework",
        action="store_true",
        default=False,
        help="task 재작업 아닌 환경 문제 등으로 rework-tasks 없이 passed=false 허용.",
    )
    r.add_argument(
        "--force-continue",
        action="store_true",
        default=False,
        help="동일 T-ID 3회째 FAIL 가드를 의도적으로 우회하고 재시도 기록.",
    )
    args = parser.parse_args()
    if args.cmd == "prepare":
        return cmd_prepare(args)
    return cmd_record(args)


if __name__ == "__main__":
    sys.exit(main())
