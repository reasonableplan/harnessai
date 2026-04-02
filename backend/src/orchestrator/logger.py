"""에이전트 행동 로깅 — JSON 구조화 로그."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class AgentLogger:
    """에이전트별 JSON 로그 기록기."""

    def __init__(self, log_dir: str | Path = "logs/agents") -> None:
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)

    def _get_log_path(self, agent: str) -> Path:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        return self._log_dir / f"{today}_{agent}.log"

    def log(
        self,
        agent: str,
        action: str,
        status: str,
        *,
        target: str | None = None,
        duration_ms: int | None = None,
        token_usage: dict[str, int] | None = None,
        error: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """에이전트 행동을 JSON 한 줄로 기록."""
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "agent": agent,
            "action": action,
            "status": status,
            "target": target,
            "duration_ms": duration_ms,
            "token_usage": token_usage,
            "error": error,
        }
        if extra:
            entry["extra"] = extra

        log_path = self._get_log_path(agent)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def log_run(
        self,
        agent: str,
        prompt: str,
        status: str,
        *,
        duration_ms: int | None = None,
        token_usage: dict[str, int] | None = None,
        error: str | None = None,
    ) -> None:
        """에이전트 실행(run) 로그 편의 메서드."""
        self.log(
            agent=agent,
            action="run",
            status=status,
            target=prompt[:100],  # 프롬프트 앞 100자만
            duration_ms=duration_ms,
            token_usage=token_usage,
            error=error,
        )

    def log_escalation(
        self,
        agent: str,
        reason: str,
        escalated_to: str,
    ) -> None:
        """에스컬레이션 로그."""
        self.log(
            agent=agent,
            action="escalation",
            status="escalated",
            extra={"reason": reason, "escalated_to": escalated_to},
        )
