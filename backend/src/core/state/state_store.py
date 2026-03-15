from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, case, desc, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.db.schema import (
    AgentConfigModel,
    AgentModel,
    ArtifactModel,
    EpicModel,
    HookModel,
    MessageModel,
    TaskModel,
)
from src.core.logging.logger import get_logger
from src.core.state.task_state_machine import is_valid_transition
from src.core.types import (
    AgentConfigRow,
    AgentStats,
    HookRow,
    Message,
    TaskHistoryEntry,
    TaskStatus,
)

log = get_logger("StateStore")


class StateStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # ===== Agent =====

    async def register_agent(self, agent_data: dict[str, Any]) -> None:
        async with self._session_factory() as session:
            existing = await session.get(AgentModel, agent_data["id"])
            if existing:
                existing.status = agent_data.get("status", "idle")
                existing.last_heartbeat = datetime.now(timezone.utc)
            else:
                session.add(AgentModel(**agent_data))
            await session.commit()

    async def get_agent(self, agent_id: str) -> AgentModel | None:
        async with self._session_factory() as session:
            return await session.get(AgentModel, agent_id)

    async def update_agent_status(self, agent_id: str, status: str) -> None:
        async with self._session_factory() as session:
            await session.execute(
                update(AgentModel).where(AgentModel.id == agent_id).values(status=status)
            )
            await session.commit()

    async def update_heartbeat(self, agent_id: str) -> None:
        async with self._session_factory() as session:
            await session.execute(
                update(AgentModel)
                .where(AgentModel.id == agent_id)
                .values(last_heartbeat=datetime.now(timezone.utc))
            )
            await session.commit()

    # ===== Task =====

    async def create_task(self, task_data: dict[str, Any]) -> None:
        async with self._session_factory() as session:
            session.add(TaskModel(**task_data))
            await session.commit()

    async def get_task(self, task_id: str) -> TaskModel | None:
        async with self._session_factory() as session:
            return await session.get(TaskModel, task_id)

    async def update_task(self, task_id: str, updates: dict[str, Any]) -> None:
        async with self._session_factory() as session:
            # Extract special increment directive (not a real column)
            values = dict(updates)
            retry_increment = values.pop("retry_count_increment", None)

            if "status" in values:
                result = await session.execute(
                    select(TaskModel.status).where(TaskModel.id == task_id)
                )
                row = result.scalar_one_or_none()
                if row is None:
                    log.warn("update_task: task not found", task_id=task_id)
                    return

                from_status = TaskStatus(row)
                to_status = TaskStatus(values["status"])
                if not is_valid_transition(from_status, to_status):
                    log.warn(
                        "Invalid task status transition, skipping",
                        task_id=task_id,
                        from_status=from_status,
                        to_status=to_status,
                    )
                    return

                if retry_increment:
                    values["retry_count"] = TaskModel.retry_count + retry_increment

                # Atomic WHERE: status=from prevents race conditions
                await session.execute(
                    update(TaskModel)
                    .where(and_(TaskModel.id == task_id, TaskModel.status == row))
                    .values(**values)
                )
            else:
                if retry_increment:
                    values["retry_count"] = TaskModel.retry_count + retry_increment
                await session.execute(
                    update(TaskModel).where(TaskModel.id == task_id).values(**values)
                )
            await session.commit()

    async def get_tasks_by_column(self, column: str) -> list[TaskModel]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(TaskModel).where(TaskModel.board_column == column)
            )
            return list(result.scalars().all())

    async def get_tasks_by_ids(self, ids: list[str]) -> list[TaskModel]:
        if not ids:
            return []
        async with self._session_factory() as session:
            result = await session.execute(
                select(TaskModel).where(TaskModel.id.in_(ids))
            )
            return list(result.scalars().all())

    async def get_tasks_by_agent(self, agent_id: str) -> list[TaskModel]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(TaskModel).where(TaskModel.assigned_agent == agent_id)
            )
            return list(result.scalars().all())

    async def get_ready_tasks_for_agent(self, agent_id: str) -> list[TaskModel]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(TaskModel).where(
                    and_(
                        TaskModel.board_column == "Ready",
                        TaskModel.assigned_agent == agent_id,
                    )
                )
            )
            return list(result.scalars().all())

    async def claim_task(self, task_id: str) -> bool:
        """Atomic: Ready → In Progress. 다른 에이전트가 먼저 선점하면 False 반환."""
        async with self._session_factory() as session:
            result = await session.execute(
                update(TaskModel)
                .where(
                    and_(
                        TaskModel.id == task_id,
                        TaskModel.board_column == "Ready",
                        TaskModel.status == "ready",
                    )
                )
                .values(
                    board_column="In Progress",
                    status="in-progress",
                    started_at=datetime.now(timezone.utc),
                )
                .returning(TaskModel.id)
            )
            await session.commit()
            return result.scalar_one_or_none() is not None

    # ===== Epic =====

    async def create_epic(self, epic_data: dict[str, Any]) -> None:
        async with self._session_factory() as session:
            session.add(EpicModel(**epic_data))
            await session.commit()

    async def get_epic(self, epic_id: str) -> EpicModel | None:
        async with self._session_factory() as session:
            return await session.get(EpicModel, epic_id)

    async def update_epic(self, epic_id: str, updates: dict[str, Any]) -> None:
        async with self._session_factory() as session:
            await session.execute(
                update(EpicModel).where(EpicModel.id == epic_id).values(**updates)
            )
            await session.commit()

    # ===== Message =====

    async def save_message(self, message: Message) -> None:
        async with self._session_factory() as session:
            session.add(
                MessageModel(
                    id=message.id,
                    type=message.type,
                    from_agent=message.from_agent,
                    to_agent=message.to_agent,
                    payload=message.payload if isinstance(message.payload, dict) else {"data": message.payload},
                    trace_id=message.trace_id,
                    created_at=message.timestamp,
                )
            )
            await session.commit()

    # ===== Artifact =====

    async def save_artifact(self, artifact_data: dict[str, Any]) -> None:
        async with self._session_factory() as session:
            session.add(ArtifactModel(**artifact_data))
            await session.commit()

    # ===== Dashboard Queries =====

    async def get_all_agents(self) -> list[AgentModel]:
        async with self._session_factory() as session:
            result = await session.execute(select(AgentModel))
            return list(result.scalars().all())

    async def get_all_tasks(self) -> list[TaskModel]:
        async with self._session_factory() as session:
            result = await session.execute(select(TaskModel))
            return list(result.scalars().all())

    async def get_all_epics(self) -> list[EpicModel]:
        async with self._session_factory() as session:
            result = await session.execute(select(EpicModel))
            return list(result.scalars().all())

    async def get_recent_messages(self, limit: int) -> list[Message]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(MessageModel).order_by(desc(MessageModel.created_at)).limit(limit)
            )
            rows = result.scalars().all()
            return [
                Message(
                    id=r.id,
                    type=r.type,
                    from_agent=r.from_agent,
                    to_agent=r.to_agent,
                    payload=r.payload,
                    trace_id=r.trace_id or "",
                    timestamp=r.created_at or datetime.now(timezone.utc),
                )
                for r in rows
            ]

    # ===== Stats & History =====

    async def get_agent_stats(self, agent_id: str) -> AgentStats:
        async with self._session_factory() as session:
            result = await session.execute(
                select(
                    func.count().label("total_tasks"),
                    func.count(
                        case((TaskModel.status == "done", 1))
                    ).label("completed_tasks"),
                    func.count(
                        case((TaskModel.status == "failed", 1))
                    ).label("failed_tasks"),
                    func.count(
                        case((TaskModel.status == "in-progress", 1))
                    ).label("in_progress_tasks"),
                    func.coalesce(func.sum(TaskModel.retry_count), 0).label("total_retries"),
                    func.avg(
                        case(
                            (
                                and_(
                                    TaskModel.status == "done",
                                    TaskModel.completed_at.isnot(None),
                                    TaskModel.started_at.isnot(None),
                                ),
                                func.extract(
                                    "epoch",
                                    TaskModel.completed_at - TaskModel.started_at,
                                ) * 1000,
                            )
                        )
                    ).label("avg_duration_ms"),
                ).where(TaskModel.assigned_agent == agent_id)
            )
            row = result.one()
            total = int(row.total_tasks or 0)
            completed = int(row.completed_tasks or 0)
            return AgentStats(
                agent_id=agent_id,
                total_tasks=total,
                completed_tasks=completed,
                failed_tasks=int(row.failed_tasks or 0),
                in_progress_tasks=int(row.in_progress_tasks or 0),
                completion_rate=completed / total if total > 0 else 0.0,
                avg_duration_ms=float(row.avg_duration_ms) if row.avg_duration_ms is not None else None,
                total_retries=int(row.total_retries or 0),
            )

    async def get_task_history(self, task_id: str) -> list[TaskHistoryEntry]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(MessageModel)
                .where(text("payload->>'taskId' = :task_id").bindparams(task_id=task_id))
                .order_by(desc(MessageModel.created_at))
                .limit(50)
            )
            rows = result.scalars().all()
            entries = []
            for r in rows:
                payload = r.payload or {}
                if "status" in payload:
                    detail = f"status: {payload['status']}"
                elif "result" in payload:
                    result_data = payload["result"]
                    success = result_data.get("success", False) if isinstance(result_data, dict) else False
                    detail = f"result: {'success' if success else 'failure'}"
                else:
                    detail = str(payload)[:120]
                entries.append(
                    TaskHistoryEntry(
                        timestamp=r.created_at or datetime.now(timezone.utc),
                        type=r.type,
                        from_agent=r.from_agent,
                        detail=detail,
                    )
                )
            return entries

    # ===== Agent Config =====

    async def get_agent_config(self, agent_id: str) -> AgentConfigRow | None:
        async with self._session_factory() as session:
            row = await session.get(AgentConfigModel, agent_id)
            if row is None:
                return None
            return AgentConfigRow(
                agent_id=row.agent_id,
                claude_model=row.claude_model,
                max_tokens=row.max_tokens,
                temperature=row.temperature,
                token_budget=row.token_budget,
                task_timeout_ms=row.task_timeout_ms,
                poll_interval_ms=row.poll_interval_ms,
                updated_at=row.updated_at,
            )

    async def upsert_agent_config(self, agent_id: str, config: dict[str, Any]) -> None:
        async with self._session_factory() as session:
            existing = await session.get(AgentConfigModel, agent_id)
            config["updated_at"] = datetime.now(timezone.utc)
            if existing:
                for k, v in config.items():
                    if hasattr(existing, k):
                        setattr(existing, k, v)
            else:
                session.add(AgentConfigModel(agent_id=agent_id, **config))
            await session.commit()

    # ===== Hooks =====

    async def get_all_hooks(self) -> list[HookRow]:
        async with self._session_factory() as session:
            result = await session.execute(select(HookModel))
            return [
                HookRow(
                    id=r.id,
                    event=r.event,
                    name=r.name,
                    description=r.description,
                    enabled=r.enabled,
                    created_at=r.created_at,
                )
                for r in result.scalars().all()
            ]

    async def upsert_hook(self, hook: HookRow) -> None:
        async with self._session_factory() as session:
            existing = await session.get(HookModel, hook.id)
            if existing:
                existing.enabled = hook.enabled
                existing.name = hook.name
                existing.description = hook.description
            else:
                session.add(
                    HookModel(
                        id=hook.id,
                        event=hook.event,
                        name=hook.name,
                        description=hook.description,
                        enabled=hook.enabled,
                    )
                )
            await session.commit()

    async def toggle_hook(self, hook_id: str, enabled: bool) -> None:
        async with self._session_factory() as session:
            await session.execute(
                update(HookModel).where(HookModel.id == hook_id).values(enabled=enabled)
            )
            await session.commit()
