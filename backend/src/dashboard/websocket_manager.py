"""WebSocket 연결 풀 관리."""
from __future__ import annotations

import asyncio
import hmac
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket
from src.core.logging.logger import get_logger

log = get_logger("WSManager")

_AUTH_TIMEOUT_S = 5.0


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def authenticate(self, ws: WebSocket, auth_token: str | None) -> bool:
        """WS 연결을 accept한 뒤 첫 메시지 기반 인증을 수행한다.

        auth_token이 None(dev 모드)이면 즉시 승인한다.
        인증 성공 시 True, 실패 시 ws를 close(4001)하고 False를 반환한다.
        """
        await ws.accept()

        if auth_token is None:
            # 인증 불필요 — 연결 풀에 바로 추가
            self._connections.add(ws)
            log.info("WS connected (no auth)", total=len(self._connections))
            return True

        # 5초 안에 {"type": "auth", "token": "..."} 수신 필요
        try:
            raw = await asyncio.wait_for(ws.receive_text(), timeout=_AUTH_TIMEOUT_S)
        except asyncio.TimeoutError:
            log.warning("WS auth timeout — closing")
            await ws.close(code=4001)
            return False
        except Exception:
            await ws.close(code=4001)
            return False

        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            await ws.close(code=4001)
            return False

        token = msg.get("token") or ""
        if msg.get("type") != "auth" or not hmac.compare_digest(token.encode(), auth_token.encode()):
            log.warning("WS auth failed — invalid token")
            await ws.close(code=4001)
            return False

        self._connections.add(ws)
        await ws.send_text(json.dumps({"type": "auth.ok"}))
        log.info("WS authenticated and connected", total=len(self._connections))
        return True

    async def connect(self, ws: WebSocket) -> None:
        """레거시 호환용 — auth 없이 연결 (dev 모드 내부 사용)."""
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
