"""GET /health 엔드포인트 테스트."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

from src.dashboard.routes.deps import get_state_store
from src.dashboard.server import create_app


def _make_mock_store(db_ok=True):
    store = MagicMock()
    if db_ok:
        store.check_db_connection = AsyncMock(return_value=True)
    else:
        store.check_db_connection = AsyncMock(side_effect=RuntimeError("connection refused"))

    agent = MagicMock()
    agent.id = "director"
    agent.status = "idle"
    store.get_all_agents = AsyncMock(return_value=[agent])
    return store


def _make_mock_ctx(git_ok=True):
    mock_git = MagicMock()
    if git_ok:
        mock_git.check_rate_limit = AsyncMock(return_value=4999)
    else:
        mock_git.check_rate_limit = AsyncMock(side_effect=RuntimeError("GitHub down"))
    ctx = MagicMock()
    ctx.git_service = mock_git
    return ctx


class TestHealthEndpoint:
    async def test_health_returns_200_when_all_ok(self):
        """DB, GitHub, agents 모두 정상이면 200 + status=ok."""
        app = create_app(auth_token=None)
        mock_store = _make_mock_store(db_ok=True)
        mock_ctx = _make_mock_ctx(git_ok=True)
        app.dependency_overrides[get_state_store] = lambda: mock_store

        with patch("src.dashboard.routes.health.get_system_context", return_value=mock_ctx):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["checks"]["database"]["status"] == "ok"
        assert data["checks"]["github"]["status"] == "ok"
        assert data["checks"]["agents"]["status"] == "ok"
        assert data["checks"]["agents"]["count"] == 1

    async def test_health_returns_503_when_db_down(self):
        """DB 실패 시 503 + status=degraded."""
        app = create_app(auth_token=None)
        mock_store = _make_mock_store(db_ok=False)
        mock_ctx = _make_mock_ctx(git_ok=True)
        app.dependency_overrides[get_state_store] = lambda: mock_store

        with patch("src.dashboard.routes.health.get_system_context", return_value=mock_ctx):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/health")

        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["checks"]["database"]["status"] == "error"

    async def test_health_returns_503_when_github_down(self):
        """GitHub 실패 시 503 + status=degraded."""
        app = create_app(auth_token=None)
        mock_store = _make_mock_store(db_ok=True)
        mock_ctx = _make_mock_ctx(git_ok=False)
        app.dependency_overrides[get_state_store] = lambda: mock_store

        with patch("src.dashboard.routes.health.get_system_context", return_value=mock_ctx):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/health")

        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["checks"]["github"]["status"] == "error"

    async def test_health_no_auth_required(self):
        """인증 토큰이 설정되어도 /health는 인증 없이 접근 가능."""
        app = create_app(auth_token="secret-token")
        mock_store = _make_mock_store(db_ok=True)
        mock_ctx = _make_mock_ctx(git_ok=True)
        app.dependency_overrides[get_state_store] = lambda: mock_store

        with patch("src.dashboard.routes.health.get_system_context", return_value=mock_ctx):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/health")

        assert resp.status_code != 401
        assert resp.status_code != 403
