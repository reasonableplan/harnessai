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
_MAX_WS_CONNECTIONS = 50


async def _safe_close(ws: WebSocket, code: int) -> None:
    """클라이언트가 이미 끊긴 경우 close() 예외를 무시한다."""
    try:
        await ws.close(code=code)
    except Exception:
        pass


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def authenticate(self, ws: WebSocket, auth_token: str | None) -> bool:
        """WS 연결을 accept한 뒤 첫 메시지 기반 인증을 수행한다.

        auth_token이 None(dev 모드)이면 즉시 승인한다.
        인증 성공 시 True, 실패 시 ws를 close(4001)하고 False를 반환한다.
        """
        await ws.accept()

        # 연결 수 제한
        if len(self._connections) >= _MAX_WS_CONNECTIONS:
            await _safe_close(ws, 4003)
            return False

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
            await _safe_close(ws, 4001)
            return False
        except Exception:
            await _safe_close(ws, 4001)
            return False

        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            await _safe_close(ws, 4001)
            return False

        token = msg.get("token") or ""
        if msg.get("type") != "auth" or not hmac.compare_digest(token.encode(), auth_token.encode()):
            log.warning("WS auth failed — invalid token")
            await _safe_close(ws, 4001)
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
            "payload": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        async def _safe_send(ws: WebSocket) -> WebSocket | None:
            try:
                await asyncio.wait_for(ws.send_text(payload), timeout=5.0)
                return None
            except Exception:
                return ws

        results = await asyncio.gather(*[_safe_send(ws) for ws in list(self._connections)])
        for ws in results:
            if ws is not None:
                self._connections.discard(ws)

    @property
    def connection_count(self) -> int:
        return len(self._connections)
