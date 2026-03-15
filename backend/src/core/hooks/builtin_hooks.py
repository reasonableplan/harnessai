"""내장 훅 3종 등록."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.core.hooks.hook_registry import HookRegistry
from src.core.logging.logger import get_logger
from src.core.state.state_store import StateStore
from src.core.types import HookEvent, HookRow

log = get_logger("BuiltinHooks")

BUILTIN_HOOKS: list[HookRow] = [
    HookRow(
        id="log-task-complete",
        event=HookEvent.TASK_COMPLETED,
        name="Log Task Completed",
        description="태스크 완료 시 로그 기록",
        enabled=True,
        created_at=datetime.now(timezone.utc),
    ),
    HookRow(
        id="toast-on-failure",
        event=HookEvent.TASK_FAILED,
        name="Toast on Failure",
        description="태스크 실패 시 경고 로그",
        enabled=True,
        created_at=datetime.now(timezone.utc),
    ),
    HookRow(
        id="log-agent-error",
        event=HookEvent.AGENT_ERROR,
        name="Log Agent Error",
        description="에이전트 에러 로그",
        enabled=True,
        created_at=datetime.now(timezone.utc),
    ),
]


def _log_task_complete(payload: dict[str, Any]) -> None:
    log.info("Hook: task completed", task_id=payload.get("taskId"), agent=payload.get("agentId"))


def _toast_on_failure(payload: dict[str, Any]) -> None:
    log.warn("Hook: task failed", task_id=payload.get("taskId"), reason=payload.get("reason"))


def _log_agent_error(payload: dict[str, Any]) -> None:
    log.error("Hook: agent error", agent=payload.get("agentId"), err=payload.get("error"))


async def register_builtin_hooks(registry: HookRegistry, state_store: StateStore) -> None:
    """DB에 내장 훅 등록 + HookRegistry에 핸들러 등록."""
    for hook in BUILTIN_HOOKS:
        await state_store.upsert_hook(hook)

    await registry.load_enabled_status()

    registry.register("log-task-complete", HookEvent.TASK_COMPLETED, _log_task_complete)
    registry.register("toast-on-failure", HookEvent.TASK_FAILED, _toast_on_failure)
    registry.register("log-agent-error", HookEvent.AGENT_ERROR, _log_agent_error)
