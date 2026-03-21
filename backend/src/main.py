"""애플리케이션 진입점."""
from __future__ import annotations

import asyncio
import signal

import uvicorn

from src.bootstrap import bootstrap, shutdown
from src.core.config import get_config
from src.core.logging.logger import configure_logging, get_logger
from src.dashboard.event_mapper import EventMapper
from src.dashboard.server import cancel_background_tasks, create_app, get_ws_manager

log = get_logger("Main")


async def _wait_for_startup(server: uvicorn.Server, server_task: asyncio.Task) -> None:
    """서버가 started 상태가 되거나 바인드 실패로 태스크가 종료될 때까지 대기한다."""
    while not server.started:
        if server_task.done():
            # 서버가 시작 전에 종료됨 — 바인드 실패 등
            exc = server_task.exception()
            if exc:
                raise exc
            raise RuntimeError("Server exited before startup completed")
        await asyncio.sleep(0.05)


async def main() -> None:
    config = get_config(require_all=True)
    configure_logging(config.log_level, config.is_production)

    log.info("Starting agent orchestration system...")

    # 부트스트랩
    ctx = await bootstrap(config)

    # FastAPI 앱 생성
    app = create_app(
        auth_token=config.dashboard_auth_token,
        cors_origins=config.cors_origins_list,
    )

    # EventMapper: MessageBus → WebSocket 브로드캐스트
    ws_manager = get_ws_manager()
    event_mapper = EventMapper(ctx.message_bus, ws_manager)

    # BoardWatcher + OrphanCleaner 시작
    ctx.board_watcher.start()
    ctx.orphan_cleaner.start()

    # 에이전트 폴링 시작
    for agent in ctx.agents:
        agent.start_polling(agent.config.poll_interval_ms)
        log.info("Agent polling started", agent=agent.id)

    # Graceful shutdown 핸들러
    loop = asyncio.get_running_loop()
    _shutdown_event = asyncio.Event()

    def _handle_signal():
        log.info("Shutdown signal received")
        _shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            # Windows: asyncio signal handler 미지원 → stdlib signal 사용
            try:
                signal.signal(sig, lambda _s, _f: _handle_signal())
            except OSError:
                log.warning("Signal not supported on this platform", signal=sig.name)

    # uvicorn 서버 (별도 태스크로 실행)
    server_config = uvicorn.Config(
        app,
        host=config.dashboard_host,
        port=config.dashboard_port,
        log_level=config.log_level.lower(),
        loop="none",
    )
    server = uvicorn.Server(server_config)
    server_task = asyncio.create_task(server.serve())

    # 바인드 실패 조기 감지 — startup 완료 또는 태스크 예외를 기다림
    startup_wait = asyncio.create_task(_wait_for_startup(server, server_task))
    try:
        await startup_wait
    except Exception as e:
        log.error("Server failed to start", err=str(e))
        event_mapper.dispose()
        await shutdown(ctx)
        raise SystemExit(1) from e

    log.info("Dashboard server started", port=config.dashboard_port)

    # 종료 신호 대기
    await _shutdown_event.wait()

    # Shutdown
    server.should_exit = True
    await server_task
    event_mapper.dispose()
    await cancel_background_tasks()
    await shutdown(ctx)


if __name__ == "__main__":
    asyncio.run(main())
