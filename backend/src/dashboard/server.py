"""FastAPI 대시보드 서버 — REST + WebSocket."""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
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
from src.dashboard.routes import agents, command, health, hooks, stats, tasks
from src.dashboard.routes.deps import get_orchestra, get_phase_manager, init_deps
from src.dashboard.websocket_manager import WebSocketManager
from src.orchestrator.phase import Phase

logger = logging.getLogger(__name__)

# structlog은 선택적 사용 — 없어도 서버는 정상 동작
try:
    import structlog as _structlog
    _HAS_STRUCTLOG = True
except ImportError:
    _HAS_STRUCTLOG = False

_ws_manager: WebSocketManager | None = None
_event_mapper: EventMapper | None = None


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """요청마다 request_id를 생성하고, 완료 시 로깅한다."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        start = time.monotonic()

        if _HAS_STRUCTLOG:
            _structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            response = await call_next(request)
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "Request completed method=%s path=%s status=%s duration_ms=%s",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
            )
            return response
        except Exception:
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            logger.error(
                "Request failed method=%s path=%s duration_ms=%s",
                request.method,
                request.url.path,
                duration_ms,
                exc_info=True,
            )
            raise
        finally:
            if _HAS_STRUCTLOG:
                _structlog.contextvars.unbind_contextvars("request_id")


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
    project_dir: str | Path | None = None,
) -> FastAPI:
    limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

    # 프로덕션(auth_token 설정 시) OpenAPI/Swagger 문서 비활성화
    is_prod = auth_token is not None
    app = FastAPI(
        title="Agent Orchestration Dashboard",
        version="2.0.0",
        docs_url=None if is_prod else "/docs",
        redoc_url=None if is_prod else "/redoc",
        openapi_url=None if is_prod else "/openapi.json",
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # 의존성 초기화 (project_dir 지정 시)
    if project_dir is not None:
        init_deps(project_dir)

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
    global _ws_manager, _event_mapper
    _ws_manager = WebSocketManager()
    _event_mapper = EventMapper(_ws_manager)

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
            logger.error("WS background task failed", exc_info=task.exception())

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        # 첫 메시지 기반 인증 (auth_token이 None이면 dev 모드 — 즉시 승인)
        ok = await _ws_manager.authenticate(ws, auth_token)
        if not ok:
            return
        _ws_msg_times[id(ws)] = []  # 재연결 시 이전 rate-limit 윈도우 초기화
        try:
            while True:
                raw = await ws.receive_text()
                if raw == "ping":
                    await ws.send_text('{"type":"pong"}')
                    continue

                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await ws.send_text('{"type":"error","message":"Invalid JSON"}')
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

                if msg_type in ("chat", "user-input"):
                    # "chat": content 필드 / "user-input": payload.text 필드
                    if msg_type == "chat":
                        content = msg.get("content", "").strip()[:4096]
                    else:
                        payload = msg.get("payload", {})
                        content = str(payload.get("text", "")).strip()[:4096]

                    if not content:
                        continue

                    try:
                        orchestra = get_orchestra()
                    except RuntimeError:
                        logger.error("Orchestra not available for %s", msg_type)
                        await ws.send_text(json.dumps({"type": "error", "message": "Server not initialized"}))
                        continue

                    phase = orchestra.phase_manager.current_phase

                    from src.orchestrator.orchestrate import PHASE_AGENT_MAP
                    agent = PHASE_AGENT_MAP.get(str(phase))
                    if agent is None:
                        await ws.send_text(
                            json.dumps({"type": "info", "message": f"no_agent_for_phase:{phase}"})
                        )
                        continue

                    async def _run_chat(
                        a: str = agent,
                        c: str = content,
                        p: Phase = phase,
                        o=orchestra,
                        em=_event_mapper,
                    ) -> None:
                        success = False
                        error: str | None = "내부 오류"
                        duration = 0
                        try:
                            await em.emit_agent_start(a, c)
                            if p == Phase.IMPLEMENTING:
                                task_id = f"ws_{uuid.uuid4().hex[:8]}"
                                res = await o.implement_with_retry(task_id, a, c)
                                impl = res.get("implement")
                                duration = impl.duration_ms if impl is not None else 0
                                success = res.get("passed", False)
                                error = None if success else "검증 실패"
                            else:
                                result = await o.runner.run(a, c)
                                success = result.success
                                duration = result.duration_ms
                                error = result.error
                            logger.info("WS command completed agent=%s phase=%s", a, p)
                        except Exception as exc:
                            error = str(exc) or "내부 오류"
                            logger.error("WS command failed agent=%s", a, exc_info=True)
                        finally:
                            try:
                                await em.emit_agent_complete(a, success, duration, error)
                            except Exception:
                                logger.error("emit_agent_complete failed agent=%s", a, exc_info=True)

                    task = asyncio.create_task(_run_chat())
                    _ws_bg_tasks.add(task)
                    task.add_done_callback(_on_bg_task_done)

                elif msg_type in ("plan.approve", "plan.commit", "plan.start"):
                    # Phase 전이 요청
                    from src.orchestrator.phase import InvalidTransitionError, Phase

                    action = msg_type.split(".")[1]
                    _action_phase_map: dict[str, str] = {
                        "start": "designing",
                        "approve": "task_breakdown",
                        "commit": "implementing",
                    }
                    target_phase_str = _action_phase_map.get(action)
                    if target_phase_str is None:
                        logger.warning("plan.%s: 지원하지 않는 액션", action)
                        await ws.send_text(json.dumps({"type": "error", "message": f"Unsupported plan action: {action}"}))
                        continue

                    try:
                        pm = get_phase_manager()
                        pm.transition(Phase(target_phase_str))
                        logger.info("Phase transitioned to %s via plan.%s", target_phase_str, action)
                    except RuntimeError:
                        logger.error("PhaseManager not available for plan action")
                        await ws.send_text(json.dumps({"type": "error", "message": "Server not initialized"}))
                    except InvalidTransitionError as exc:
                        await ws.send_text(
                            json.dumps({"type": "error", "message": str(exc)})
                        )

                elif msg_type == "task-retry":
                    payload = msg.get("payload", {})
                    task_id = str(payload.get("taskId", "")).strip()[:64]
                    if not task_id:
                        continue

                    try:
                        from src.dashboard.routes.deps import get_state_manager
                        sm = get_state_manager()
                    except RuntimeError:
                        logger.error("StateManager not available for task-retry")
                        continue

                    result = sm.load_task_result(task_id)
                    if result is None:
                        await ws.send_text('{"type":"error","message":"Task not found"}')
                        continue

                    status = result.get("status", "")
                    if status not in ("failed", "error"):
                        await ws.send_text(
                            '{"type":"error","message":"Only failed tasks can be retried"}'
                        )
                        continue

                    # 태스크 결과를 "pending"으로 업데이트해서 재실행 신호
                    result["status"] = "pending"
                    sm.save_task_result(task_id, result)
                    logger.info("Task retry requested task_id=%s", task_id)

        except WebSocketDisconnect:
            logger.debug("WebSocket client disconnected ws_id=%s", id(ws))
        except Exception as exc:
            logger.error("WS connection error: %s", exc)
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


def get_event_mapper() -> EventMapper:
    if _event_mapper is None:
        raise RuntimeError("EventMapper not initialized")
    return _event_mapper


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
