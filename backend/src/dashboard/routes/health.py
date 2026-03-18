"""GET /health — DB + GitHub 연결 상태 확인."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from starlette.responses import JSONResponse

from src.bootstrap import get_system_context
from src.core.logging.logger import get_logger
from src.dashboard.routes.deps import get_state_store

log = get_logger("Health")

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(store=Depends(get_state_store)):
    """DB와 GitHub 연결 상태를 확인한다. 인증 불필요."""
    checks: dict[str, dict] = {}

    # DB 확인
    try:
        await store.check_db_connection()
        checks["database"] = {"status": "ok"}
    except Exception as e:
        log.error("Health: DB check failed", err=str(e))
        checks["database"] = {"status": "error"}

    # GitHub 확인
    try:
        ctx = get_system_context()
        await ctx.git_service.check_rate_limit()
        checks["github"] = {"status": "ok"}
    except Exception as e:
        log.error("Health: GitHub check failed", err=str(e))
        checks["github"] = {"status": "error"}

    # 에이전트 상태 요약
    try:
        agents = await store.get_all_agents()
        checks["agents"] = {"status": "ok", "count": len(agents)}
    except Exception as e:
        log.error("Health: agents check failed", err=str(e))
        checks["agents"] = {"status": "error"}

    overall = "ok" if all(c["status"] == "ok" for c in checks.values()) else "degraded"
    status_code = 200 if overall == "ok" else 503

    return JSONResponse(
        status_code=status_code,
        content={"status": overall, "checks": checks},
    )
