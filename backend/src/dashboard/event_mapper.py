"""MessageBus 메시지 → WebSocket 이벤트 변환."""
from __future__ import annotations

from src.core.messaging.message_bus import MessageBus
from src.core.types import Message, MessageType
from src.core.logging.logger import get_logger

log = get_logger("EventMapper")


class EventMapper:
    def __init__(self, message_bus: MessageBus, ws_manager) -> None:
        self._ws = ws_manager
        self._message_bus = message_bus
        message_bus.subscribe_all(self._on_message)

    def dispose(self) -> None:
        """MessageBus 구독 해제 — 셧다운 시 호출."""
        self._message_bus.unsubscribe_all(self._on_message)

    async def _on_message(self, msg: Message) -> None:
        event_type, data = self._map(msg)
        if event_type:
            await self._ws.broadcast(event_type, data)

    def _map(self, msg: Message) -> tuple[str | None, dict]:
        payload = msg.payload if isinstance(msg.payload, dict) else {}

        if msg.type == MessageType.AGENT_STATUS:
            return "agent.status", {
                "agentId": msg.from_agent,
                "status": payload.get("status"),
                "taskId": payload.get("taskId"),
            }
        if msg.type == MessageType.TOKEN_USAGE:
            return "token.usage", {
                "agentId": msg.from_agent,
                "inputTokens": payload.get("inputTokens", 0),
                "outputTokens": payload.get("outputTokens", 0),
            }
        if msg.type == MessageType.BOARD_MOVE:
            return "board.move", payload
        if msg.type == MessageType.REVIEW_REQUEST:
            return "review.request", {
                "agentId": msg.from_agent,
                "taskId": payload.get("taskId"),
            }
        if msg.type == MessageType.EPIC_PROGRESS:
            return "epic.progress", payload
        return None, {}
