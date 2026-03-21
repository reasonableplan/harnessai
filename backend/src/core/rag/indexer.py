"""코드 청크를 Qdrant 벡터DB에 인덱싱한다."""
from __future__ import annotations

import asyncio
import hashlib
import uuid
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
    VectorParams,
)

from src.core.logging.logger import get_logger
from src.core.rag.chunker import CodeChunk, scan_workspace
from src.core.resilience.api_retry import with_retry

log = get_logger("CodebaseIndexer")

COLLECTION_NAME = "codebase"
EMBEDDING_DIM = 384  # fastembed BAAI/bge-small-en-v1.5 기본 차원


class CodebaseIndexer:
    """워크스페이스 파일을 벡터DB에 인덱싱한다."""

    def __init__(self, qdrant: QdrantClient, embedding_fn) -> None:
        self._qdrant = qdrant
        self._embed = embedding_fn
        self._indexed_hashes: set[str] = set()
        self._collection_ready = False

    async def ensure_collection(self) -> None:
        """컬렉션이 없으면 생성한다."""
        if self._collection_ready:
            return
        result = await with_retry(
            lambda: asyncio.to_thread(self._qdrant.get_collections),
            max_retries=3, label="Qdrant get_collections",
        )
        if not any(c.name == COLLECTION_NAME for c in result.collections):
            await with_retry(
                lambda: asyncio.to_thread(
                    self._qdrant.create_collection,
                    collection_name=COLLECTION_NAME,
                    vectors_config=VectorParams(
                        size=EMBEDDING_DIM,
                        distance=Distance.COSINE,
                    ),
                ),
                max_retries=3, label="Qdrant create_collection",
            )
            log.info("Qdrant collection created", collection=COLLECTION_NAME)
        self._collection_ready = True

    async def index_workspace(self, work_dir: Path) -> int:
        """워크스페이스 전체를 스캔하여 인덱싱한다. 반환: 인덱싱된 청크 수."""
        await self.ensure_collection()

        chunks = scan_workspace(work_dir)
        if not chunks:
            log.info("No files to index", work_dir=str(work_dir))
            return 0

        # 이미 인덱싱된 청크는 건너뛴다 (content hash 기반)
        new_chunks = [c for c in chunks if self._content_hash(c) not in self._indexed_hashes]
        if not new_chunks:
            log.info("All chunks already indexed", total=len(chunks))
            return 0

        points = self._chunks_to_points(new_chunks)
        if points:
            # 배치 upsert (100개씩)
            for i in range(0, len(points), 100):
                batch = points[i : i + 100]
                await with_retry(
                    lambda b=batch: asyncio.to_thread(
                        self._qdrant.upsert, collection_name=COLLECTION_NAME, points=b,
                    ),
                    max_retries=3, label="Qdrant upsert",
                )

        for c in new_chunks:
            self._indexed_hashes.add(self._content_hash(c))

        log.info("Codebase indexed", new_chunks=len(new_chunks), total=len(chunks))
        return len(new_chunks)

    async def reindex_files(self, work_dir: Path, file_paths: list[str]) -> int:
        """변경된 파일만 재인덱싱한다 (incremental)."""
        from src.core.rag.chunker import chunk_file

        await self.ensure_collection()

        all_new: list[CodeChunk] = []
        work_dir = work_dir.resolve()

        for rel_path in file_paths:
            abs_path = (work_dir / rel_path).resolve()
            if not abs_path.is_relative_to(work_dir):
                log.warning("Path traversal blocked in reindex", path=rel_path)
                continue
            if not abs_path.exists():
                continue

            # 해당 파일의 기존 청크 삭제
            await with_retry(
                lambda rp=rel_path: asyncio.to_thread(
                    self._qdrant.delete,
                    collection_name=COLLECTION_NAME,
                    points_selector=FilterSelector(
                        filter=Filter(
                            must=[FieldCondition(key="file_path", match=MatchValue(value=rp))]
                        )
                    ),
                ),
                max_retries=3, label="Qdrant delete",
            )
            # 기존 해시 제거
            self._indexed_hashes = {
                h for h in self._indexed_hashes
                if not h.startswith(rel_path + ":")
            }

            new_chunks = chunk_file(abs_path, work_dir)
            all_new.extend(new_chunks)

        if all_new:
            points = self._chunks_to_points(all_new)
            for i in range(0, len(points), 100):
                batch = points[i : i + 100]
                await with_retry(
                    lambda b=batch: asyncio.to_thread(
                        self._qdrant.upsert, collection_name=COLLECTION_NAME, points=b,
                    ),
                    max_retries=3, label="Qdrant upsert",
                )

            for c in all_new:
                self._indexed_hashes.add(self._content_hash(c))

        log.info("Files reindexed", files=len(file_paths), chunks=len(all_new))
        return len(all_new)

    def _chunks_to_points(self, chunks: list[CodeChunk]) -> list[PointStruct]:
        """청크 리스트를 Qdrant PointStruct 리스트로 변환한다."""
        # 임베딩 텍스트: context + content
        texts = [f"{c.context}\n{c.content}" for c in chunks]
        try:
            embeddings = list(self._embed(texts))
        except Exception as e:
            log.error("Embedding failed", chunk_count=len(texts), err=str(e))
            return []

        points = []
        for chunk, vector in zip(chunks, embeddings):
            points.append(PointStruct(
                id=str(uuid.uuid4()),
                vector=vector.tolist() if hasattr(vector, "tolist") else list(vector),
                payload={
                    "file_path": chunk.file_path,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "content": chunk.content,
                    "context": chunk.context,
                    "language": chunk.language,
                    "content_hash": self._content_hash(chunk),
                },
            ))
        return points

    @staticmethod
    def _content_hash(chunk: CodeChunk) -> str:
        return f"{chunk.file_path}:{hashlib.sha256(chunk.content.encode()).hexdigest()[:16]}"
