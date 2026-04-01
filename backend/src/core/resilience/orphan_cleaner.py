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
                await self._unlock_backlog()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("OrphanCleaner error", err=str(e))

    async def _clean(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=ORPHAN_TIMEOUT_MINUTES)
        in_progress = await self._state_store.get_tasks_by_column("In Progress")
        in_review = await self._state_store.get_tasks_by_column("Review")
        # 두 컬럼에 동일 태스크가 있을 경우 중복 방지
        seen: set[str] = set()
        tasks = []
        for t in in_progress + in_review:
            if t.id not in seen:
                seen.add(t.id)
                tasks.append(t)
        for task in tasks:
            is_orphan = False
            if task.started_at is None:
                log.warning("In-Progress task with no started_at, resetting as orphan", task_id=task.id)
                is_orphan = True
            else:
                started = task.started_at if task.started_at.tzinfo is not None else task.started_at.replace(tzinfo=timezone.utc)
                if started < cutoff:
                    is_orphan = True

            if not is_orphan:
                continue

            log.warning(
                "Rolling back orphaned task to Ready",
                task_id=task.id,
                started_at=task.started_at.isoformat() if task.started_at else "None",
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

    async def _unlock_backlog(self) -> None:
        """의존성이 충족된 backlog 태스크를 ready로 전환한다."""
        all_tasks = await self._state_store.get_all_tasks()
        completed_ids = {t.id for t in all_tasks if t.status in ("done", "skipped")}

        unlock_count = 0
        for t in all_tasks:
            if t.status != "backlog":
                continue
            deps = t.dependencies or []
            if not deps or all(d in completed_ids for d in deps):
                # Board-first: Board 이동 성공 후 DB 업데이트
                if self._git_service and t.github_issue_number:
                    try:
                        await self._git_service.move_issue_to_column(
                            t.github_issue_number, "Ready")
                    except Exception as e:
                        log.warning("Backlog unlock: Board move failed",
                                    task_id=t.id, err=str(e))
                        continue
                await self._state_store.update_task(t.id, {
                    "status": "ready", "board_column": "Ready",
                })
                unlock_count += 1

        if unlock_count:
            log.info("Backlog tasks unlocked", count=unlock_count)
