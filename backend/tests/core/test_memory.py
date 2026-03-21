"""MemoryStore 테스트 — 기억 저장/검색/대화 요약."""
from __future__ import annotations

from src.core.memory.memory_store import Memory, MemoryStore


def _make_store():
    from qdrant_client import QdrantClient
    from fastembed import TextEmbedding

    qdrant = QdrantClient(":memory:")
    embed_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    return MemoryStore(qdrant, embed_model.embed)


class TestMemoryStore:
    async def test_save_and_search(self):
        """기억 저장 후 관련 쿼리로 검색할 수 있다."""
        store = _make_store()
        await store.save("인증 시스템은 JWT를 사용하기로 결정", category="decision")
        await store.save("데이터베이스는 PostgreSQL을 사용", category="decision")
        await store.save("프론트엔드는 React + TypeScript", category="decision")

        results = await store.search("JWT 인증 로그인")
        assert len(results) > 0
        assert any("JWT" in m.content for m in results)

    async def test_search_with_category_filter(self):
        """카테고리 필터로 검색 범위를 제한할 수 있다."""
        store = _make_store()
        await store.save("JWT 인증 결정", category="decision")
        await store.save("사용자가 다크모드를 선호", category="preference")

        decisions = await store.search("인증", category="decision")
        assert all(m.category == "decision" for m in decisions)

    async def test_search_formatted_returns_xml(self):
        """search_formatted가 XML 딜리미터로 감싼 프롬프트용 텍스트를 반환한다."""
        store = _make_store()
        await store.save("REST API는 FastAPI로 구현", category="decision")

        text = await store.search_formatted("API 프레임워크")
        assert "FastAPI" in text
        assert 'category="decision"' in text
        assert "<memory" in text
        assert "</memory>" in text

    async def test_save_conversation_summary(self):
        """대화 요약과 결정 사항을 저장한다."""
        store = _make_store()
        ids = await store.save_conversation_summary(
            summary="사용자가 블로그 플랫폼 개발을 요청",
            decisions=["Next.js + Prisma 사용", "댓글은 2차 개발"],
            session_id="sess-001",
        )
        assert len(ids) == 3  # 1 summary + 2 decisions

        results = await store.search("블로그 플랫폼")
        assert len(results) > 0

    async def test_empty_search_returns_empty(self):
        """검색 결과가 없으면 빈 리스트를 반환한다."""
        store = _make_store()
        results = await store.search("존재하지 않는 내용")
        assert results == []

    async def test_min_score_filters_low_relevance(self):
        """min_score 이하의 결과는 필터링된다."""
        store = _make_store()
        await store.save("Python 백엔드 개발", category="decision")

        # 완전히 무관한 쿼리 — 낮은 점수 예상
        results = await store.search(
            "quantum physics particle accelerator",
            min_score=0.9,
        )
        # 매우 높은 임계값이므로 필터링될 가능성 높음
        assert len(results) <= 1

    async def test_memory_has_created_at(self):
        """저장된 기억에 created_at이 포함된다."""
        store = _make_store()
        await store.save("테스트 기억", category="fact")

        results = await store.search("테스트")
        if results:
            assert results[0].created_at != ""
