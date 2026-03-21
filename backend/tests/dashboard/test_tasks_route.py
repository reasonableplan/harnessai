"""tasks 라우트 테스트 — 목록 조회, 히스토리."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.dashboard.routes.deps import get_state_store
from src.dashboard.server import create_app


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.get_all_tasks = AsyncMock(return_value=[])
    store.get_task_history = AsyncMock(return_value=[])
    return store


@pytest.fixture
def client(mock_store):
    app = create_app(auth_token=None)
    app.dependency_overrides[get_state_store] = lambda: mock_store
    return TestClient(app), mock_store


class TestListTasks:
    def test_empty_list(self, client):
        c, _ = client
        resp = c.get("/api/tasks")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_tasks_with_data(self, client):
        c, store = client
        task = MagicMock(
            id="t1", epic_id="e1", title="Test", status="ready",
            board_column="Ready", assigned_agent=None, priority=1, retry_count=0,
        )
        store.get_all_tasks = AsyncMock(return_value=[task])

        resp = c.get("/api/tasks")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "t1"
        assert data[0]["status"] == "ready"


class TestTaskHistory:
    def test_empty_history(self, client):
        c, _ = client
        resp = c.get("/api/tasks/task-1/history")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_history_with_entries(self, client):
        c, store = client
        entry = MagicMock()
        entry.model_dump.return_value = {"id": "m1", "type": "BOARD_MOVE", "payload": {}}
        store.get_task_history = AsyncMock(return_value=[entry])

        resp = c.get("/api/tasks/task-1/history")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["type"] == "BOARD_MOVE"

    def test_task_id_too_long_rejected(self, client):
        """64자 초과 task_id는 422."""
        c, _ = client
        resp = c.get(f"/api/tasks/{'x' * 65}/history")
        assert resp.status_code == 422
