"""agents 라우트 테스트 — 에이전트 존재 확인, claude_model 화이트리스트."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.core.llm.claude_client import ALLOWED_MODELS
from src.dashboard.routes.deps import get_state_store
from src.dashboard.server import create_app


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.get_all_agents = AsyncMock(return_value=[])
    store.get_agent_config = AsyncMock(return_value=None)
    store.upsert_agent_config = AsyncMock()
    return store


@pytest.fixture
def client(mock_store):
    app = create_app(auth_token=None)
    app.dependency_overrides[get_state_store] = lambda: mock_store
    return TestClient(app), mock_store


class TestAgentExistenceCheck:
    def test_put_config_404_for_unknown_agent(self, client):
        c, store = client
        store.get_all_agents = AsyncMock(return_value=[])

        resp = c.put("/api/agents/unknown-agent/config", json={"max_tokens": 1024})
        assert resp.status_code == 404

    def test_put_config_200_for_known_agent(self, client):
        c, store = client
        agent = MagicMock()
        agent.id = "agent-backend"
        store.get_all_agents = AsyncMock(return_value=[agent])

        resp = c.put("/api/agents/agent-backend/config", json={"max_tokens": 1024})
        assert resp.status_code == 200

    def test_put_config_no_fields_400(self, client):
        c, store = client
        agent = MagicMock()
        agent.id = "agent-backend"
        store.get_all_agents = AsyncMock(return_value=[agent])

        resp = c.put("/api/agents/agent-backend/config", json={})
        assert resp.status_code == 400


class TestClaudeModelWhitelist:
    def test_valid_model_accepted(self, client):
        c, store = client
        agent = MagicMock()
        agent.id = "agent-backend"
        store.get_all_agents = AsyncMock(return_value=[agent])

        valid_model = next(iter(ALLOWED_MODELS))
        resp = c.put("/api/agents/agent-backend/config", json={"claude_model": valid_model})
        assert resp.status_code == 200

    def test_invalid_model_rejected(self, client):
        c, store = client
        agent = MagicMock()
        agent.id = "agent-backend"
        store.get_all_agents = AsyncMock(return_value=[agent])

        resp = c.put("/api/agents/agent-backend/config", json={"claude_model": "gpt-4-invented"})
        assert resp.status_code == 422

    def test_empty_model_rejected(self, client):
        c, store = client
        agent = MagicMock()
        agent.id = "agent-backend"
        store.get_all_agents = AsyncMock(return_value=[agent])

        resp = c.put("/api/agents/agent-backend/config", json={"claude_model": ""})
        assert resp.status_code == 422
