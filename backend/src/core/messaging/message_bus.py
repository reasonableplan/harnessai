from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import TYPE_CHECKING, Awaitable, Callable, Union

from src.core.logging.logger import get_logger
from src.core.types import Message

if TYPE_CHECKING:
    from src.core.state.state_store import StateStore

log = get_logger("MessageBus")

MessageHandler = Callable[["Message"], Union[Awaitable[None], None]]


class MessageBus:
    """인메모리 pub/sub 메시지 버스. DB 자동 퍼시스트."""

    def __init__(self, state_store: StateStore | None = None) -> None:
        self._handlers: dict[str, list[MessageHandler]] = defaultdict(list)
        self._all_handlers: list[MessageHandler] = []
        self._state_store = state_store

    def set_state_store(self, state_store: StateStore) -> None:
        """bootstrap 순서상 StateStore가 나중에 생성될 때 사용."""
        self._state_store = state_store

    async def publish(self, message: Message) -> None:
        # DB 퍼시스트 (감사 로그)
        if self._state_store is not None:
            try:
                await self._state_store.save_message(message)
            except Exception as e:
                log.error("Failed to persist message", err=str(e), message_type=message.type)

        # 타입별 핸들러 호출
        for handler in list(self._handlers.get(message.type, [])):
            await self._call(handler, message)

        # 전체 구독 핸들러 호출 (대시보드용)
        for handler in list(self._all_handlers):
            await self._call(handler, message)

    async def _call(self, handler, message: Message) -> None:
        try:
            result = handler(message)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            log.error("Handler error", err=str(e), message_type=message.type)

    def subscribe(self, msg_type: str, handler) -> None:
        self._handlers[msg_type].append(handler)

    def subscribe_all(self, handler) -> None:
        self._all_handlers.append(handler)

    def unsubscribe(self, msg_type: str, handler) -> None:
        handlers = self._handlers.get(msg_type, [])
        if handler in handlers:
            handlers.remove(handler)

    def unsubscribe_all(self, handler) -> None:
        self._all_handlers = [h for h in self._all_handlers if h is not handler]
