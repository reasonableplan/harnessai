"""BoardWatcher — GitHub Project Board → DB 주기적 동기화."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

from src.core.git_service.git_service import GitService
from src.core.logging.logger import get_logger
from src.core.messaging.message_bus import MessageBus
from src.core.state.state_store import StateStore
from src.core.types import Message, MessageType

log = get_logger("BoardWatcher")

DEFAULT_INTERVAL_S = 15.0


class BoardWatcher:
    def __init__(
        self,
        git_service: GitService,
        state_store: StateStore,
        message_bus: MessageBus,
        interval_s: float = DEFAULT_INTERVAL_S,
    ) -> None:
        self._git_service = git_service
        self._state_store = state_store
        self._message_bus = message_bus
        self._interval_s = interval_s
        self._task: asyncio.Task | None = None
        self._syncing = False
        # issue_number → last known column
        self._column_cache: dict[int, str] = {}

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
                await self._sync()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("BoardWatcher sync error", err=str(e))

    async def _sync(self) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            items = await self._git_service.get_all_project_items()
            for item in items:
                await self._process_item(item)
        finally:
            self._syncing = False

    async def _process_item(self, item) -> None:
        from src.core.types import BoardIssue
        issue_number = item.issue_number
        new_column = item.column
        old_column = self._column_cache.get(issue_number)

        # DB에서 현재 태스크 조회
        tasks = await self._state_store.get_tasks_by_column(old_column or "")
        task = next((t for t in tasks if t.github_issue_number == issue_number), None)

        if task and old_column and old_column != new_column:
            # Board에서 컬럼이 바뀐 경우 DB 업데이트 + 메시지 발행
            status_map = {
                "Backlog": "backlog",
                "Ready": "ready",
                "In Progress": "in-progress",
                "Review": "review",
                "Failed": "failed",
                "Done": "done",
            }
            new_status = status_map.get(new_column, "backlog")
            await self._state_store.update_task(
                task.id,
                {"board_column": new_column, "status": new_status},
            )

            await self._message_bus.publish(
                Message(
                    id=str(uuid.uuid4()),
                    type=MessageType.BOARD_MOVE,
                    from_agent="board-watcher",
                    payload={
                        "issueNumber": issue_number,
                        "from": old_column,
                        "to": new_column,
                        "taskId": task.id,
                    },
                    trace_id=str(uuid.uuid4()),
                    timestamp=datetime.utcnow(),
                )
            )
            log.info("Board column changed", issue=issue_number, from_col=old_column, to_col=new_column)

        self._column_cache[issue_number] = new_column
