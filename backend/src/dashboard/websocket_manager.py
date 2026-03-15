"""WebSocket 연결 풀 관리."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket
from src.core.logging.logger import get_logger

log = get_logger("WSManager")


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)
        log.info("WS connected", total=len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)
        log.info("WS disconnected", total=len(self._connections))

    async def broadcast(self, event_type: str, data: Any) -> None:
        if not self._connections:
            return
        payload = json.dumps({
            "type": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        dead: list[WebSocket] = []
        for ws in list(self._connections):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.discard(ws)

    @property
    def connection_count(self) -> int:
        return len(self._connections)
