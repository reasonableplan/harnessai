"""EventMapper 테스트 — MessageBus → WebSocket 이벤트 변환."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from src.core.messaging.message_bus import MessageBus
from src.core.types import Message, MessageType
from src.dashboard.event_mapper import EventMapper


def _make_msg(msg_type: str, from_agent: str = "director", payload: dict | None = None) -> Message:
    return Message(
        id="m1",
        type=msg_type,
        from_agent=from_agent,
        payload=payload or {},
    )


class TestEventMapper:
    async def test_agent_status_mapped(self):
        bus = MessageBus()
        ws = MagicMock()
        ws.broadcast = AsyncMock()
        mapper = EventMapper(bus, ws)

        msg = _make_msg(MessageType.AGENT_STATUS, payload={"status": "idle", "taskId": "t1"})
        await mapper._on_message(msg)

        ws.broadcast.assert_called_once_with("agent.status", {
            "agentId": "director",
            "status": "idle",
            "taskId": "t1",
        })

    async def test_token_usage_mapped(self):
        bus = MessageBus()
        ws = MagicMock()
        ws.broadcast = AsyncMock()
        mapper = EventMapper(bus, ws)

        msg = _make_msg(MessageType.TOKEN_USAGE, payload={"inputTokens": 100, "outputTokens": 50})
        await mapper._on_message(msg)

        ws.broadcast.assert_called_once_with("token.usage", {
            "agentId": "director",
            "inputTokens": 100,
            "outputTokens": 50,
        })

    async def test_director_message_mapped(self):
        bus = MessageBus()
        ws = MagicMock()
        ws.broadcast = AsyncMock()
        mapper = EventMapper(bus, ws)

        msg = _make_msg(MessageType.DIRECTOR_MESSAGE, payload={"content": "hello"})
        await mapper._on_message(msg)

        ws.broadcast.assert_called_once_with("director.message", {"content": "hello"})

    async def test_unknown_type_not_broadcast(self):
        bus = MessageBus()
        ws = MagicMock()
        ws.broadcast = AsyncMock()
        mapper = EventMapper(bus, ws)

        msg = _make_msg("unknown.type")
        await mapper._on_message(msg)

        ws.broadcast.assert_not_called()

    async def test_director_committed_mapped(self):
        bus = MessageBus()
        ws = MagicMock()
        ws.broadcast = AsyncMock()
        mapper = EventMapper(bus, ws)

        msg = _make_msg(MessageType.DIRECTOR_COMMITTED, payload={
            "epicId": "e1", "epicTitle": "Epic", "issues": [1, 2],
        })
        await mapper._on_message(msg)

        ws.broadcast.assert_called_once_with("director.committed", {
            "epicId": "e1",
            "epicTitle": "Epic",
            "issues": [1, 2],
        })

    async def test_dispose_unsubscribes(self):
        bus = MessageBus()
        ws = MagicMock()
        ws.broadcast = AsyncMock()
        mapper = EventMapper(bus, ws)

        # dispose 전에는 all_handlers에 등록되어 있음
        assert len(bus._all_handlers) == 1

        mapper.dispose()

        # dispose 후에는 all_handlers에서 제거됨
        assert len(bus._all_handlers) == 0

    async def test_non_dict_payload_handled(self):
        bus = MessageBus()
        ws = MagicMock()
        ws.broadcast = AsyncMock()
        mapper = EventMapper(bus, ws)

        msg = _make_msg(MessageType.AGENT_STATUS, payload=None)
        msg.payload = "not a dict"
        await mapper._on_message(msg)

        ws.broadcast.assert_called_once()
        call_data = ws.broadcast.call_args[0][1]
        assert call_data["status"] is None
