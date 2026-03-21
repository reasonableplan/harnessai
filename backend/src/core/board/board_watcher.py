"""BoardWatcher — GitHub Project Board → DB 주기적 동기화."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

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

            # 변경된 항목의 old_column들을 수집하여 한 번에 조회 (N+1 방지)
            changed_columns: set[str] = set()
            for item in items:
                old_col = self._column_cache.get(item.issue_number)
                if old_col is not None and old_col != item.column:
                    changed_columns.add(old_col)

            # 필요한 컬럼의 태스크를 미리 일괄 조회 (병렬)
            tasks_by_column: dict[str, list] = {}
            failed_columns: set[str] = set()
            if changed_columns:
                cols = list(changed_columns)
                results = await asyncio.gather(
                    *(self._state_store.get_tasks_by_column(c) for c in cols),
                    return_exceptions=True,
                )
                for col, result in zip(cols, results):
                    if isinstance(result, Exception):
                        log.error("Failed to fetch tasks for column", column=col, err=str(result))
                        failed_columns.add(col)
                    else:
                        tasks_by_column[col] = result

            for item in items:
                await self._process_item(item, tasks_by_column, failed_columns)
        finally:
            self._syncing = False

    async def _process_item(self, item, tasks_by_column: dict[str, list], failed_columns: set[str] | None = None) -> None:
        issue_number = item.issue_number
        new_column = item.column
        old_column = self._column_cache.get(issue_number)

        # 첫 sync이거나 컬럼이 변하지 않은 경우 캐시만 갱신하고 조기 반환
        if old_column is None or old_column == new_column:
            self._column_cache[issue_number] = new_column
            return

        # 실패한 컬럼의 아이템은 캐시 갱신하지 않아 다음 사이클에 재시도
        if failed_columns and old_column in failed_columns:
            return

        # 미리 조회한 태스크에서 검색
        tasks = tasks_by_column.get(old_column, [])
        task = next((t for t in tasks if t.github_issue_number == issue_number), None)

        if task:
            # Board에서 컬럼이 바뀐 경우 DB 업데이트 + 메시지 발행 (old_column != new_column은 위에서 보장)
            status_map = {
                "Backlog": "backlog",
                "Ready": "ready",
                "In Progress": "in-progress",
                "Review": "review",
                "Failed": "failed",
                "Done": "done",
            }
            new_status = status_map.get(new_column, "backlog")
            try:
                await self._state_store.update_task(
                    task.id,
                    {"board_column": new_column, "status": new_status},
                )
            except Exception as e:
                log.error("Failed to sync board change to DB, will retry next cycle",
                          issue=issue_number, err=str(e))
                return  # 캐시 갱신하지 않아 다음 사이클에 재시도

            try:
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
                        timestamp=datetime.now(timezone.utc),
                    )
                )
            except Exception as e:
                log.error("Failed to publish board move event", issue=issue_number, err=str(e))
            log.info("Board column changed", issue=issue_number, from_col=old_column, to_col=new_column)

        self._column_cache[issue_number] = new_column
