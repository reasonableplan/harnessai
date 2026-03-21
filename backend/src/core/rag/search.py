"""코드베이스 검색 서비스 — Dense 벡터 검색 + 키워드 필터링."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import FieldCondition, Filter, MatchValue

from src.core.logging.logger import get_logger
from src.core.rag.indexer import COLLECTION_NAME

log = get_logger("CodeSearch")


@dataclass
class SearchResult:
    """검색 결과 하나."""
    file_path: str
    start_line: int
    end_line: int
    content: str
    context: str
    language: str
    score: float


class CodeSearchService:
    """코드베이스 벡터 검색 서비스."""

    def __init__(self, qdrant: QdrantClient, embedding_fn) -> None:
        self._qdrant = qdrant
        self._embed = embedding_fn

    async def search(
        self,
        query: str,
        top_k: int = 5,
        language: str | None = None,
        file_path: str | None = None,
    ) -> list[SearchResult]:
        """쿼리 텍스트로 관련 코드 청크를 검색한다."""
        embeddings = list(self._embed([query]))
        if not embeddings:
            return []

        query_vector = embeddings[0]
        if hasattr(query_vector, "tolist"):
            query_vector = query_vector.tolist()

        # 필터 구성
        conditions = []
        if language:
            conditions.append(
                FieldCondition(key="language", match=MatchValue(value=language))
            )
        if file_path:
            conditions.append(
                FieldCondition(key="file_path", match=MatchValue(value=file_path))
            )

        search_filter = Filter(must=conditions) if conditions else None

        try:
            result = await asyncio.to_thread(
                self._qdrant.query_points,
                collection_name=COLLECTION_NAME,
                query=query_vector,
                limit=top_k,
                query_filter=search_filter,
            )
            hits = result.points
        except (UnexpectedResponse, ConnectionError, TimeoutError) as e:
            log.error("Code search failed", err=str(e))
            return []

        results = []
        for hit in hits:
            payload = hit.payload or {}
            results.append(SearchResult(
                file_path=payload.get("file_path", ""),
                start_line=payload.get("start_line", 0),
                end_line=payload.get("end_line", 0),
                content=payload.get("content", ""),
                context=payload.get("context", ""),
                language=payload.get("language", ""),
                score=hit.score if hit.score is not None else 0.0,
            ))

        log.debug("Code search completed", query=query[:50], results=len(results))
        return results

    async def search_formatted(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.3,
    ) -> str:
        """검색 결과를 LLM 프롬프트에 주입할 수 있는 형태로 반환한다."""
        results = await self.search(query, top_k=top_k)

        # 최소 점수 이하 결과 필터링
        results = [r for r in results if r.score >= min_score]

        if not results:
            return ""

        parts: list[str] = []
        for i, r in enumerate(results, 1):
            parts.append(
                f"<reference id=\"{i}\" file=\"{r.file_path}\" "
                f"lines=\"{r.start_line}-{r.end_line}\" score=\"{r.score:.2f}\">\n"
                f"{r.content}\n"
                f"</reference>"
            )

        return "\n\n".join(parts)
