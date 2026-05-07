"""Task B4: 6 SKILL.md 에 모바일 워크플로우 구체 예시 섹션 존재 검증.

각 SKILL.md 에:
1. "모바일 프로젝트 사용 예시" 섹션 헤더 존재
2. Flutter / react-native / android / ios 키워드 중 하나 이상 포함
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS_DIR = REPO_ROOT / "skills"

SKILL_NAMES = ["ha-init", "ha-design", "ha-plan", "ha-build", "ha-verify", "ha-review"]


@pytest.mark.parametrize("skill_name", SKILL_NAMES)
def test_skill_md_has_mobile_examples_section(skill_name: str) -> None:
    """SKILL.md 에 '모바일 프로젝트 사용 예시' 섹션 헤더 존재."""
    skill_md = SKILLS_DIR / skill_name / "SKILL.md"
    assert skill_md.exists(), f"{skill_md} not found"
    text = skill_md.read_text(encoding="utf-8")
    assert "모바일 프로젝트 사용 예시" in text, (
        f"{skill_name}/SKILL.md 에 '모바일 프로젝트 사용 예시' 섹션 없음"
    )


@pytest.mark.parametrize("skill_name", SKILL_NAMES)
def test_skill_md_has_mobile_keyword(skill_name: str) -> None:
    """SKILL.md 에 Flutter / react-native / android / ios 키워드 중 하나 이상 포함."""
    skill_md = SKILLS_DIR / skill_name / "SKILL.md"
    assert skill_md.exists(), f"{skill_md} not found"
    text = skill_md.read_text(encoding="utf-8").lower()
    mobile_keywords = ["flutter", "react-native", "android", "ios"]
    found = [kw for kw in mobile_keywords if kw in text]
    assert found, (
        f"{skill_name}/SKILL.md 에 모바일 키워드 없음 "
        f"(검색: {mobile_keywords})"
    )
