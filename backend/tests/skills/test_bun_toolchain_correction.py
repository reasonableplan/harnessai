"""V3 회귀 테스트: react-native-expo profile 의 toolchain.test 정확성.

bun test  ≠ bun run test:
- `bun test`     → bun 내장 test runner (jest 와 별개, 항상 내장 runner 실행)
- `bun run test` → package.json scripts.test 실행 (RN/Expo 프로젝트의 jest 실행 경로)

pnpm 은 `pnpm test` = `pnpm run test` 별칭이라 문제 없지만,
bun 은 별칭이 아니므로 `bun test` 직접 지정 시 jest 가 한 번도 안 돌고
toolchain gate 가 모두 통과되는 silent fail 이 발생한다.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HARNESS_DIR = REPO_ROOT / "harness"


def _load_profile_loader():
    """ProfileLoader 를 import. harness/ 없으면 skip."""
    if not HARNESS_DIR.exists():
        pytest.skip("harness/ 디렉토리 없음")
    from src.orchestrator.profile_loader import ProfileLoader  # noqa: PLC0415
    return ProfileLoader


def test_react_native_expo_toolchain_test_is_bun_run_test() -> None:
    """react-native-expo toolchain.test 는 반드시 'bun run test' 여야 한다.

    'bun test' 는 bun 내장 runner 를 직접 실행하므로 package.json scripts.test (jest)
    를 호출하지 않는다. RN/Expo 프로젝트에서 'bun test' 사용 시 jest 가 실행되지 않아
    toolchain gate 가 silent pass 되는 결함이 발생한다 (챙겼니 dogfood 발견).
    """
    ProfileLoader = _load_profile_loader()
    profile_md = HARNESS_DIR / "profiles" / "react-native-expo.md"
    if not profile_md.exists():
        pytest.skip("react-native-expo.md 없음")

    loader = ProfileLoader(harness_dir=HARNESS_DIR)
    profile = loader.load("react-native-expo")

    # 핵심 assertion: bun test 가 아니라 bun run test
    assert profile.toolchain.test == "bun run test", (
        f"toolchain.test='{profile.toolchain.test}' — "
        "'bun test' 는 bun 내장 runner (jest 미실행). "
        "package.json scripts.test (jest) 경유는 'bun run test' 여야 함."
    )


def test_react_native_expo_toolchain_test_is_not_bare_bun_test() -> None:
    """'bun test' 문자열이 toolchain.test 에 그대로 없는지 확인 (의도 명시 테스트)."""
    ProfileLoader = _load_profile_loader()
    profile_md = HARNESS_DIR / "profiles" / "react-native-expo.md"
    if not profile_md.exists():
        pytest.skip("react-native-expo.md 없음")

    loader = ProfileLoader(harness_dir=HARNESS_DIR)
    profile = loader.load("react-native-expo")

    assert profile.toolchain.test != "bun test", (
        "toolchain.test 가 'bun test' 로 되어 있음. "
        "bun 내장 runner 가 호출되어 jest 테스트가 실행되지 않는다. "
        "'bun run test' 로 수정 필요."
    )


def test_other_bun_profile_toolchain_install_unchanged() -> None:
    """react-native-expo 의 install 명령은 여전히 'bun install' 이어야 한다 (수정 스코프 확인)."""
    ProfileLoader = _load_profile_loader()
    profile_md = HARNESS_DIR / "profiles" / "react-native-expo.md"
    if not profile_md.exists():
        pytest.skip("react-native-expo.md 없음")

    loader = ProfileLoader(harness_dir=HARNESS_DIR)
    profile = loader.load("react-native-expo")

    assert profile.toolchain.install == "bun install"
