"""
Orphan Cleaner — 크래시된 에이전트의 in-progress 태스크를 ready로 롤백.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from src.core.logging.logger import get_logger
from src.core.state.state_store import StateStore

log = get_logger("OrphanCleaner")

ORPHAN_TIMEOUT_MINUTES = 30


class OrphanCleaner:
    def __init__(
        self,
        state_store: StateStore,
        git_service: Any,
        interval_s: float = 300.0,
    ) -> None:
        self._state_store = state_store
        self._git_service = git_service
        self._interval_s = interval_s
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._interval_s)
                await self._clean()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("OrphanCleaner error", err=str(e))

    async def _clean(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=ORPHAN_TIMEOUT_MINUTES)
        tasks = await self._state_store.get_tasks_by_column("In Progress")
        for task in tasks:
            if task.started_at and task.started_at < cutoff:
                log.warning(
                    "Rolling back orphaned task to Ready",
                    task_id=task.id,
                    started_at=task.started_at.isoformat(),
                )
                # Board-first: Board 컬럼 변경 후 DB 업데이트
                if task.github_issue_number:
                    try:
                        await self._git_service.move_issue_to_column(
                            task.github_issue_number, "Ready"
                        )
                    except Exception as e:
                        log.error(
                            "OrphanCleaner: Board move failed, skipping DB update",
                            task_id=task.id,
                            err=str(e),
                        )
                        continue
                await self._state_store.update_task(
                    task.id,
                    {"status": "ready", "board_column": "Ready", "started_at": None},
                )
