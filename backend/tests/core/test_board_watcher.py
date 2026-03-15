"""BoardWatcher._process_item 테스트."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.board.board_watcher import BoardWatcher
from src.core.messaging.message_bus import MessageBus


def make_board_issue(issue_number: int, column: str):
    item = MagicMock()
    item.issue_number = issue_number
    item.column = column
    return item


def make_task(task_id: str, issue_number: int):
    task = MagicMock()
    task.id = task_id
    task.github_issue_number = issue_number
    return task


@pytest.fixture
def state_store():
    store = MagicMock()
    store.get_tasks_by_column = AsyncMock(return_value=[])
    store.update_task = AsyncMock()
    store.save_message = AsyncMock()
    return store


@pytest.fixture
def git_service():
    return MagicMock()


@pytest.fixture
def message_bus():
    return MessageBus()


@pytest.fixture
def watcher(git_service, state_store, message_bus):
    return BoardWatcher(git_service, state_store, message_bus, interval_s=999)


class TestProcessItem:
    async def test_first_sync_no_db_query(self, watcher, state_store):
        """첫 sync (old_column=None)에서는 DB 쿼리를 실행하지 않는다."""
        item = make_board_issue(1, "Backlog")
        await watcher._process_item(item)

        state_store.get_tasks_by_column.assert_not_called()
        state_store.update_task.assert_not_called()

    async def test_first_sync_updates_cache(self, watcher):
        """첫 sync는 column_cache만 갱신한다."""
        item = make_board_issue(1, "Backlog")
        await watcher._process_item(item)

        assert watcher._column_cache[1] == "Backlog"

    async def test_same_column_no_db_update(self, watcher, state_store):
        """컬럼이 바뀌지 않으면 DB 업데이트하지 않는다."""
        watcher._column_cache[1] = "Ready"
        item = make_board_issue(1, "Ready")

        await watcher._process_item(item)

        state_store.get_tasks_by_column.assert_not_called()
        state_store.update_task.assert_not_called()

    async def test_column_change_updates_db(self, watcher, state_store):
        """컬럼이 변경되면 DB를 업데이트한다."""
        watcher._column_cache[1] = "Ready"
        task = make_task("t1", 1)
        state_store.get_tasks_by_column = AsyncMock(return_value=[task])

        item = make_board_issue(1, "In Progress")
        await watcher._process_item(item)

        state_store.update_task.assert_called_once_with(
            "t1", {"board_column": "In Progress", "status": "in-progress"}
        )

    async def test_column_change_updates_cache(self, watcher, state_store):
        watcher._column_cache[1] = "Ready"
        task = make_task("t1", 1)
        state_store.get_tasks_by_column = AsyncMock(return_value=[task])

        item = make_board_issue(1, "In Progress")
        await watcher._process_item(item)

        assert watcher._column_cache[1] == "In Progress"

    async def test_unknown_issue_number_no_db_update(self, watcher, state_store):
        """DB에 없는 이슈 번호는 DB 업데이트를 하지 않는다."""
        watcher._column_cache[99] = "Ready"
        state_store.get_tasks_by_column = AsyncMock(return_value=[])

        item = make_board_issue(99, "In Progress")
        await watcher._process_item(item)

        state_store.update_task.assert_not_called()

    async def test_done_column_maps_to_done_status(self, watcher, state_store):
        watcher._column_cache[1] = "Review"
        task = make_task("t1", 1)
        state_store.get_tasks_by_column = AsyncMock(return_value=[task])

        await watcher._process_item(make_board_issue(1, "Done"))

        call_args = state_store.update_task.call_args[0][1]
        assert call_args["status"] == "done"
