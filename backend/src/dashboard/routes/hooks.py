"""GET /api/hooks — 훅 목록 (새 구조에서 미구현, 빈 응답 반환)."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/hooks", tags=["hooks"])


@router.get("")
async def list_hooks() -> list:
    """훅 목록을 반환한다. 새 구조에서 훅 기능은 미구현이므로 빈 리스트를 반환한다."""
    return []
