"""Provider 추상 인터페이스 — 에이전트 실행 방식을 교체 가능하게."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from src.orchestrator.config import AgentConfig


class BaseProvider(ABC):
    """모든 provider가 구현해야 하는 인터페이스."""

    @abstractmethod
    async def execute(
        self,
        agent_name: str,
        config: AgentConfig,
        prompt: str,
        *,
        system_prompt: str | None = None,
        working_dir: Path | None = None,
    ) -> str:
        """에이전트를 실행하고 결과 텍스트를 반환.

        Args:
            agent_name: 에이전트 이름
            config: 에이전트 설정
            prompt: 사용자 프롬프트
            system_prompt: 시스템 프롬프트 (CLAUDE.md 내용 등)
            working_dir: 작업 디렉토리

        Returns:
            에이전트 출력 텍스트

        Raises:
            TimeoutError: 타임아웃 초과
            RuntimeError: 실행 실패
        """
