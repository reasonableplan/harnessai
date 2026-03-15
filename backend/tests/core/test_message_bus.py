"""MessageBus 테스트."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.messaging.message_bus import MessageBus
from src.core.types import Message


def make_message(msg_type: str = "test.event", payload: dict | None = None) -> Message:
    return Message(
        id="msg-1",
        type=msg_type,
        from_agent="agent-a",
        payload=payload or {},
        trace_id="trace-1",
    )


@pytest.mark.asyncio
async def test_subscribe_and_receive():
    bus = MessageBus()
    received = []

    def handler(msg: Message):
        received.append(msg)

    bus.subscribe("test.event", handler)
    await bus.publish(make_message("test.event"))

    assert len(received) == 1
    assert received[0].type == "test.event"


@pytest.mark.asyncio
async def test_subscribe_all():
    bus = MessageBus()
    received = []

    bus.subscribe_all(lambda msg: received.append(msg))
    await bus.publish(make_message("event.a"))
    await bus.publish(make_message("event.b"))

    assert len(received) == 2


@pytest.mark.asyncio
async def test_unsubscribe():
    bus = MessageBus()
    received = []

    def handler(msg: Message):
        received.append(msg)

    bus.subscribe("test.event", handler)
    bus.unsubscribe("test.event", handler)
    await bus.publish(make_message("test.event"))

    assert len(received) == 0


@pytest.mark.asyncio
async def test_unsubscribe_all():
    bus = MessageBus()
    received = []

    handler = lambda msg: received.append(msg)
    bus.subscribe_all(handler)
    bus.unsubscribe_all(handler)
    await bus.publish(make_message("test.event"))

    assert len(received) == 0


@pytest.mark.asyncio
async def test_async_handler():
    bus = MessageBus()
    received = []

    async def async_handler(msg: Message):
        await asyncio.sleep(0)
        received.append(msg)

    bus.subscribe("test.event", async_handler)
    await bus.publish(make_message("test.event"))

    assert len(received) == 1


@pytest.mark.asyncio
async def test_persists_to_state_store():
    state_store = MagicMock()
    state_store.save_message = AsyncMock()

    bus = MessageBus(state_store)
    await bus.publish(make_message("test.event"))

    state_store.save_message.assert_called_once()


@pytest.mark.asyncio
async def test_handler_error_does_not_propagate():
    bus = MessageBus()

    def bad_handler(msg: Message):
        raise ValueError("handler error")

    bus.subscribe("test.event", bad_handler)
    # 에러가 전파되지 않아야 함
    await bus.publish(make_message("test.event"))


@pytest.mark.asyncio
async def test_type_isolation():
    bus = MessageBus()
    received_a = []
    received_b = []

    bus.subscribe("event.a", lambda msg: received_a.append(msg))
    bus.subscribe("event.b", lambda msg: received_b.append(msg))

    await bus.publish(make_message("event.a"))

    assert len(received_a) == 1
    assert len(received_b) == 0
