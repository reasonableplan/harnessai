"""Coder prompts must not carry hardcoded whitelists (profile = single source).

Regression for the 2026-07-06 audit: all four mobile_coder_* CLAUDE.md files
claimed "(<profile> 프로파일과 동기)" while drifting from the actual profile
whitelist — ios even allowed Apollo/Realm which the ios-swift profile does not
whitelist. The single source is the profile frontmatter delivered to the coder
via ha-build prepare output; prompts must reference it instead of enumerating.

Extended 2026-07-08: backend_coder/frontend_coder kept the same drift class —
frontend allowed jsdom/@testing-library/user-event which the react-vite profile
does not whitelist, and the hardcoded list is wrong wholesale for nextjs.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENTS_DIR = REPO_ROOT / "backend" / "agents"
PROFILES_DIR = REPO_ROOT / "harness" / "profiles"

MOBILE_CODERS = [
    "mobile_coder_rn",
    "mobile_coder_flutter",
    "mobile_coder_android",
    "mobile_coder_ios",
]


@pytest.mark.parametrize("agent", MOBILE_CODERS)
def test_mobile_coder_prompt_references_profile_as_single_source(agent: str) -> None:
    text = (AGENTS_DIR / agent / "CLAUDE.md").read_text(encoding="utf-8")
    # single-source reference must be present
    assert "단일 소스" in text, f"{agent}: whitelist 단일 소스(프로파일) 참조 문구 없음"
    # drift-prone inline enumeration header must be gone
    assert "프로파일과 동기" not in text, f"{agent}: 하드코딩 whitelist 잔존 (drift 원인)"


WEB_CODERS = [
    "backend_coder",
    "frontend_coder",
]


@pytest.mark.parametrize("agent", WEB_CODERS)
def test_web_coder_prompt_references_profile_as_single_source(agent: str) -> None:
    text = (AGENTS_DIR / agent / "CLAUDE.md").read_text(encoding="utf-8")
    assert "단일 소스" in text, f"{agent}: whitelist 단일 소스(프로파일) 참조 문구 없음"
    # drift-prone inline enumeration section must be gone
    assert "## 허용 라이브러리" not in text, f"{agent}: 하드코딩 whitelist 잔존 (drift 원인)"


def test_frontend_prompt_does_not_allow_libs_missing_from_profile() -> None:
    text = (AGENTS_DIR / "frontend_coder" / "CLAUDE.md").read_text(encoding="utf-8")
    profile = (PROFILES_DIR / "react-vite.md").read_text(encoding="utf-8")
    for lib in ("jsdom", "@testing-library/user-event"):
        if lib.lower() not in profile.lower():
            assert lib not in text, (
                f"frontend prompt allows '{lib}' which the react-vite profile does not whitelist"
            )


def test_ios_prompt_does_not_allow_libs_missing_from_profile() -> None:
    text = (AGENTS_DIR / "mobile_coder_ios" / "CLAUDE.md").read_text(encoding="utf-8")
    profile = (PROFILES_DIR / "ios-swift.md").read_text(encoding="utf-8")
    for lib in ("Apollo", "Realm"):
        if lib.lower() not in profile.lower():
            assert lib not in text, (
                f"ios prompt allows '{lib}' which the ios-swift profile does not whitelist"
            )


def test_rn_expo_whitelist_covers_chart_libs() -> None:
    """workout-app dogfood #14: chart libs required a local whitelist bypass."""
    profile = (PROFILES_DIR / "react-native-expo.md").read_text(encoding="utf-8")
    assert "react-native-svg" in profile
    assert "react-native-gifted-charts" in profile
