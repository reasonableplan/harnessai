"""capability_inference 단위 테스트 — 설명 텍스트 → has.* 신호 추론 (P5 #11).

비전문가의 자연어 설명에서 프로파일/6축이 못 잡는 capability 를 감지해 제안한다.
자동 활성화가 아니라 제안 — ha-init 이 사용자에게 확인(HITL).
"""

from __future__ import annotations

from src.orchestrator.capabilities import KNOWN_CAPABILITY_ATOMS
from src.orchestrator.capability_inference import infer_capabilities_from_text


def test_crud_korean_implies_storage() -> None:
    inferred = infer_capabilities_from_text("할 일 CRUD, 마감/우선순위 관리")
    assert "storage" in inferred
    assert inferred["storage"]  # evidence keywords non-empty


def test_database_english_implies_storage() -> None:
    assert "storage" in infer_capabilities_from_text("a todo app backed by a database")


def test_login_implies_users() -> None:
    inferred = infer_capabilities_from_text("계정 로그인 후 개인 데이터 접근")
    assert "users" in inferred
    assert "storage" in inferred  # 데이터 → storage 도


def test_api_implies_http_server() -> None:
    assert "http_server" in infer_capabilities_from_text("REST API 엔드포인트 제공")


def test_screen_implies_ui() -> None:
    assert "ui" in infer_capabilities_from_text("대시보드 화면에서 목록을 본다")


def test_pure_computation_infers_nothing() -> None:
    """저장/사용자/화면 신호 없는 순수 계산 설명 → 빈 결과."""
    assert infer_capabilities_from_text("두 숫자를 더하는 계산기 함수") == {}


def test_empty_text_returns_empty() -> None:
    assert infer_capabilities_from_text("") == {}
    assert infer_capabilities_from_text("   ") == {}


def test_only_returns_known_atoms() -> None:
    """추론된 모든 atom 은 KNOWN_CAPABILITY_ATOMS 의 부분집합이어야 한다."""
    inferred = infer_capabilities_from_text(
        "로그인 계정, 할 일 데이터베이스 CRUD, REST API, 대시보드 화면"
    )
    assert set(inferred) <= KNOWN_CAPABILITY_ATOMS


def test_case_insensitive() -> None:
    assert "storage" in infer_capabilities_from_text("A TODO app with a DATABASE")
