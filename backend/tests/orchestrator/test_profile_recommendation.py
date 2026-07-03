"""Tests for profile_recommendation — description → ranked profile candidates.

blueprint 흡수(B) 1조각: 비전문가가 스택을 몰라도(unsure) 설명만으로 후보 프로파일을
점수순으로 제시. 코드=결정론 키워드 스코어링, LLM(ha-init 스킬)=이유·트레이드오프 서술.
capability_inference 와 동일 매칭 규약(한국어 substring / 영어 word-boundary).
"""

from __future__ import annotations

from src.orchestrator.profile_recommendation import (
    ProfileRecommendation,
    recommend_profiles,
)


def _ids(recs: list[ProfileRecommendation]) -> list[str]:
    return [r.profile_id for r in recs]


def test_webapp_recommends_nextjs_top() -> None:
    recs = recommend_profiles("로그인 있는 웹앱, 대시보드 화면")
    assert recs[0].profile_id == "nextjs"
    assert recs[0].score > 0
    assert recs[0].signals  # matched signals recorded


def test_backend_api_recommends_backend_top() -> None:
    recs = recommend_profiles("REST API 백엔드 서버, 엔드포인트 여러 개")
    assert recs[0].profile_id == "fastapi"


def test_cli_recommends_python_cli_top() -> None:
    recs = recommend_profiles("명령줄 CLI 자동화 도구")
    assert recs[0].profile_id == "python-cli"


def test_ios_recommends_ios_swift_top() -> None:
    recs = recommend_profiles("아이폰 iOS 앱")
    assert recs[0].profile_id == "ios-swift"


def test_flutter_name_wins() -> None:
    recs = recommend_profiles("플러터로 앱 만들래")
    assert recs[0].profile_id == "flutter"


def test_english_matching_word_boundary() -> None:
    # "app" must match as a word, not inside "application-agnostic"
    recs = recommend_profiles("a cross-platform mobile app with expo")
    assert recs[0].profile_id == "react-native-expo"


def test_empty_description_returns_empty() -> None:
    assert recommend_profiles("") == []
    assert recommend_profiles("   ") == []


def test_no_signal_returns_empty() -> None:
    assert recommend_profiles("무언가 재미있는 것") == []


def test_candidate_restriction() -> None:
    recs = recommend_profiles("모바일 앱", candidate_ids=["nextjs", "react-vite"])
    # mobile signals belong to RN/flutter/etc — none of the restricted web ids match
    assert all(r.profile_id in {"nextjs", "react-vite"} for r in recs)


def test_deterministic_order_and_tiebreak() -> None:
    r1 = recommend_profiles("REST API 서버 백엔드")
    r2 = recommend_profiles("REST API 서버 백엔드")
    assert _ids(r1) == _ids(r2)
    # sorted by score desc; ties broken by profile_id asc
    scores = [r.score for r in r1]
    assert scores == sorted(scores, reverse=True)


def test_only_positive_scores_returned() -> None:
    recs = recommend_profiles("웹앱")
    assert all(r.score > 0 for r in recs)


# --- 오탐 방지: "도구"/"tool" 제거 후 python-cli 동점 오탐 차단 ---


def test_jira_like_web_tool_recommends_nextjs_top() -> None:
    """지라 같은 웹 도구 설명 → nextjs 가 1위, python-cli 는 결과에 없어야 함."""
    desc = "팀에서 이슈랑 할 일을 관리하는 지라 같은 웹 도구. 칸반 보드 포함."
    recs = recommend_profiles(desc)
    assert recs[0].profile_id == "nextjs"
    assert "python-cli" not in _ids(recs)


def test_collaboration_tool_excludes_python_cli() -> None:
    """협업 도구 — python-cli 가 결과에 포함되면 안 됨."""
    recs = recommend_profiles("팀을 위한 협업 도구")
    assert "python-cli" not in _ids(recs)


def test_real_cli_still_matches_python_cli() -> None:
    """진짜 CLI 설명은 여전히 python-cli 를 포함해야 함 (회귀 방지)."""
    recs = recommend_profiles("명령줄 자동화 스크립트")
    assert "python-cli" in _ids(recs)


def test_cli_keyword_still_matches_python_cli() -> None:
    """'cli 도구' 설명에서 cli 신호로 python-cli 가 잡혀야 함 (회귀 방지)."""
    recs = recommend_profiles("cli 도구 만들기")
    assert "python-cli" in _ids(recs)
