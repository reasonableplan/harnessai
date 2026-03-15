from __future__ import annotations

import asyncio
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from src.core.logging.logger import get_logger
from src.core.messaging.message_bus import MessageBus
from src.core.state.state_store import StateStore
from src.core.types import (
    AgentConfig,
    AgentStatus,
    Message,
    MessageType,
    Task,
    TaskComplexity,
    TaskResult,
    TaskStatus,
)

DEFAULT_TASK_TIMEOUT_S = 300.0  # 5분
MAX_BACKOFF_S = 60.0
HEARTBEAT_INTERVAL_CYCLES = 3


class BaseAgent(ABC):
    def __init__(
        self,
        config: AgentConfig,
        message_bus: MessageBus,
        state_store: StateStore,
        git_service: Any,  # IGitService — circular import 방지
    ) -> None:
        self.id = config.id
        self.domain = config.domain
        self.config = config

        self._message_bus = message_bus
        self._state_store = state_store
        self._git_service = git_service
        self._log = get_logger(config.id)

        self._status: AgentStatus = AgentStatus.IDLE
        self._polling = False
        self._poll_task: asyncio.Task | None = None
        self._consecutive_errors = 0
        self._subscriptions: list[tuple[str, Any]] = []

        # config hot-reload 구독
        async def _config_handler(msg: Message) -> None:
            payload = msg.payload or {}
            if isinstance(payload, dict) and payload.get("agentId") == self.id:
                await self._reload_config()

        self._subscribe(MessageType.AGENT_CONFIG_UPDATED, _config_handler)

    # ===== Config Hot-Reload =====

    async def _reload_config(self) -> None:
        db_config = await self._state_store.get_agent_config(self.id)
        if db_config is None:
            return
        self.config = self.config.model_copy(
            update={
                "claude_model": db_config.claude_model,
                "max_tokens": db_config.max_tokens,
                "temperature": db_config.temperature,
                "token_budget": db_config.token_budget,
                "task_timeout_ms": db_config.task_timeout_ms,
                "poll_interval_ms": db_config.poll_interval_ms,
            }
        )
        self._log.info("Config reloaded", config=db_config.model_dump())

    # ===== Status =====

    @property
    def status(self) -> AgentStatus:
        return self._status

    async def _set_status(
        self, status: AgentStatus, task_id: str | None = None, trace_id: str | None = None
    ) -> None:
        self._status = status
        payload: dict[str, Any] = {"status": status.value}
        if task_id:
            payload["taskId"] = task_id
        await self._message_bus.publish(
            Message(
                id=str(uuid.uuid4()),
                type=MessageType.AGENT_STATUS,
                from_agent=self.id,
                payload=payload,
                trace_id=trace_id or str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
            )
        )

    async def _publish_token_usage(self, input_tokens: int, output_tokens: int) -> None:
        await self._message_bus.publish(
            Message(
                id=str(uuid.uuid4()),
                type=MessageType.TOKEN_USAGE,
                from_agent=self.id,
                payload={"inputTokens": input_tokens, "outputTokens": output_tokens},
                trace_id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
            )
        )

    # ===== Polling =====

    def start_polling(self, interval_ms: int = 10_000) -> None:
        if self._polling:
            return
        self._polling = True
        self._poll_task = asyncio.create_task(self._poll_loop(interval_ms))

    def stop_polling(self) -> None:
        self._polling = False
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()

    async def drain(self) -> None:
        """Graceful shutdown: 현재 태스크 완료 대기 후 구독 해제."""
        self.stop_polling()
        for msg_type, handler in self._subscriptions:
            self._message_bus.unsubscribe(msg_type, handler)
        self._subscriptions.clear()
        if self._poll_task:
            try:
                await asyncio.wait_for(asyncio.shield(self._poll_task), timeout=30.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            self._poll_task = None

    async def pause(self) -> None:
        self.stop_polling()
        await self._set_status(AgentStatus.PAUSED)

    async def resume(self, interval_ms: int = 10_000) -> None:
        if self._poll_task and not self._poll_task.done():
            try:
                await self._poll_task
            except (asyncio.CancelledError, Exception):
                pass
        self._poll_task = None
        await self._set_status(AgentStatus.IDLE)
        self.start_polling(interval_ms)

    async def _poll_loop(self, initial_interval_ms: int) -> None:
        cycle_count = 0
        while self._polling:
            cycle_count += 1

            # 하트비트
            if cycle_count % HEARTBEAT_INTERVAL_CYCLES == 0:
                try:
                    await self._state_store.update_heartbeat(self.id)
                except Exception as e:
                    self._log.error("Heartbeat failed", err=str(e))

            if self._status in (AgentStatus.IDLE, AgentStatus.ERROR):
                try:
                    if self._status == AgentStatus.ERROR:
                        self._log.info("Recovering from error state")
                        await self._set_status(AgentStatus.IDLE)

                    task = await self._find_next_task()
                    self._consecutive_errors = 0
                    if task:
                        task_trace_id = str(uuid.uuid4())
                        await self._set_status(AgentStatus.BUSY, task.id, task_trace_id)
                        result = await self._execute_with_timeout(task)
                        await self._on_task_complete(task, result)
                        await self._set_status(AgentStatus.IDLE, None, task_trace_id)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    self._consecutive_errors += 1
                    await self._set_status(AgentStatus.ERROR)
                    self._log.error(
                        "Polling error",
                        err=str(e),
                        consecutive_errors=self._consecutive_errors,
                    )

            interval_s = (self.config.poll_interval_ms or initial_interval_ms) / 1000
            if self._consecutive_errors > 0:
                backoff_s = min(
                    interval_s * (2 ** (self._consecutive_errors - 1)), MAX_BACKOFF_S
                )
            else:
                backoff_s = interval_s

            try:
                await asyncio.sleep(backoff_s)
            except asyncio.CancelledError:
                break

    async def _execute_with_timeout(self, task: Task) -> TaskResult:
        timeout_s = (self.config.task_timeout_ms or DEFAULT_TASK_TIMEOUT_S * 1000) / 1000
        try:
            return await asyncio.wait_for(self.execute_task(task), timeout=timeout_s)
        except asyncio.TimeoutError:
            raise TimeoutError(f'Task "{task.title}" timed out after {timeout_s}s')

    # ===== Subscription =====

    def _subscribe(self, msg_type: str, handler: Any) -> None:
        self._message_bus.subscribe(msg_type, handler)
        self._subscriptions.append((msg_type, handler))

    # ===== Task Finding =====

    async def _find_next_task(self) -> Task | None:
        rows = await self._state_store.get_ready_tasks_for_agent(self.id)
        if not rows:
            return None

        rows.sort(key=lambda r: r.priority or 3)

        for row in rows:
            claimed = await self._state_store.claim_task(row.id)
            if not claimed:
                continue

            # Board 동기화 — 실패 시 DB 롤백
            if row.github_issue_number:
                try:
                    await self._git_service.move_issue_to_column(
                        row.github_issue_number, "In Progress"
                    )
                except Exception as e:
                    self._log.warn(
                        "Failed to sync Board after claim, rolling back",
                        err=str(e),
                        task_id=row.id,
                    )
                    await self._state_store.update_task(
                        row.id,
                        {"status": "ready", "board_column": "Ready", "started_at": None},
                    )
                    continue

            return self._row_to_task(row)

        return None

    def _row_to_task(self, row: Any) -> Task:
        return Task(
            id=row.id,
            epic_id=row.epic_id,
            title=row.title,
            description=row.description or "",
            assigned_agent=row.assigned_agent,
            status=TaskStatus(row.status or "in-progress"),
            github_issue_number=row.github_issue_number,
            board_column=row.board_column or "In Progress",
            dependencies=list(row.dependencies or []),
            priority=row.priority or 3,
            complexity=TaskComplexity(row.complexity or "medium"),
            retry_count=row.retry_count or 0,
            artifacts=[],
            labels=list(row.labels or []),
            review_note=row.review_note,
        )

    # ===== Task Complete =====

    async def _on_task_complete(self, task: Task, result: TaskResult) -> None:
        new_status = "review" if result.success else "failed"
        new_column = "Review" if result.success else "Failed"

        # Board-first: external state before internal state
        if task.github_issue_number:
            try:
                await self._git_service.move_issue_to_column(
                    task.github_issue_number, new_column
                )
            except Exception as e:
                self._log.warn(
                    "Failed to sync Board column after task complete",
                    err=str(e),
                    task_id=task.id,
                    column=new_column,
                )

        updates: dict[str, Any] = {"status": new_status, "board_column": new_column}
        if result.success:
            updates["completed_at"] = datetime.now(timezone.utc)
        await self._state_store.update_task(task.id, updates)

        await self._message_bus.publish(
            Message(
                id=str(uuid.uuid4()),
                type=MessageType.REVIEW_REQUEST,
                from_agent=self.id,
                payload={"taskId": task.id, "result": result.model_dump()},
                trace_id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
            )
        )

    @abstractmethod
    async def execute_task(self, task: Task) -> TaskResult:
        """태스크를 실행한다. 서브클래스에서 구현."""
        ...
