"""Profile recommendation — description → ranked candidate profiles.

blueprint 흡수(B)의 1조각: 비전문가가 스택을 몰라도(unsure) 자연어 설명만으로
가장 맞는 프로파일 후보를 점수순으로 제시한다. ha-init 의 프로파일 선택 트리는
사용자가 도메인→플랫폼→프레임워크를 *알아야* 고를 수 있었다 — 이 모듈이 그 진입
장벽을 낮춘다("누구든지"의 실질 상한).

코드/LLM 경계 (HarnessAI 원칙): 이 모듈 = **결정론 키워드 스코어링**(어느 후보를
얼마나 강하게 추천). 이유·트레이드오프 서술은 ha-init 스킬(LLM)이 프로파일 본문을
읽고 담당 — 정적 지식을 데이터로 중복 보관하지 않는다.

매칭 규약은 capability_inference 와 동일: 한국어=substring, 영어=word-boundary.

Entry point: recommend_profiles(description, candidate_ids=None) -> [ProfileRecommendation]
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# profile_id -> 추천 신호 키워드 (한국어 substring + 영어 word-boundary 혼재).
# 신호는 "설명에 이 말이 있으면 이 프로파일일 확률이 높다" 수준의 판별어만 — 너무
# 일반적인 말(파이썬 등, 여러 프로파일 공유)은 노이즈라 제외.
_PROFILE_SIGNALS: dict[str, tuple[str, ...]] = {
    "nextjs": (
        "웹앱",
        "웹",
        "웹사이트",
        "사이트",
        "대시보드",
        "랜딩",
        "풀스택",
        "web",
        "website",
        "webapp",
        "dashboard",
        "saas",
        "ssr",
        "fullstack",
        "landing",
        "nextjs",
    ),
    "react-vite": (
        "싱글페이지",
        "관리자",
        "어드민",
        "내부 도구",
        "대시보드",
        "spa",
        "admin",
        "dashboard",
        "vite",
    ),
    "fastapi": (
        "서버",
        "백엔드",
        "엔드포인트",
        "api",
        "rest",
        "backend",
        "endpoint",
        "fastapi",
    ),
    "nestjs": (
        "서버",
        "백엔드",
        "api",
        "backend",
        "nest",
        "nestjs",
        "node",
    ),
    "django": (
        "장고",
        "관리자 페이지",
        "django",
        "orm",
    ),
    "python-cli": (
        "명령줄",
        "명령어",
        "터미널",
        "자동화",
        "도구",
        "스크립트",
        "cli",
        "command",
        "terminal",
        "script",
        "automation",
        "tool",
    ),
    "python-lib": (
        "라이브러리",
        "패키지",
        "모듈",
        "유틸",
        "library",
        "package",
        "sdk",
        "module",
        "util",
    ),
    "claude-skill": (
        "스킬",
        "클로드 스킬",
        "skill",
        "claude skill",
    ),
    "electron": (
        "데스크톱",
        "데스크탑",
        "트레이",
        "일렉트론",
        "desktop",
        "electron",
        "tray",
    ),
    "react-native-expo": (
        "모바일",
        "앱",
        "크로스플랫폼",
        "리액트 네이티브",
        "엑스포",
        "mobile",
        "app",
        "expo",
        "react native",
        "cross-platform",
        "rn",
    ),
    "flutter": (
        "플러터",
        "다트",
        "flutter",
        "dart",
    ),
    "android-kotlin": (
        "안드로이드",
        "코틀린",
        "android",
        "kotlin",
    ),
    "ios-swift": (
        "아이폰",
        "애플",
        "스위프트",
        "ios",
        "iphone",
        "swift",
        "apple",
    ),
}


@dataclass(frozen=True)
class ProfileRecommendation:
    """A scored profile candidate derived from the description.

    profile_id: recommended profile.
    score:      number of distinct matched signals (higher = stronger fit).
    signals:    the matched keywords, in declaration order (for user-facing근거).
    """

    profile_id: str
    score: int
    signals: tuple[str, ...]


def _matched_signals(keywords: tuple[str, ...], text: str, lowered: str) -> tuple[str, ...]:
    """Return the subset of keywords present in the description.

    ASCII keyword → word-boundary match on lowercased text (avoids 'app' inside
    'application'). Non-ASCII (Korean) → plain substring (no case, no boundary).
    """
    hits: list[str] = []
    for kw in keywords:
        if kw.isascii():
            if re.search(rf"\b{re.escape(kw)}\b", lowered):
                hits.append(kw)
        elif kw in text:
            hits.append(kw)
    return tuple(hits)


def recommend_profiles(
    description: str,
    candidate_ids: list[str] | None = None,
) -> list[ProfileRecommendation]:
    """Rank profiles by how strongly the description signals each one.

    Args:
        description: user's natural-language project description.
        candidate_ids: if given, restrict scoring to these profile ids.

    Returns:
        ProfileRecommendation list, score-desc then profile_id-asc (deterministic),
        including only profiles with at least one matched signal. Empty list when
        description is blank or nothing matches.
    """
    if not description or not description.strip():
        return []
    lowered = description.lower()

    ids = (
        [pid for pid in candidate_ids if pid in _PROFILE_SIGNALS]
        if candidate_ids is not None
        else list(_PROFILE_SIGNALS)
    )

    recs: list[ProfileRecommendation] = []
    for pid in ids:
        hits = _matched_signals(_PROFILE_SIGNALS[pid], description, lowered)
        if hits:
            recs.append(ProfileRecommendation(profile_id=pid, score=len(hits), signals=hits))

    recs.sort(key=lambda r: (-r.score, r.profile_id))
    return recs
