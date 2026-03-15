"""
Board-first 패턴 헬퍼.
Board(GitHub) 변경을 먼저 수행하고, 실패 시 DB는 그대로 유지.
DB 변경 후 Board 실패 시 DB를 원래 상태로 롤백.
"""
from __future__ import annotations

from typing import Any, Callable

from src.core.logging.logger import get_logger

log = get_logger("BoardThenDb")


async def board_then_db(
    board_fn: Callable,
    db_fn: Callable,
    rollback_fn: Callable | None = None,
    label: str = "operation",
) -> None:
    """
    1. Board(외부) 먼저 변경
    2. DB(내부) 변경
    3. DB 실패 시 Board rollback (rollback_fn 제공 시)
    """
    import asyncio

    # Step 1: Board
    board_result = board_fn()
    if asyncio.iscoroutine(board_result):
        await board_result

    # Step 2: DB
    try:
        db_result = db_fn()
        if asyncio.iscoroutine(db_result):
            await db_result
    except Exception as db_err:
        log.error("DB operation failed after Board success, attempting rollback", label=label, err=str(db_err))
        if rollback_fn is not None:
            try:
                rb_result = rollback_fn()
                if asyncio.iscoroutine(rb_result):
                    await rb_result
                log.info("Board rollback succeeded", label=label)
            except Exception as rb_err:
                log.error("Board rollback also failed — state may be inconsistent", label=label, err=str(rb_err))
        raise
