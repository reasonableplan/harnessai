"""POST /api/command 엔드포인트 테스트."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.dashboard.routes.deps import get_director
from src.dashboard.server import create_app


def _make_client(auth_token: str | None = None) -> tuple[TestClient, MagicMock]:
    app = create_app(auth_token=auth_token)

    mock_director = MagicMock()
    mock_director.handle_user_input = AsyncMock()
    app.dependency_overrides[get_director] = lambda: mock_director

    return TestClient(app, raise_server_exceptions=True), mock_director


def test_command_accepted():
    client, _ = _make_client()
    resp = client.post("/api/command", json={"content": "사용자 요청 테스트"})
    assert resp.status_code == 202
    assert resp.json() == {"status": "accepted"}


def test_command_empty_content_rejected():
    client, _ = _make_client()
    resp = client.post("/api/command", json={"content": ""})
    assert resp.status_code == 422


def test_command_missing_body_rejected():
    client, _ = _make_client()
    resp = client.post("/api/command", json={})
    assert resp.status_code == 422


def test_command_content_too_long_rejected():
    client, _ = _make_client()
    resp = client.post("/api/command", json={"content": "x" * 4097})
    assert resp.status_code == 422


def test_command_auth_required():
    """인증 토큰 없이 요청하면 401 반환."""
    client, _ = _make_client(auth_token="secret-token")
    resp = client.post("/api/command", json={"content": "test"})
    assert resp.status_code == 401


def test_command_with_valid_token():
    """올바른 Bearer 토큰으로 요청하면 202 반환."""
    client, _ = _make_client(auth_token="secret-token")
    resp = client.post(
        "/api/command",
        json={"content": "test"},
        headers={"Authorization": "Bearer secret-token"},
    )
    assert resp.status_code == 202
