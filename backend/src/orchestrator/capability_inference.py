"""capability_inference — 자연어 설명에서 has.* 신호를 추론 (P5 인터뷰 지능화).

6축(capabilities.derive_axes_capabilities) 과 프로파일 선언(compute_has_keys)이
못 잡는 capability 를, 사용자 설명 텍스트의 키워드로 감지한다. 목적: 비전문가가
"할 일 관리 앱" 이라고만 써도 storage(→persistence/data_model) 가 빠지지 않도록
**제안**한다. 자동 활성화가 아니라 제안 — ha-init 이 사용자에게 확인(HITL, 결정권 분리).

결정론적 키워드 매핑 (한국어 + 영어). 오탐을 줄이려 강한 신호 위주로 선별.
"""

from __future__ import annotations

import re

# atom → (한국어 substring 키워드, 영어 단어경계 키워드).
# 한국어는 어절 경계가 없어 substring, 영어는 단어경계(\b) 로 오탐 억제.
# 모든 atom 은 capabilities.KNOWN_CAPABILITY_ATOMS 의 멤버여야 한다
# (test_only_returns_known_atoms 가 강제).
_KEYWORDS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "storage": (
        # "관리" is broad but "X 관리 앱/도구/시스템" almost always implies persistence;
        # rare false-positives (e.g. "상태 관리") are caught by HITL confirmation.
        (
            "저장",
            "데이터베이스",
            "데이터",
            "목록",
            "기록",
            "히스토리",
            "영속",
            "관리",
            "이슈",
            "할 일",
            "할일",
            "태스크",
            "작업",
            "항목",
            "등록",
            "조회",
            "댓글",
            "게시",
            "메모",
            "노트",
            "예약",
            "주문",
        ),
        (
            "crud",
            "database",
            "persist",
            "persistence",
            "manage",
            "track",
            "todo",
            "task",
            "issue",
            "note",
        ),
    ),
    "users": (
        (
            "로그인",
            "계정",
            "회원",
            "사용자",
            "유저",
            "인증",
            "권한",
            "담당자",
            "멤버",
            "팀원",
            "작성자",
        ),
        ("login", "account", "signup", "signin", "auth", "member", "assignee"),
    ),
    "http_server": (
        ("엔드포인트", "서버"),
        ("api", "rest", "endpoint", "webhook"),
    ),
    "ui": (
        ("화면", "페이지", "웹앱", "대시보드", "버튼", "폼"),
        ("dashboard", "frontend", "webapp"),
    ),
}


def infer_capabilities_from_text(text: str) -> dict[str, list[str]]:
    """설명 텍스트에서 has.* atom 을 추론.

    Returns:
        {atom: [매칭된 키워드...]} — 근거 키워드를 함께 반환해 사용자에게 이유를
        보여줄 수 있게 한다. 신호 없으면 빈 dict.
    """
    if not text or not text.strip():
        return {}
    lowered = text.lower()
    result: dict[str, list[str]] = {}
    for atom, (ko_words, en_words) in _KEYWORDS.items():
        hits: list[str] = []
        for kw in ko_words:
            if kw in text:  # 한국어: substring
                hits.append(kw)
        for kw in en_words:
            if re.search(rf"\b{re.escape(kw)}\b", lowered):  # 영어: 단어경계
                hits.append(kw)
        if hits:
            result[atom] = hits
    return result
