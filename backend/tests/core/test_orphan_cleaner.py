"""OrphanCleaner 테스트 — Board-first 롤백 로직."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.resilience.orphan_cleaner import ORPHAN_TIMEOUT_MINUTES, OrphanCleaner


def make_task(task_id: str = "t1", github_issue_number: int | None = 42, minutes_ago: int = 60):
    task = MagicMock()
    task.id = task_id
    task.github_issue_number = github_issue_number
    task.started_at = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return task


@pytest.fixture
def state_store():
    store = MagicMock()
    store.get_tasks_by_column = AsyncMock(return_value=[])
    store.update_task = AsyncMock()
    return store


@pytest.fixture
def git_service():
    svc = MagicMock()
    svc.move_issue_to_column = AsyncMock()
    return svc


@pytest.fixture
def cleaner(state_store, git_service):
    return OrphanCleaner(state_store, git_service, interval_s=999)


class TestOrphanCleanerBoardFirst:
    async def test_recent_task_not_rolled_back(self, cleaner, state_store, git_service):
        """타임아웃 이내 태스크는 롤백하지 않는다."""
        task = make_task(minutes_ago=ORPHAN_TIMEOUT_MINUTES - 1)
        state_store.get_tasks_by_column = AsyncMock(return_value=[task])

        await cleaner._clean()

        git_service.move_issue_to_column.assert_not_called()
        state_store.update_task.assert_not_called()

    async def test_board_moved_before_db_update(self, cleaner, state_store, git_service):
        """Board 이동이 DB 업데이트보다 먼저 호출된다 (Board-first)."""
        call_order: list[str] = []
        git_service.move_issue_to_column = AsyncMock(side_effect=lambda *a: call_order.append("board"))
        state_store.update_task = AsyncMock(side_effect=lambda *a, **kw: call_order.append("db"))

        task = make_task()
        state_store.get_tasks_by_column = AsyncMock(return_value=[task])

        await cleaner._clean()

        assert call_order == ["board", "db"]

    async def test_board_move_called_with_ready(self, cleaner, state_store, git_service):
        task = make_task(github_issue_number=99)
        state_store.get_tasks_by_column = AsyncMock(return_value=[task])

        await cleaner._clean()

        git_service.move_issue_to_column.assert_called_once_with(99, "Ready")

    async def test_db_update_skipped_if_board_fails(self, cleaner, state_store, git_service):
        """Board 이동 실패 시 DB 업데이트를 건너뛴다."""
        git_service.move_issue_to_column = AsyncMock(side_effect=RuntimeError("GitHub down"))
        task = make_task()
        state_store.get_tasks_by_column = AsyncMock(return_value=[task])

        await cleaner._clean()

        state_store.update_task.assert_not_called()

    async def test_task_without_issue_number_still_updates_db(self, cleaner, state_store, git_service):
        """github_issue_number가 없는 태스크는 Board 스킵 후 DB만 업데이트한다."""
        task = make_task(github_issue_number=None)
        state_store.get_tasks_by_column = AsyncMock(return_value=[task])

        await cleaner._clean()

        git_service.move_issue_to_column.assert_not_called()
        state_store.update_task.assert_called_once()
        call_args = state_store.update_task.call_args
        assert call_args[0][1]["status"] == "ready"
        assert call_args[0][1]["board_column"] == "Ready"

    async def test_multiple_tasks_independent(self, cleaner, state_store, git_service):
        """Board 실패 태스크는 건너뛰고 나머지는 정상 처리한다."""
        task1 = make_task("t1", github_issue_number=1)
        task2 = make_task("t2", github_issue_number=2)

        async def move_side_effect(issue_number, column):
            if issue_number == 1:
                raise RuntimeError("fail")

        git_service.move_issue_to_column = AsyncMock(side_effect=move_side_effect)
        state_store.get_tasks_by_column = AsyncMock(return_value=[task1, task2])

        await cleaner._clean()

        # t1은 Board 실패로 DB 스킵, t2는 정상 처리
        assert state_store.update_task.call_count == 1
        assert state_store.update_task.call_args[0][0] == "t2"
