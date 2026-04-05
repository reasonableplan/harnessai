"""에이전트 오케스트레이션 대시보드 서버 진입점."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import uvicorn

from src.dashboard.server import cancel_background_tasks, create_app


async def _serve(host: str, port: int, project_dir: Path) -> None:
    auth_token = os.environ.get("DASHBOARD_AUTH_TOKEN")
    cors_origins_str = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173")
    cors_origins = [o.strip() for o in cors_origins_str.split(",")]

    # create_app 내부에서 init_deps(project_dir)를 호출하므로 중복 호출 불필요
    app = create_app(
        auth_token=auth_token,
        cors_origins=cors_origins,
        project_dir=project_dir,
    )

    config = uvicorn.Config(app, host=host, port=port, log_level="info", loop="none")
    server = uvicorn.Server(config)
    try:
        await server.serve()
    finally:
        await cancel_background_tasks()


def main() -> None:
    port = int(os.environ.get("DASHBOARD_PORT", "3002"))
    host = os.environ.get("DASHBOARD_HOST", "0.0.0.0")
    # 프로젝트 루트 = backend/
    project_dir = Path(__file__).parent.parent

    asyncio.run(_serve(host, port, project_dir))


if __name__ == "__main__":
    main()
