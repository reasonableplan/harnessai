from __future__ import annotations

import asyncio
import time
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

DEFAULT_TASK_TIMEOUT_S = 360.0  # 6분 (CLI timeout + 여유 60s)
MAX_BACKOFF_S = 60.0
HEARTBEAT_INTERVAL_CYCLES = 3


def _now_ms() -> int:
    return int(time.monotonic() * 1000)


class BaseAgent(ABC):
    # 워크트리 → workspace sync 시 파일 충돌 방지 (전 에이전트 공유)
    _sync_lock: asyncio.Lock | None = None

    @classmethod
    def _get_sync_lock(cls) -> asyncio.Lock:
        if cls._sync_lock is None:
            cls._sync_lock = asyncio.Lock()
        return cls._sync_lock

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
        self._active_worktree: str | None = None  # 현재 태스크의 worktree 경로
        self._token_budget: Any | None = None  # TokenBudgetManager (옵셔널)

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

    async def _publish_progress(
        self, task_id: str, stage: str, detail: str = "",
    ) -> None:
        """실시간 진행률 이벤트를 발행한다."""
        await self._message_bus.publish(
            Message(
                id=str(uuid.uuid4()),
                type=MessageType.TASK_PROGRESS,
                from_agent=self.id,
                payload={"taskId": task_id, "stage": stage, "detail": detail},
                trace_id=str(uuid.uuid4()),
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
                await asyncio.wait_for(asyncio.shield(self._poll_task), timeout=5.0)
            except asyncio.CancelledError:
                pass
            except asyncio.TimeoutError:
                self._log.warning("Previous poll task did not finish in time, proceeding")
            except Exception as e:
                self._log.error("Previous poll task error during resume", err=str(e))
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
                    if task:
                        task_trace_id = str(uuid.uuid4())
                        await self._set_status(AgentStatus.BUSY, task.id, task_trace_id)
                        # 워크트리 생성 (격리된 작업 공간)
                        try:
                            await self._setup_worktree(task)
                        except Exception as wt_err:
                            # worktree 실패 → 부분 생성된 worktree 정리 + 태스크 failed
                            await self._cleanup_worktree(task)
                            self._log.error(
                                "Worktree setup failed, marking task as failed",
                                task_id=task.id, err=str(wt_err),
                            )
                            await self._on_task_complete(
                                task,
                                TaskResult(
                                    success=False,
                                    error={"message": f"Worktree creation failed: {wt_err}"},
                                    artifacts=[],
                                ),
                            )
                            await self._set_status(AgentStatus.IDLE, None, task_trace_id)
                            continue
                        try:
                            result = await self._execute_with_timeout(task)
                            # CLI가 main workspace에 직접 쓴 경우 sync 건너뜀
                            if not getattr(result, "skip_sync", False):
                                await self._sync_worktree_to_workspace(task)
                            await self._remap_artifact_paths(task)
                            await self._on_task_complete(task, result)
                        except (TimeoutError, Exception) as exec_err:
                            # 타임아웃/예외 시 태스크를 failed로 마킹 (in-progress 고착 방지)
                            self._log.error(
                                "Task execution error, marking as failed",
                                task_id=task.id, err=str(exec_err),
                            )
                            await self._on_task_complete(
                                task,
                                TaskResult(
                                    success=False,
                                    error={"message": str(exec_err)[:500]},
                                    artifacts=[],
                                ),
                            )
                        finally:
                            # 워크트리 정리 (리뷰/머지 후 — 파일은 이미 workspace에 복사됨)
                            await self._cleanup_worktree(task)
                        self._consecutive_errors = 0
                        await self._set_status(AgentStatus.IDLE, None, task_trace_id)
                    else:
                        self._consecutive_errors = 0
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

        log_id = str(uuid.uuid4())
        start_ms = _now_ms()
        attempt = (task.retry_count or 0) + 1

        # 토큰 예산 체크
        if self._token_budget:
            allowed, reason = await self._token_budget.check_budget(task.id)
            if not allowed:
                try:
                    await self._state_store.create_task_log({
                        "id": log_id,
                        "task_id": task.id,
                        "agent_id": self.id,
                        "attempt": attempt,
                        "status": "budget_exceeded",
                        "duration_ms": 0,
                    })
                except Exception as e:
                    self._log.warning("Failed to create budget log", err=str(e))
                return TaskResult(
                    success=False,
                    error={"message": reason},
                    artifacts=[],
                )

        # 실행 로그 생성 (started)
        try:
            await self._state_store.create_task_log({
                "id": log_id,
                "task_id": task.id,
                "agent_id": self.id,
                "attempt": attempt,
                "status": "started",
            })
        except Exception as e:
            self._log.warning("Failed to create task log", err=str(e))

        try:
            # LLM 토큰 사용량 추정을 위해 실행 전 값 저장
            llm = getattr(self, "_llm", None)
            tokens_before = getattr(llm, "tokens_used", 0) if llm else 0

            result = await asyncio.wait_for(self.execute_task(task), timeout=timeout_s)

            # 토큰 추정치 계산
            tokens_after = getattr(llm, "tokens_used", 0) if llm else 0
            token_delta = max(tokens_after - tokens_before, 0)
            est_input = token_delta // 2
            est_output = token_delta - est_input

            # 성공/실패 로그 업데이트 (토큰 포함)
            log_status = "success" if result.success else "failed"
            await self._update_task_log(
                log_id, log_status, start_ms,
                token_input=est_input, token_output=est_output,
            )
            return result
        except asyncio.TimeoutError:
            await self._update_task_log(log_id, "timeout", start_ms)
            raise TimeoutError(f'Task "{task.title}" timed out after {timeout_s}s')
        except Exception:
            await self._update_task_log(log_id, "failed", start_ms)
            raise

    async def _update_task_log(
        self, log_id: str, status: str, start_ms: int,
        token_input: int = 0, token_output: int = 0,
    ) -> None:
        try:
            updates: dict[str, Any] = {
                "status": status,
                "duration_ms": _now_ms() - start_ms,
            }
            if token_input or token_output:
                updates["token_input"] = token_input
                updates["token_output"] = token_output
            await self._state_store.update_task_log(log_id, updates)
        except Exception as e:
            self._log.warning("Failed to update task log", err=str(e))

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
                    self._log.warning(
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

    # ===== Worktree Lifecycle =====

    async def _setup_worktree(self, task: Task) -> None:
        """태스크 시작 시 독립 worktree를 생성한다."""
        try:
            from pathlib import Path

            branch_name = "task"
            worktree_path = await self._git_service.create_worktree(
                task.id, branch_name,
            )
            # sandbox 검증: worktree가 workspace 하위인지 확인
            ws_root = Path(self._git_service.work_dir).resolve()
            wt_resolved = Path(worktree_path).resolve()
            if not wt_resolved.is_relative_to(ws_root):
                self._log.error(
                    "SECURITY: worktree path outside workspace, rejecting",
                    path=worktree_path, workspace=str(ws_root),
                )
                self._active_worktree = None
                raise RuntimeError("SECURITY: worktree path outside workspace")

            self._active_worktree = worktree_path
            self._log.info("Worktree ready", task_id=task.id, path=worktree_path)
        except Exception as e:
            self._log.error(
                "Worktree creation failed, task cannot proceed",
                task_id=task.id, err=str(e),
            )
            self._active_worktree = None
            raise RuntimeError(f"Worktree creation failed for task {task.id}: {e}") from e

    async def _sync_worktree_to_workspace(self, task: Task) -> None:
        """워크트리의 변경사항을 공유 workspace로 복사한다.

        워커는 worktree에 파일만 쓰고 커밋하지 않으므로,
        git diff 대신 파일 시스템 직접 복사 방식을 사용한다.
        Lock으로 동시 sync를 방지하여 파일 충돌을 차단한다.
        """
        if not self._active_worktree:
            return
        async with self._get_sync_lock():
            try:
                import shutil
                from pathlib import Path

                wt = Path(self._active_worktree)
                ws = Path(self._git_service.work_dir)
                if not wt.exists() or not ws.exists():
                    return

                skip_dirs = {".git", ".venv", "node_modules", "__pycache__", ".worktrees"}

                def _do_sync() -> int:
                    count = 0
                    for src_file in wt.rglob("*"):
                        if not src_file.is_file():
                            continue
                        rel = src_file.relative_to(wt)
                        if any(d in rel.parts for d in skip_dirs):
                            continue
                        dst = ws / rel
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(str(src_file), str(dst))
                        count += 1
                    return count

                copied = await asyncio.to_thread(_do_sync)
                self._log.info("Worktree synced to workspace",
                               task_id=task.id, files=copied)
            except Exception as e:
                self._log.warning(
                    "Worktree sync failed", task_id=task.id, err=str(e),
                )

    async def _remap_artifact_paths(self, task: Task) -> None:
        """artifact의 file_path를 worktree → workspace 기준으로 재매핑한다.

        worktree 삭제 후에도 artifact 경로가 유효하도록 보장.
        """
        if not self._active_worktree:
            return
        try:
            from pathlib import Path

            wt = Path(self._active_worktree)
            ws = Path(self._git_service.work_dir)
            artifacts = await self._state_store.get_artifacts_for_task(task.id)
            for art in artifacts:
                fpath = Path(art.file_path)
                try:
                    rel = fpath.relative_to(wt)
                    new_path = str(ws / rel)
                    await self._state_store.update_artifact_path(art.id, new_path)
                except ValueError:
                    pass  # worktree 경로가 아닌 경우 무시
            self._log.info("Artifact paths remapped", task_id=task.id)
        except Exception as e:
            self._log.warning(
                "Artifact path remap failed", task_id=task.id, err=str(e),
            )

    async def _cleanup_worktree(self, task: Task) -> None:
        """태스크 완료 후 worktree를 정리한다."""
        if not self._active_worktree:
            return
        try:
            await self._git_service.remove_worktree(task.id)
        except Exception as e:
            self._log.warning(
                "Worktree cleanup failed", task_id=task.id, err=str(e),
            )
        finally:
            self._active_worktree = None

    # ===== Task Complete =====

    async def _on_task_complete(self, task: Task, result: TaskResult) -> None:
        new_status = "review" if result.success else "failed"
        new_column = "Review" if result.success else "Failed"
        if not result.success:
            self._log.warning("Task failed", task_id=task.id, error=result.error)

        # Board-first: external state before internal state
        if task.github_issue_number:
            try:
                await self._git_service.move_issue_to_column(
                    task.github_issue_number, new_column
                )
            except Exception as e:
                self._log.warning(
                    "Failed to sync Board column after task complete",
                    err=str(e),
                    task_id=task.id,
                    column=new_column,
                )
                return  # Board-first: do not update DB if Board failed

        updates: dict[str, Any] = {"status": new_status, "board_column": new_column}
        if result.success:
            updates["completed_at"] = datetime.now(timezone.utc)
        await self._state_store.update_task(task.id, updates)

        # 성공한 태스크만 Director 리뷰 요청 (실패 태스크는 Board=Failed로 이미 처리됨)
        if result.success:
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
