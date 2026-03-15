"""Bearer token 인증 미들웨어."""
from __future__ import annotations

import hmac

from fastapi import HTTPException, Request, status


def make_auth_checker(token: str | None):
    """token이 None이면 dev 모드 (인증 스킵)."""

    async def check_auth(request: Request) -> None:
        if not token:
            return  # dev 모드
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
        provided = auth_header[len("Bearer "):]
        # timing-safe compare
        if not hmac.compare_digest(provided.encode(), token.encode()):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    return check_auth
