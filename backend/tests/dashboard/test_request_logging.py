"""RequestLoggingMiddleware 테스트."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

from src.dashboard.routes.deps import get_state_store
from src.dashboard.server import create_app


def _make_mock_store():
    store = MagicMock()
    store.check_db_connection = AsyncMock(return_value=True)
    agent = MagicMock()
    agent.id = "director"
    agent.status = "idle"
    store.get_all_agents = AsyncMock(return_value=[agent])
    return store


def _make_mock_ctx():
    mock_git = MagicMock()
    mock_git.check_rate_limit = AsyncMock(return_value=4999)
    ctx = MagicMock()
    ctx.git_service = mock_git
    return ctx


class TestRequestLoggingMiddleware:
    async def test_response_contains_x_request_id(self):
        """모든 응답에 X-Request-ID 헤더가 포함된다."""
        app = create_app(auth_token=None)
        mock_store = _make_mock_store()
        mock_ctx = _make_mock_ctx()
        app.dependency_overrides[get_state_store] = lambda: mock_store

        with patch("src.dashboard.routes.health.get_system_context", return_value=mock_ctx):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/health")

        assert resp.status_code == 200
        request_id = resp.headers.get("X-Request-ID")
        assert request_id is not None
        assert len(request_id) == 36  # UUID4 형식

    async def test_request_id_is_unique_per_request(self):
        """각 요청마다 고유한 request_id가 생성된다."""
        app = create_app(auth_token=None)
        mock_store = _make_mock_store()
        mock_ctx = _make_mock_ctx()
        app.dependency_overrides[get_state_store] = lambda: mock_store

        with patch("src.dashboard.routes.health.get_system_context", return_value=mock_ctx):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp1 = await client.get("/health")
                resp2 = await client.get("/health")

        id1 = resp1.headers.get("X-Request-ID")
        id2 = resp2.headers.get("X-Request-ID")
        assert id1 != id2

    async def test_logs_request_completion(self):
        """요청 완료 시 method, path, status, duration_ms가 로깅된다."""
        app = create_app(auth_token=None)
        mock_store = _make_mock_store()
        mock_ctx = _make_mock_ctx()
        app.dependency_overrides[get_state_store] = lambda: mock_store

        with (
            patch("src.dashboard.routes.health.get_system_context", return_value=mock_ctx),
            patch("src.dashboard.server._request_log") as mock_log,
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.get("/health")

        mock_log.info.assert_called_once()
        call_kwargs = mock_log.info.call_args
        # positional arg: log message
        assert call_kwargs[0][0] == "Request completed"
        # keyword args: method, path, status, duration_ms
        assert call_kwargs[1]["method"] == "GET"
        assert call_kwargs[1]["path"] == "/health"
        assert call_kwargs[1]["status"] == 200
        assert "duration_ms" in call_kwargs[1]
        assert isinstance(call_kwargs[1]["duration_ms"], float)

    async def test_contextvars_bound_during_request(self):
        """요청 처리 중 structlog contextvars에 request_id가 바인딩된다."""
        captured_request_id = {}

        app = create_app(auth_token=None)
        mock_store = _make_mock_store()
        mock_ctx = _make_mock_ctx()
        app.dependency_overrides[get_state_store] = lambda: mock_store

        import structlog

        original_bind = structlog.contextvars.bind_contextvars

        def spy_bind(**kwargs):
            if "request_id" in kwargs:
                captured_request_id["value"] = kwargs["request_id"]
            return original_bind(**kwargs)

        with (
            patch("src.dashboard.routes.health.get_system_context", return_value=mock_ctx),
            patch("src.dashboard.server.structlog.contextvars.bind_contextvars", side_effect=spy_bind),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/health")

        assert "value" in captured_request_id
        assert captured_request_id["value"] == resp.headers["X-Request-ID"]
