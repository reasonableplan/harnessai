"""hooks 라우트 테스트 — 목록, 토글."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.dashboard.routes.deps import get_state_store
from src.dashboard.server import create_app


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.get_all_hooks = AsyncMock(return_value=[])
    store.toggle_hook = AsyncMock()
    return store


@pytest.fixture
def client(mock_store):
    app = create_app(auth_token=None)
    app.dependency_overrides[get_state_store] = lambda: mock_store
    return TestClient(app), mock_store


class TestListHooks:
    def test_empty_list(self, client):
        c, _ = client
        resp = c.get("/api/hooks")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_hooks_with_data(self, client):
        c, store = client
        hook = MagicMock()
        hook.model_dump.return_value = {"id": "h1", "name": "auto-review", "enabled": True}
        store.get_all_hooks = AsyncMock(return_value=[hook])

        resp = c.get("/api/hooks")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "h1"


class TestToggleHook:
    def test_toggle_enabled(self, client):
        c, store = client
        resp = c.put("/api/hooks/hook-1/toggle", json={"enabled": True})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        store.toggle_hook.assert_called_once_with("hook-1", True)

    def test_toggle_disabled(self, client):
        c, store = client
        resp = c.put("/api/hooks/hook-1/toggle", json={"enabled": False})
        assert resp.status_code == 200
        store.toggle_hook.assert_called_once_with("hook-1", False)

    def test_toggle_missing_body(self, client):
        c, _ = client
        resp = c.put("/api/hooks/hook-1/toggle")
        assert resp.status_code == 422

    def test_hook_id_too_long_rejected(self, client):
        """64자 초과 hook_id는 422."""
        c, _ = client
        resp = c.put(f"/api/hooks/{'x' * 65}/toggle", json={"enabled": True})
        assert resp.status_code == 422
