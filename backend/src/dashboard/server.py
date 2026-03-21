"""FastAPI 대시보드 서버 — REST + WebSocket."""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path

import structlog
from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.core.logging.logger import get_logger
from src.core.types import UserInput
from src.dashboard.auth import make_auth_checker
from src.dashboard.routes import agents, command, health, hooks, stats, tasks
from src.dashboard.routes.deps import get_agent_by_id, get_all_agents, get_director
from src.dashboard.websocket_manager import WebSocketManager

_log = get_logger("DashboardServer")
_request_log = get_logger("RequestLog")

_ws_manager: WebSocketManager | None = None


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """요청마다 request_id를 생성하고, 완료 시 로깅한다."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        start = time.monotonic()

        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            response = await call_next(request)
            duration_ms = round((time.monotonic() - start) * 1000, 2)

            response.headers["X-Request-ID"] = request_id
            _request_log.info(
                "Request completed",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=duration_ms,
            )
            return response
        except Exception:
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            _request_log.error(
                "Request failed",
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
                exc_info=True,
            )
            raise
        finally:
            structlog.contextvars.unbind_contextvars("request_id")


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
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self' ws://localhost:* wss://localhost:*;"
        )
        return response


def create_app(
    auth_token: str | None = None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

    # 프로덕션(auth_token 설정 시) OpenAPI/Swagger 문서 비활성화
    is_prod = auth_token is not None
    app = FastAPI(
        title="Agent Orchestration Dashboard",
        version="1.0.0",
        docs_url=None if is_prod else "/docs",
        redoc_url=None if is_prod else "/redoc",
        openapi_url=None if is_prod else "/openapi.json",
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # 요청 로깅 (가장 바깥 → 전체 duration 측정)
    app.add_middleware(RequestLoggingMiddleware)

    # 보안 헤더 (CORS보다 먼저 등록 → 모든 응답에 적용)
    app.add_middleware(SecurityHeadersMiddleware)

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or ["http://localhost:3000", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    auth_check = make_auth_checker(auth_token)

    # 인증 불필요 라우터
    app.include_router(health.router)

    # REST 라우터 등록
    app.include_router(agents.router, dependencies=[Depends(auth_check)])
    app.include_router(tasks.router, dependencies=[Depends(auth_check)])
    app.include_router(hooks.router, dependencies=[Depends(auth_check)])
    app.include_router(stats.router, dependencies=[Depends(auth_check)])
    app.include_router(command.router, dependencies=[Depends(auth_check)])

    # WebSocket
    global _ws_manager
    _ws_manager = WebSocketManager()

    # 진행 중인 WS 백그라운드 태스크 — GC 방지
    _ws_bg_tasks: set[asyncio.Task] = set()
    register_bg_task_set(_ws_bg_tasks)

    # command route의 백그라운드 태스크도 shutdown 시 정리되도록 등록
    from src.dashboard.routes.command import _background_tasks as cmd_bg_tasks
    register_bg_task_set(cmd_bg_tasks)

    # WS 메시지 rate limiting (LLM API 비용 보호)
    _ws_msg_times: dict[int, list[float]] = {}
    _WS_RATE_LIMIT = 20  # messages per minute

    def _on_bg_task_done(task: asyncio.Task) -> None:
        _ws_bg_tasks.discard(task)
        if not task.cancelled() and task.exception():
            _log.error("WS background task failed", exc_info=task.exception())

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        # 첫 메시지 기반 인증 (auth_token이 None이면 dev 모드 — 즉시 승인)
        ok = await _ws_manager.authenticate(ws, auth_token)
        if not ok:
            return
        try:
            while True:
                raw = await ws.receive_text()
                if raw == "ping":
                    await ws.send_text('{"type":"pong"}')
                    continue

                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type", "")

                # WS rate limiting
                ws_id = id(ws)
                now = time.monotonic()
                _ws_msg_times.setdefault(ws_id, [])
                _ws_msg_times[ws_id] = [t for t in _ws_msg_times[ws_id] if now - t < 60]
                if len(_ws_msg_times[ws_id]) >= _WS_RATE_LIMIT:
                    await ws.send_text('{"type":"error","message":"Rate limit exceeded"}')
                    continue
                _ws_msg_times[ws_id].append(now)

                if msg_type == "chat":
                    content = msg.get("content", "").strip()[:4096]
                    if not content:
                        continue
                    try:
                        director = get_director()
                    except RuntimeError:
                        _log.error("DirectorAgent not available for chat")
                        continue
                    user_input = UserInput(source="dashboard", content=content)
                    task = asyncio.create_task(director.handle_user_input(user_input))
                    _ws_bg_tasks.add(task)
                    task.add_done_callback(_on_bg_task_done)

                elif msg_type in ("plan.approve", "plan.revise", "plan.commit"):
                    action = msg_type.split(".")[1]  # "approve" / "revise" / "commit"
                    content = msg.get("content", "")
                    try:
                        director = get_director()
                    except RuntimeError:
                        _log.error("DirectorAgent not available for plan action")
                        continue
                    task = asyncio.create_task(
                        director.handle_plan_action(action, content)
                    )
                    _ws_bg_tasks.add(task)
                    task.add_done_callback(_on_bg_task_done)

                elif msg_type == "agent-pause":
                    payload = msg.get("payload", {})
                    agent_id = str(payload.get("agentId", ""))[:64]
                    if not agent_id:
                        continue
                    agent = get_agent_by_id(agent_id)
                    if agent:
                        task = asyncio.create_task(agent.pause())
                        _ws_bg_tasks.add(task)
                        task.add_done_callback(_on_bg_task_done)
                        _log.info("Agent pause requested", agent_id=agent_id)

                elif msg_type == "agent-resume":
                    payload = msg.get("payload", {})
                    agent_id = str(payload.get("agentId", ""))[:64]
                    if not agent_id:
                        continue
                    agent = get_agent_by_id(agent_id)
                    if agent:
                        task = asyncio.create_task(agent.resume())
                        _ws_bg_tasks.add(task)
                        task.add_done_callback(_on_bg_task_done)
                        _log.info("Agent resume requested", agent_id=agent_id)

                elif msg_type == "system-pause":
                    for agent in get_all_agents():
                        task = asyncio.create_task(agent.pause())
                        _ws_bg_tasks.add(task)
                        task.add_done_callback(_on_bg_task_done)
                    _log.info("System pause requested")

                elif msg_type == "system-resume":
                    for agent in get_all_agents():
                        task = asyncio.create_task(agent.resume())
                        _ws_bg_tasks.add(task)
                        task.add_done_callback(_on_bg_task_done)
                    _log.info("System resume requested")

                elif msg_type == "task-retry":
                    payload = msg.get("payload", {})
                    task_id = str(payload.get("taskId", "")).strip()
                    if not task_id:
                        continue
                    from src.dashboard.routes.deps import get_state_store
                    store = get_state_store()
                    task_row = await store.get_task(task_id)
                    if task_row is None:
                        await ws.send_text('{"type":"error","message":"Task not found"}')
                        continue
                    if task_row.status not in ("failed", "error"):
                        await ws.send_text('{"type":"error","message":"Only failed tasks can be retried"}')
                        continue
                    # Board-first: 외부(Board) 먼저 → 내부(DB) 나중
                    if task_row.github_issue_number:
                        try:
                            from src.bootstrap import get_system_context
                            git_service = get_system_context().git_service
                            await git_service.move_issue_to_column(
                                task_row.github_issue_number, "Ready"
                            )
                        except Exception as e:
                            _log.error("Task retry: Board move failed, aborting retry", task_id=task_id, err=str(e))
                            await ws.send_text('{"type":"error","message":"Board move failed, retry aborted"}')
                            continue
                    await store.update_task(
                        task_id, {"status": "ready", "board_column": "Ready"}
                    )
                    _log.info("Task retry requested", task_id=task_id)

                elif msg_type == "user-input":
                    payload = msg.get("payload", {})
                    text = str(payload.get("text", "")).strip()[:4096]
                    if not text:
                        continue
                    try:
                        director = get_director()
                    except RuntimeError:
                        _log.error("DirectorAgent not available for user-input")
                        continue
                    user_input = UserInput(source="dashboard", content=text)
                    task = asyncio.create_task(director.handle_user_input(user_input))
                    _ws_bg_tasks.add(task)
                    task.add_done_callback(_on_bg_task_done)

        except WebSocketDisconnect:
            _log.debug("WebSocket client disconnected", ws_id=id(ws))
        except Exception as e:
            _log.error("WS connection error", err=str(e))
        finally:
            _ws_msg_times.pop(id(ws), None)
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


# WS/command 백그라운드 태스크 참조 (셧다운 시 정리용)
_all_bg_task_sets: list[set[asyncio.Task]] = []


def register_bg_task_set(task_set: set[asyncio.Task]) -> None:
    """create_app 내부에서 호출 — shutdown 시 정리할 태스크 셋 등록."""
    _all_bg_task_sets.append(task_set)


async def cancel_background_tasks() -> None:
    """Graceful shutdown 시 진행 중인 WS/command 백그라운드 태스크를 정리한다."""
    for task_set in _all_bg_task_sets:
        for task in list(task_set):
            task.cancel()
        await asyncio.gather(*task_set, return_exceptions=True)
        task_set.clear()
