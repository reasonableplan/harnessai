"""BaseAgent 테스트."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.agent.base_agent import BaseAgent
from src.core.messaging.message_bus import MessageBus
from src.core.types import AgentConfig, AgentLevel, AgentStatus, Task, TaskResult, TaskStatus


class ConcreteAgent(BaseAgent):
    """테스트용 구체 에이전트."""

    def __init__(self, *args, execute_result: TaskResult | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._execute_result = execute_result or TaskResult(success=True, artifacts=[])
        self.executed_tasks: list[Task] = []

    async def execute_task(self, task: Task) -> TaskResult:
        self.executed_tasks.append(task)
        return self._execute_result


def make_config(**kwargs) -> AgentConfig:
    return AgentConfig(
        id=kwargs.get("id", "test-agent"),
        domain=kwargs.get("domain", "backend"),
        level=kwargs.get("level", AgentLevel.WORKER),
        poll_interval_ms=kwargs.get("poll_interval_ms", 100),
        task_timeout_ms=kwargs.get("task_timeout_ms", 5000),
    )


def make_task(task_id: str = "task-1") -> Task:
    return Task(
        id=task_id,
        title="Test Task",
        description="desc",
        status=TaskStatus.IN_PROGRESS,
        board_column="In Progress",
    )


@pytest.fixture
def message_bus():
    return MessageBus()


@pytest.fixture
def state_store():
    store = MagicMock()
    store.get_ready_tasks_for_agent = AsyncMock(return_value=[])
    store.claim_task = AsyncMock(return_value=True)
    store.update_task = AsyncMock()
    store.update_heartbeat = AsyncMock()
    store.get_agent_config = AsyncMock(return_value=None)
    store.save_message = AsyncMock()
    return store


@pytest.fixture
def git_service():
    svc = MagicMock()
    svc.move_issue_to_column = AsyncMock()
    return svc


@pytest.fixture
def agent(message_bus, state_store, git_service):
    return ConcreteAgent(
        config=make_config(),
        message_bus=message_bus,
        state_store=state_store,
        git_service=git_service,
    )


def test_initial_status(agent):
    assert agent.status == AgentStatus.IDLE


@pytest.mark.asyncio
async def test_set_status_publishes_message(agent, message_bus):
    received = []
    message_bus.subscribe_all(lambda msg: received.append(msg))

    await agent._set_status(AgentStatus.BUSY, task_id="task-1")

    assert any(m.type == "agent.status" for m in received)
    status_msg = next(m for m in received if m.type == "agent.status")
    assert status_msg.payload["status"] == "busy"
    assert status_msg.payload["taskId"] == "task-1"


@pytest.mark.asyncio
async def test_publish_token_usage(agent, message_bus):
    received = []
    message_bus.subscribe_all(lambda msg: received.append(msg))

    await agent._publish_token_usage(100, 200)

    token_msg = next((m for m in received if m.type == "token.usage"), None)
    assert token_msg is not None
    assert token_msg.payload["inputTokens"] == 100
    assert token_msg.payload["outputTokens"] == 200


@pytest.mark.asyncio
async def test_on_task_complete_success(agent, state_store, message_bus):
    received = []
    message_bus.subscribe_all(lambda msg: received.append(msg))

    task = make_task()
    result = TaskResult(success=True, artifacts=[])
    await agent._on_task_complete(task, result)

    state_store.update_task.assert_called_once()
    call_args = state_store.update_task.call_args
    assert call_args[0][1]["status"] == "review"
    assert call_args[0][1]["board_column"] == "Review"

    review_msg = next((m for m in received if m.type == "review.request"), None)
    assert review_msg is not None


@pytest.mark.asyncio
async def test_on_task_complete_failure(agent, state_store):
    task = make_task()
    result = TaskResult(success=False, error={"message": "error"}, artifacts=[])
    await agent._on_task_complete(task, result)

    call_args = state_store.update_task.call_args
    assert call_args[0][1]["status"] == "failed"
    assert call_args[0][1]["board_column"] == "Failed"


@pytest.mark.asyncio
async def test_drain_stops_polling(agent):
    agent.start_polling(interval_ms=100)
    assert agent._polling is True
    await agent.drain()
    assert agent._polling is False


@pytest.mark.asyncio
async def test_pause_and_resume(agent):
    agent.start_polling(interval_ms=100)
    await agent.pause()
    assert agent.status == AgentStatus.PAUSED

    await agent.resume(interval_ms=100)
    assert agent.status == AgentStatus.IDLE
    assert agent._polling is True
    await agent.drain()


@pytest.mark.asyncio
async def test_task_timeout(message_bus, state_store, git_service):
    class SlowAgent(ConcreteAgent):
        async def execute_task(self, task: Task) -> TaskResult:
            await asyncio.sleep(10)
            return TaskResult(success=True, artifacts=[])

    agent = SlowAgent(
        config=make_config(task_timeout_ms=100),
        message_bus=message_bus,
        state_store=state_store,
        git_service=git_service,
    )
    task = make_task()
    with pytest.raises(TimeoutError):
        await agent._execute_with_timeout(task)


@pytest.mark.asyncio
async def test_subscribe_and_unsubscribe_on_drain(agent, message_bus):
    received = []
    agent._subscribe("custom.event", lambda msg: received.append(msg))

    await agent.drain()

    # drain 후 구독 해제 확인
    from src.core.types import Message
    import uuid
    await message_bus.publish(Message(
        id=str(uuid.uuid4()), type="custom.event",
        from_agent="other", payload={}, trace_id=""
    ))
    assert len(received) == 0
