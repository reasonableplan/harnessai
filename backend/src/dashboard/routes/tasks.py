"""GET /api/tasks — 태스크 결과 조회."""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("")
async def list_tasks() -> list[dict]:
    """StateManager results/ 디렉토리의 모든 태스크 결과를 반환한다."""
    from src.dashboard.routes.deps import get_state_manager

    sm = get_state_manager()
    results: list[dict] = []

    try:
        for path in sorted(sm._results_dir.iterdir()):
            if path.suffix != ".json":
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                # task_id를 파일명(확장자 제거)에서 복원
                if isinstance(data, dict) and "task_id" not in data:
                    data["task_id"] = path.stem
                results.append(data)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("tasks: %s 파일 읽기 실패: %s", path.name, exc)
    except OSError as exc:
        logger.error("tasks: results 디렉토리 접근 실패: %s", exc)

    return results


@router.get("/{task_id}")
async def get_task(
    task_id: str = Path(..., min_length=1, max_length=64),
) -> dict:
    """특정 태스크 결과를 반환한다."""
    from src.dashboard.routes.deps import get_state_manager

    sm = get_state_manager()
    result = sm.load_task_result(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return result
