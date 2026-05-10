#!/usr/bin/env python3
"""HarnessAI v2 — `/ha-verify` 백엔드."""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "_ha_shared"))
from utils import (  # noqa: E402
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


def cmd_prepare(args: argparse.Namespace) -> int:
    plan, plan_path, project = load_plan()
    assert_state(plan, ["built"], "/ha-verify")

    profiles = get_active_profiles(plan, project)
    current_platform = _detect_platform()

    output = {
        "project": str(project),
        "plan_path": str(plan_path),
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
            }
            for i, p in enumerate(profiles)
        ],
        "platform_warnings": [
            w
            for i, p in enumerate(profiles)
            for w in _check_platform_warnings(p.id, current_platform)
        ],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    plan, plan_path, project = load_plan()
    assert_state(plan, ["built", "verified"], "/ha-verify record")

    passed = args.passed.lower() in ("true", "1", "yes", "y")

    record_verify(plan, step="ha-verify", passed=passed, summary=args.summary)

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
        "summary": args.summary,
        "current_step": plan.pipeline.current_step,
        "verify_history_count": len(plan.verify_history),
        "next": "/ha-review" if passed else "/ha-build <T-ID> (실패 원인 수정 후)",
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
    args = parser.parse_args()
    if args.cmd == "prepare":
        return cmd_prepare(args)
    return cmd_record(args)


if __name__ == "__main__":
    sys.exit(main())
