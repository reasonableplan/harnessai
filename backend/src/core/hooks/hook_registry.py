"""Hook 시스템 — 이벤트 기반 플러그인."""
from __future__ import annotations

import asyncio
from typing import Any, Callable

from src.core.logging.logger import get_logger
from src.core.state.state_store import StateStore
from src.core.types import HookEvent, HookRow

log = get_logger("HookRegistry")

HookHandler = Callable[[dict[str, Any]], Any]


class HookRegistry:
    def __init__(self, state_store: StateStore) -> None:
        self._state_store = state_store
        self._handlers: dict[str, list[tuple[str, HookHandler]]] = {}  # event → [(id, handler)]
        self._enabled: dict[str, bool] = {}

    async def load_enabled_status(self) -> None:
        """DB에서 활성화 상태 로드."""
        rows = await self._state_store.get_all_hooks()
        self._enabled = {r.id: r.enabled for r in rows}

    def register(self, hook_id: str, event: str, handler: HookHandler) -> None:
        if event not in self._handlers:
            self._handlers[event] = []
        self._handlers[event].append((hook_id, handler))
        log.info("Hook registered", hook_id=hook_id, hook_event=event)

    async def dispatch(self, event: str, payload: dict[str, Any]) -> None:
        for hook_id, handler in self._handlers.get(event, []):
            if not self._enabled.get(hook_id, True):
                continue
            try:
                result = handler(payload)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                log.error("Hook handler error", hook_id=hook_id, hook_event=event, err=str(e))

    async def set_enabled(self, hook_id: str, enabled: bool) -> None:
        self._enabled[hook_id] = enabled
        await self._state_store.toggle_hook(hook_id, enabled)
