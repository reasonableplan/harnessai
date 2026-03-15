"""DirectorAgent._handle_review 테스트 — Board-first 원칙."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.director.director_agent import DirectorAgent
from src.core.messaging.message_bus import MessageBus
from src.core.types import AgentConfig, AgentLevel, Message, MessageType, TaskStatus


def make_director(state_store, git_service, llm_client=None):
    if llm_client is None:
        llm_client = MagicMock()
        llm_client.chat = AsyncMock(return_value=("create_epic", 0, 0))
    config = AgentConfig(id="director", domain="director", level=AgentLevel.DIRECTOR)
    bus = MessageBus()
    return DirectorAgent(
        config=config,
        message_bus=bus,
        state_store=state_store,
        git_service=git_service,
        llm_client=llm_client,
    )


def make_review_message(task_id: str, success: bool) -> Message:
    import uuid
    from datetime import datetime, timezone
    return Message(
        id=str(uuid.uuid4()),
        type=MessageType.REVIEW_REQUEST,
        from_agent="agent-backend",
        payload={"taskId": task_id, "result": {"success": success}},
        trace_id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def state_store():
    store = MagicMock()
    store.update_task = AsyncMock()
    store.get_all_agents = AsyncMock(return_value=[])
    store.get_all_tasks = AsyncMock(return_value=[])
    store.save_message = AsyncMock()
    store.get_agent_config = AsyncMock(return_value=None)
    return store


@pytest.fixture
def git_service():
    svc = MagicMock()
    svc.move_issue_to_column = AsyncMock()
    return svc


@pytest.fixture
def director(state_store, git_service):
    return make_director(state_store, git_service)


class TestHandleReview:
    async def test_approved_moves_board_to_done(self, director, state_store, git_service):
        """승인 시 Board를 Done으로 이동한다."""
        task = MagicMock()
        task.github_issue_number = 42
        state_store.get_task = AsyncMock(return_value=task)

        msg = make_review_message("t1", success=True)
        await director._handle_review(msg)

        git_service.move_issue_to_column.assert_called_once_with(42, "Done")

    async def test_rejected_moves_board_to_ready(self, director, state_store, git_service):
        """거절 시 Board를 Ready로 이동한다."""
        task = MagicMock()
        task.github_issue_number = 42
        state_store.get_task = AsyncMock(return_value=task)

        msg = make_review_message("t1", success=False)
        await director._handle_review(msg)

        git_service.move_issue_to_column.assert_called_once_with(42, "Ready")

    async def test_board_first_order(self, director, state_store, git_service):
        """Board 이동이 DB 업데이트보다 먼저 호출된다."""
        call_order: list[str] = []
        git_service.move_issue_to_column = AsyncMock(side_effect=lambda *a: call_order.append("board"))
        state_store.update_task = AsyncMock(side_effect=lambda *a, **kw: call_order.append("db"))

        task = MagicMock()
        task.github_issue_number = 1
        state_store.get_task = AsyncMock(return_value=task)

        await director._handle_review(make_review_message("t1", success=True))

        assert call_order == ["board", "db"]

    async def test_board_failure_skips_db_update(self, director, state_store, git_service):
        """Board 이동 실패 시 DB 업데이트를 건너뛴다."""
        git_service.move_issue_to_column = AsyncMock(side_effect=RuntimeError("GitHub down"))
        task = MagicMock()
        task.github_issue_number = 1
        state_store.get_task = AsyncMock(return_value=task)

        await director._handle_review(make_review_message("t1", success=True))

        state_store.update_task.assert_not_called()

    async def test_approved_sets_done_status(self, director, state_store, git_service):
        state_store.get_task = AsyncMock(return_value=MagicMock(github_issue_number=None))

        await director._handle_review(make_review_message("t1", success=True))

        call_args = state_store.update_task.call_args[0][1]
        assert call_args["status"] == "done"
        assert call_args["board_column"] == "Done"
        assert "retry_count_increment" not in call_args

    async def test_rejected_increments_retry_count(self, director, state_store, git_service):
        state_store.get_task = AsyncMock(return_value=MagicMock(github_issue_number=None))

        await director._handle_review(make_review_message("t1", success=False))

        call_args = state_store.update_task.call_args[0][1]
        assert call_args["status"] == "ready"
        assert call_args["retry_count_increment"] == 1

    async def test_missing_task_id_is_noop(self, director, state_store, git_service):
        """taskId가 없는 메시지는 무시한다."""
        import uuid
        from datetime import datetime, timezone
        msg = Message(
            id=str(uuid.uuid4()),
            type=MessageType.REVIEW_REQUEST,
            from_agent="agent-backend",
            payload={"result": {"success": True}},
            trace_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
        )
        await director._handle_review(msg)

        state_store.update_task.assert_not_called()
        git_service.move_issue_to_column.assert_not_called()
