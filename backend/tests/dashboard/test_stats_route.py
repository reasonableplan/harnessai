"""stats 라우트 테스트 — summary 엔드포인트, 부분 실패 허용."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.dashboard.routes.deps import get_state_store
from src.dashboard.server import create_app


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.get_all_agents = AsyncMock(return_value=[])
    store.get_all_tasks = AsyncMock(return_value=[])
    store.get_all_epics = AsyncMock(return_value=[])
    return store


@pytest.fixture
def client(mock_store):
    app = create_app(auth_token=None)
    app.dependency_overrides[get_state_store] = lambda: mock_store
    return TestClient(app), mock_store


class TestSummary:
    def test_empty_summary(self, client):
        c, _ = client
        resp = c.get("/api/stats/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["totalAgents"] == 0
        assert data["totalTasks"] == 0
        assert data["totalEpics"] == 0
        assert data["tasksByStatus"] == {}

    def test_summary_with_data(self, client):
        c, store = client
        agent = MagicMock()
        task1 = MagicMock(status="ready")
        task2 = MagicMock(status="ready")
        task3 = MagicMock(status="done")
        epic = MagicMock()
        store.get_all_agents = AsyncMock(return_value=[agent])
        store.get_all_tasks = AsyncMock(return_value=[task1, task2, task3])
        store.get_all_epics = AsyncMock(return_value=[epic])

        resp = c.get("/api/stats/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["totalAgents"] == 1
        assert data["totalTasks"] == 3
        assert data["totalEpics"] == 1
        assert data["tasksByStatus"]["ready"] == 2
        assert data["tasksByStatus"]["done"] == 1

    def test_summary_partial_failure(self, client):
        """하나의 쿼리가 실패해도 나머지는 정상 반환."""
        c, store = client
        agent = MagicMock()
        store.get_all_agents = AsyncMock(return_value=[agent])
        store.get_all_tasks = AsyncMock(side_effect=RuntimeError("DB error"))
        store.get_all_epics = AsyncMock(return_value=[])

        resp = c.get("/api/stats/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["totalAgents"] == 1
        assert data["totalTasks"] == 0  # 실패한 쿼리는 빈 배열
        assert data["totalEpics"] == 0
