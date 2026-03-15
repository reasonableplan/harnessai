"""WebSocket 첫 메시지 기반 인증 테스트."""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from src.dashboard.server import create_app


@pytest.fixture()
def auth_app():
    return create_app(auth_token="secret")


@pytest.fixture()
def no_auth_app():
    return create_app(auth_token=None)


class TestWebSocketAuth:
    def test_no_auth_required_connects_immediately(self, no_auth_app):
        """auth_token=None 이면 인증 메시지 없이 바로 연결된다."""
        with TestClient(no_auth_app).websocket_connect("/ws") as ws:
            ws.send_text("ping")
            data = json.loads(ws.receive_text())
            assert data["type"] == "pong"

    def test_valid_token_receives_auth_ok(self, auth_app):
        """올바른 토큰을 보내면 auth.ok를 수신한다."""
        with TestClient(auth_app).websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"type": "auth", "token": "secret"}))
            data = json.loads(ws.receive_text())
            assert data["type"] == "auth.ok"

    def test_valid_token_can_ping(self, auth_app):
        """인증 후 ping/pong이 정상 동작한다."""
        with TestClient(auth_app).websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"type": "auth", "token": "secret"}))
            ws.receive_text()  # auth.ok
            ws.send_text("ping")
            data = json.loads(ws.receive_text())
            assert data["type"] == "pong"

    def test_wrong_token_closes_with_4001(self, auth_app):
        """잘못된 토큰은 4001로 연결을 종료한다."""
        with pytest.raises(Exception):
            with TestClient(auth_app).websocket_connect("/ws") as ws:
                ws.send_text(json.dumps({"type": "auth", "token": "wrong"}))
                ws.receive_text()  # 4001 close → exception

    def test_invalid_json_closes_with_4001(self, auth_app):
        """JSON이 아닌 첫 메시지는 4001로 종료한다."""
        with pytest.raises(Exception):
            with TestClient(auth_app).websocket_connect("/ws") as ws:
                ws.send_text("not-json")
                ws.receive_text()

    def test_wrong_message_type_closes_with_4001(self, auth_app):
        """type이 auth가 아닌 첫 메시지는 4001로 종료한다."""
        with pytest.raises(Exception):
            with TestClient(auth_app).websocket_connect("/ws") as ws:
                ws.send_text(json.dumps({"type": "ping"}))
                ws.receive_text()

    def test_token_not_in_url(self, auth_app):
        """쿼리 파라미터로 토큰을 전달해도 인증되지 않는다 (메시지 기반만 허용)."""
        with pytest.raises(Exception):
            with TestClient(auth_app).websocket_connect("/ws?token=secret") as ws:
                ws.receive_text()  # 첫 메시지가 없으므로 timeout → 4001
