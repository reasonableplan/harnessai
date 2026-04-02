"""GET /health — 서버 상태 확인."""
from __future__ import annotations

import logging

from fastapi import APIRouter
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> JSONResponse:
    """서버 생존 여부와 현재 Phase 상태를 반환한다. 인증 불필요."""
    checks: dict[str, dict] = {}

    # Phase 상태 확인
    try:
        from src.dashboard.routes.deps import get_phase_manager
        pm = get_phase_manager()
        checks["phase"] = {"status": "ok", "current": str(pm.current_phase)}
    except RuntimeError:
        # init_deps 호출 전(개발/테스트)에는 경고만
        logger.warning("PhaseManager not initialized during health check")
        checks["phase"] = {"status": "not_initialized"}
    except Exception as exc:
        logger.error("Health: phase check failed", exc_info=exc)
        checks["phase"] = {"status": "error"}

    # config 확인
    try:
        from src.dashboard.routes.deps import get_config
        cfg = get_config()
        checks["config"] = {"status": "ok", "agents": len(cfg.all_agents())}
    except RuntimeError:
        checks["config"] = {"status": "not_initialized"}
    except Exception as exc:
        logger.error("Health: config check failed", exc_info=exc)
        checks["config"] = {"status": "error"}

    overall = (
        "ok"
        if all(c["status"] in ("ok", "not_initialized") for c in checks.values())
        else "degraded"
    )
    status_code = 200 if overall == "ok" else 503

    return JSONResponse(
        status_code=status_code,
        content={"status": overall, "checks": checks},
    )
