"""dogfood #19/#20 회귀 테스트: ha-design commit 의 '> 작성 가이드' 잔재 검출.

실전 결함 (운동관리앱 dogfood 드라이런, 2026-07-05):
- 운전자가 §11 채울 때 템플릿의 "> 작성 가이드:" 블록을 미제거 → 잔재 예시 텍스트
  (hypothesis/fast-check 등)가 clarify 모호어 검사에서 substring 오탐 연쇄 (#19).
- 스킬 가드레일은 "작성가이드 제거 필수"인데 자동 검출이 없어 운전자 누락에 무방비 (#20).

Fix: cmd_commit 이 _find_guide_residues 로 잔재를 검출하면 BLOCK (exit 1).
tasks/notes 섹션은 placeholder 검사와 동일하게 제외 (이후 스킬이 채움).
"""

from __future__ import annotations

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HA_DESIGN_RUN = REPO_ROOT / "skills" / "ha-design" / "run.py"


@pytest.fixture(scope="module")
def ha_design() -> ModuleType:
    loader = SourceFileLoader("ha_design_guide_residue", str(HA_DESIGN_RUN))
    spec = importlib.util.spec_from_loader("ha_design_guide_residue", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_design_guide_residue"] = mod
    loader.exec_module(mod)
    return mod


def test_guide_residue_detected(ha_design: ModuleType) -> None:
    """잔여 '> 작성 가이드:' 블록 1건 검출."""
    text = (
        "## 11. 테스트 전략\n본문 내용.\n\n"
        "> 작성 가이드:\n"
        "> - property-based: hypothesis/fast-check 사용\n"
    )
    assert len(ha_design._find_guide_residues(text)) == 1


def test_multiple_guide_residues_counted(ha_design: ModuleType) -> None:
    """여러 섹션의 잔재는 각각 집계."""
    text = "> 작성 가이드:\n> - a\n\n본문\n\n> 작성 가이드:\n> - b\n"
    assert len(ha_design._find_guide_residues(text)) == 2


def test_normal_blockquote_not_flagged(ha_design: ModuleType) -> None:
    """일반 인용 블록('> 참고:' 등)은 잔재가 아님."""
    text = "> 참고: prod CORS 와일드카드 금지\n> HITL 규칙: 인터뷰 단계에서만 채움\n"
    assert ha_design._find_guide_residues(text) == []


def test_clean_skeleton_no_residue(ha_design: ModuleType) -> None:
    """가이드가 제거된 skeleton → 잔재 0."""
    text = "## 1. 개요\n운동 기록 앱.\n\n## 2. 스택\nRN + Expo.\n"
    assert ha_design._find_guide_residues(text) == []
