"""StateStore 테스트 — SQLite in-memory DB 사용."""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.core.db.schema import Base
from src.core.state.state_store import StateStore
from src.core.types import TaskStatus


@pytest.fixture
async def store():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield StateStore(factory)
    await engine.dispose()


@pytest.mark.asyncio
async def test_register_and_get_agent(store: StateStore):
    await store.register_agent({
        "id": "agent-1",
        "domain": "backend",
        "level": 2,
        "status": "idle",
    })
    agent = await store.get_agent("agent-1")
    assert agent is not None
    assert agent.domain == "backend"
    assert agent.status == "idle"


@pytest.mark.asyncio
async def test_register_agent_upsert(store: StateStore):
    await store.register_agent({"id": "agent-1", "domain": "backend", "level": 2, "status": "idle"})
    await store.register_agent({"id": "agent-1", "domain": "backend", "level": 2, "status": "busy"})
    agent = await store.get_agent("agent-1")
    assert agent.status == "busy"


@pytest.mark.asyncio
async def test_update_agent_status(store: StateStore):
    await store.register_agent({"id": "agent-1", "domain": "backend", "level": 2, "status": "idle"})
    await store.update_agent_status("agent-1", "busy")
    agent = await store.get_agent("agent-1")
    assert agent.status == "busy"


@pytest.mark.asyncio
async def test_update_heartbeat(store: StateStore):
    await store.register_agent({"id": "agent-1", "domain": "backend", "level": 2, "status": "idle"})
    await store.update_heartbeat("agent-1")
    agent = await store.get_agent("agent-1")
    assert agent.last_heartbeat is not None


@pytest.mark.asyncio
async def test_create_and_get_task(store: StateStore):
    await store.register_agent({"id": "agent-1", "domain": "backend", "level": 2, "status": "idle"})
    await store.create_task({
        "id": "task-1",
        "title": "Test task",
        "status": "ready",
        "board_column": "Ready",
        "assigned_agent": "agent-1",
        "priority": 2,
        "dependencies": [],
        "labels": [],
        "retry_count": 0,
    })
    task = await store.get_task("task-1")
    assert task is not None
    assert task.title == "Test task"
    assert task.status == "ready"


@pytest.mark.asyncio
async def test_claim_task(store: StateStore):
    await store.register_agent({"id": "agent-1", "domain": "backend", "level": 2, "status": "idle"})
    await store.create_task({
        "id": "task-1",
        "title": "Test task",
        "status": "ready",
        "board_column": "Ready",
        "assigned_agent": "agent-1",
        "priority": 2,
        "dependencies": [],
        "labels": [],
        "retry_count": 0,
    })
    claimed = await store.claim_task("task-1")
    assert claimed is True

    task = await store.get_task("task-1")
    assert task.status == "in-progress"
    assert task.board_column == "In Progress"
    assert task.started_at is not None


@pytest.mark.asyncio
async def test_claim_task_twice_fails(store: StateStore):
    await store.register_agent({"id": "agent-1", "domain": "backend", "level": 2, "status": "idle"})
    await store.create_task({
        "id": "task-1",
        "title": "Test task",
        "status": "ready",
        "board_column": "Ready",
        "assigned_agent": "agent-1",
        "priority": 2,
        "dependencies": [],
        "labels": [],
        "retry_count": 0,
    })
    first = await store.claim_task("task-1")
    second = await store.claim_task("task-1")
    assert first is True
    assert second is False


@pytest.mark.asyncio
async def test_get_ready_tasks_for_agent(store: StateStore):
    await store.register_agent({"id": "agent-1", "domain": "backend", "level": 2, "status": "idle"})
    await store.create_task({
        "id": "task-1", "title": "T1", "status": "ready", "board_column": "Ready",
        "assigned_agent": "agent-1", "priority": 2, "dependencies": [], "labels": [], "retry_count": 0,
    })
    await store.create_task({
        "id": "task-2", "title": "T2", "status": "backlog", "board_column": "Backlog",
        "assigned_agent": "agent-1", "priority": 3, "dependencies": [], "labels": [], "retry_count": 0,
    })
    tasks = await store.get_ready_tasks_for_agent("agent-1")
    assert len(tasks) == 1
    assert tasks[0].id == "task-1"


@pytest.mark.asyncio
async def test_invalid_status_transition_skipped(store: StateStore):
    await store.register_agent({"id": "agent-1", "domain": "backend", "level": 2, "status": "idle"})
    await store.create_task({
        "id": "task-1", "title": "T1", "status": "backlog", "board_column": "Backlog",
        "assigned_agent": "agent-1", "priority": 2, "dependencies": [], "labels": [], "retry_count": 0,
    })
    # backlog → done 은 유효하지 않은 전환
    await store.update_task("task-1", {"status": "done"})
    task = await store.get_task("task-1")
    assert task.status == "backlog"  # 변경되지 않아야 함


@pytest.mark.asyncio
async def test_get_all_agents(store: StateStore):
    await store.register_agent({"id": "a1", "domain": "backend", "level": 2, "status": "idle"})
    await store.register_agent({"id": "a2", "domain": "frontend", "level": 2, "status": "idle"})
    agents = await store.get_all_agents()
    assert len(agents) == 2


@pytest.mark.asyncio
async def test_upsert_agent_config(store: StateStore):
    await store.register_agent({"id": "agent-1", "domain": "backend", "level": 2, "status": "idle"})
    await store.upsert_agent_config("agent-1", {"claude_model": "claude-opus-4-20250514", "max_tokens": 8192})
    config = await store.get_agent_config("agent-1")
    assert config is not None
    assert config.claude_model == "claude-opus-4-20250514"
    assert config.max_tokens == 8192


@pytest.mark.asyncio
async def test_toggle_hook(store: StateStore):
    from src.core.types import HookRow
    hook = HookRow(id="hook-1", event="hook.task.completed", name="Test Hook", enabled=True)
    await store.upsert_hook(hook)
    await store.toggle_hook("hook-1", False)
    hooks = await store.get_all_hooks()
    assert hooks[0].enabled is False
