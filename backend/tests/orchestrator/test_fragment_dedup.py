"""dogfood #6 회귀 테스트: data_model ↔ persistence 스키마 중복 제거 잠금.

실전 결함 (운동관리앱 dogfood 드라이런, 2026-07-05):
- 두 fragment 모두 has.storage 트리거라 항상 동시 활성인데, 둘 다 ERD/스키마/
  인덱스/마이그레이션 서브섹션을 갖고 있어 운전자에게 ERD 이중 작성을 강요.

Fix: data_model = 스키마 단일 소스 (ERD/컬럼/관계/인덱스/마이그레이션 + 관련
decision_points), persistence = 저장소 타입/동시성/파일/백업.
"""

from __future__ import annotations

from pathlib import Path

from src.orchestrator.decision_coverage import load_decision_points

REPO_ROOT = Path(__file__).resolve().parents[3]
FRAGMENTS_DIR = REPO_ROOT / "harness" / "templates" / "skeleton"


def test_persistence_has_no_schema_subsections() -> None:
    """persistence 에 ERD/스키마 서브섹션 재유입 금지 (data_model 이 단일 소스)."""
    body = (FRAGMENTS_DIR / "persistence.md").read_text(encoding="utf-8")
    assert "erDiagram" not in body
    assert "### 스키마 정의" not in body
    assert "### 마이그레이션 전략" not in body


def test_data_model_holds_schema_content() -> None:
    """data_model 이 ERD + 마이그레이션 정책을 보유 (스키마의 집)."""
    body = (FRAGMENTS_DIR / "data_model.md").read_text(encoding="utf-8")
    assert "erDiagram" in body
    assert "### 마이그레이션 정책" in body


def test_decision_points_follow_content() -> None:
    """decision detect 는 섹션 본문 한정이므로 결정 포인트가 내용과 같은 섹션에 있어야 한다."""
    dp = load_decision_points(FRAGMENTS_DIR)
    data_model_ids = {p.point_id for p in dp.get("data_model", [])}
    persistence_ids = {p.point_id for p in dp.get("persistence", [])}
    assert {"multi_tenant", "soft_delete"} <= data_model_ids
    assert "concurrency" in persistence_ids
    # 스키마 결정이 persistence 에 남아 있으면 답을 data_model 에 써도 미해소 오탐.
    assert "soft_delete" not in persistence_ids
    assert "multi_tenant" not in persistence_ids
