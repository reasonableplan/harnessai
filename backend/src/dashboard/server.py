"""FastAPI 대시보드 서버 — REST + WebSocket."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.dashboard.auth import make_auth_checker
from src.dashboard.event_mapper import EventMapper
from src.dashboard.routes import agents, hooks, stats, tasks
from src.dashboard.websocket_manager import WebSocketManager

_ws_manager: WebSocketManager | None = None
_event_mapper: EventMapper | None = None


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """OWASP 권고 보안 헤더를 모든 응답에 추가한다."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self' ws: wss:;"
        )
        return response


def create_app(
    auth_token: str | None = None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

    app = FastAPI(title="Agent Orchestration Dashboard", version="1.0.0")
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # 보안 헤더 (CORS보다 먼저 등록 → 모든 응답에 적용)
    app.add_middleware(SecurityHeadersMiddleware)

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or ["http://localhost:3000", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    auth_check = make_auth_checker(auth_token)

    # REST 라우터 등록
    app.include_router(agents.router, dependencies=[Depends(auth_check)])
    app.include_router(tasks.router, dependencies=[Depends(auth_check)])
    app.include_router(hooks.router, dependencies=[Depends(auth_check)])
    app.include_router(stats.router, dependencies=[Depends(auth_check)])

    # WebSocket
    global _ws_manager
    _ws_manager = WebSocketManager()

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket, token: str | None = None):
        # WS 토큰 검증
        if auth_token and token != auth_token:
            await ws.close(code=4001)
            return
        await _ws_manager.connect(ws)
        try:
            while True:
                # 클라이언트 메시지 수신 (ping 등)
                data = await ws.receive_text()
                if data == "ping":
                    await ws.send_text('{"type":"pong"}')
        except WebSocketDisconnect:
            _ws_manager.disconnect(ws)

    # 정적 파일 (빌드된 프론트엔드)
    static_dir = Path(__file__).parent.parent.parent.parent / "packages" / "dashboard-client" / "dist"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app


def get_ws_manager() -> WebSocketManager:
    if _ws_manager is None:
        raise RuntimeError("WebSocketManager not initialized")
    return _ws_manager
