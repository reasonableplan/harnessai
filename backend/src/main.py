"""애플리케이션 진입점."""
from __future__ import annotations

import asyncio
import signal
import sys

import uvicorn

from src.bootstrap import bootstrap, get_system_context, shutdown
from src.core.config import get_config
from src.core.logging.logger import configure_logging, get_logger
from src.dashboard.event_mapper import EventMapper
from src.dashboard.server import create_app, get_ws_manager

log = get_logger("Main")


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
    EventMapper(ctx.message_bus, ws_manager)

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
            # Windows에서는 signal handler 미지원
            pass

    # uvicorn 서버 (별도 태스크로 실행)
    server_config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=config.dashboard_port,
        log_level=config.log_level.lower(),
        loop="none",
    )
    server = uvicorn.Server(server_config)
    server_task = asyncio.create_task(server.serve())

    log.info("Dashboard server started", port=config.dashboard_port)

    # 종료 신호 대기
    await _shutdown_event.wait()

    # Shutdown
    server.should_exit = True
    await server_task
    await shutdown(ctx)


if __name__ == "__main__":
    asyncio.run(main())
