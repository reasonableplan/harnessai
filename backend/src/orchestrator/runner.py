"""에이전트 실행기 — provider에 위임, 타임아웃/재시도/에스컬레이션 관리."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path

from src.orchestrator.config import AgentConfig, OnTimeout, OrchestratorConfig, Provider
from src.orchestrator.context import build_context
from src.orchestrator.logger import AgentLogger
from src.orchestrator.providers.base import BaseProvider
from src.orchestrator.providers.claude_cli import ClaudeCliProvider
from src.orchestrator.providers.gemini_api import GeminiApiProvider
from src.orchestrator.providers.gemini_cli import GeminiCliProvider


@dataclass
class RunResult:
    """에이전트 실행 결과."""

    agent: str
    output: str
    success: bool
    duration_ms: int
    attempts: int
    error: str | None = None
    escalated: bool = False


def _create_provider(config: AgentConfig) -> BaseProvider:
    """에이전트 설정에 맞는 provider 인스턴스를 생성."""
    if config.provider == Provider.CLAUDE_CLI:
        return ClaudeCliProvider()
    if config.provider == Provider.GEMINI:
        return GeminiApiProvider()
    if config.provider == Provider.GEMINI_CLI:
        return GeminiCliProvider()
    raise NotImplementedError(f"provider '{config.provider}'는 아직 지원하지 않습니다.")


@dataclass
class AgentRunner:
    """에이전트를 실행하는 핵심 엔진.

    - provider에 실행을 위임
    - 타임아웃/재시도/에스컬레이션 정책 처리
    - 동시 실행 세마포어로 병렬 제어
    - skeleton 컨텍스트 자동 주입
    """

    config: OrchestratorConfig
    project_dir: str | Path = "."
    logger: AgentLogger = field(default_factory=AgentLogger)
    def __post_init__(self) -> None:
        self.project_dir = Path(self.project_dir).resolve()
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent)
        self._providers: dict[str, BaseProvider] = {}

    def _get_provider(self, agent: str) -> BaseProvider:
        """에이전트별 provider를 캐싱해서 반환."""
        if agent not in self._providers:
            agent_config = self.config.get_agent(agent)
            self._providers[agent] = _create_provider(agent_config)
        return self._providers[agent]

    async def run(
        self,
        agent: str,
        prompt: str,
        *,
        working_dir: str | Path | None = None,
    ) -> RunResult:
        """에이전트를 실행하고 결과를 반환한다.

        - 세마포어로 동시 실행 수 제한
        - skeleton 컨텍스트 자동 주입
        - 타임아웃 시 on_timeout 정책에 따라 retry/escalate/log_only
        """
        async with self._semaphore:
            return await self._run_with_retry(agent, prompt, working_dir=working_dir)

    async def run_many(
        self,
        tasks: list[tuple[str, str]],
        *,
        working_dir: str | Path | None = None,
    ) -> list[RunResult]:
        """여러 에이전트를 병렬 실행. 세마포어로 동시 실행 수 제한.

        Args:
            tasks: [(에이전트명, 프롬프트), ...] 리스트
        """
        coros = [
            self.run(agent, prompt, working_dir=working_dir)
            for agent, prompt in tasks
        ]
        results = await asyncio.gather(*coros, return_exceptions=True)
        # 예외를 RunResult로 변환 — 한 에이전트 실패가 나머지에 영향 없음
        converted: list[RunResult] = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                agent_name = tasks[i][0]
                converted.append(RunResult(
                    agent=agent_name, output="", success=False,
                    duration_ms=0, attempts=0, error=str(r),
                ))
            else:
                converted.append(r)
        return converted

    async def _run_with_retry(
        self,
        agent: str,
        prompt: str,
        *,
        working_dir: str | Path | None = None,
    ) -> RunResult:
        """재시도 로직을 포함한 실행."""
        agent_config = self.config.get_agent(agent)
        provider = self._get_provider(agent)
        work_dir = Path(working_dir) if working_dir else self.project_dir

        # 컨텍스트 조합
        prompt_path = self.project_dir / agent_config.prompt_path
        skeleton_path = self.project_dir / "docs" / "skeleton.md"
        docs_dir = self.project_dir / "docs"

        system_prompt: str | None = None
        if prompt_path.exists() or skeleton_path.exists():
            system_prompt = build_context(
                agent=agent,
                skeleton_path=skeleton_path,
                docs_dir=docs_dir,
                prompt_path=prompt_path if prompt_path.exists() else None,
            ) or None

        max_attempts = 1 + (
            agent_config.max_retries_on_timeout
            if agent_config.on_timeout == OnTimeout.RETRY
            else 0
        )
        attempt = 0

        while attempt < max_attempts:
            attempt += 1
            start = time.monotonic()

            try:
                output = await provider.execute(
                    agent_name=agent,
                    config=agent_config,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    working_dir=work_dir,
                )
                duration_ms = int((time.monotonic() - start) * 1000)

                self.logger.log_run(
                    agent=agent, prompt=prompt, status="success", duration_ms=duration_ms,
                )
                return RunResult(
                    agent=agent, output=output, success=True,
                    duration_ms=duration_ms, attempts=attempt,
                )

            except TimeoutError:
                duration_ms = int((time.monotonic() - start) * 1000)
                self.logger.log_run(
                    agent=agent, prompt=prompt, status="timeout",
                    duration_ms=duration_ms,
                    error=f"타임아웃 ({agent_config.timeout_seconds}초)",
                )
                if attempt < max_attempts:
                    continue

                return self._handle_final_timeout(
                    agent, agent_config, duration_ms, attempt,
                )

            except Exception as e:
                duration_ms = int((time.monotonic() - start) * 1000)
                self.logger.log_run(
                    agent=agent, prompt=prompt, status="error",
                    duration_ms=duration_ms, error=str(e),
                )
                return RunResult(
                    agent=agent, output="", success=False,
                    duration_ms=duration_ms, attempts=attempt, error=str(e),
                )

        raise RuntimeError("예상치 못한 루프 종료")  # unreachable

    def _handle_final_timeout(
        self,
        agent: str,
        config: AgentConfig,
        duration_ms: int,
        attempts: int,
    ) -> RunResult:
        """최종 타임아웃 시 on_timeout 정책 처리."""
        if config.on_timeout == OnTimeout.ESCALATE:
            self.logger.log_escalation(
                agent=agent,
                reason=f"타임아웃 {attempts}회 — 최대 재시도 초과",
                escalated_to="PM",
            )
            return RunResult(
                agent=agent, output="", success=False,
                duration_ms=duration_ms, attempts=attempts,
                error="타임아웃 → PM에 에스컬레이션", escalated=True,
            )

        # log_only
        return RunResult(
            agent=agent, output="", success=False,
            duration_ms=duration_ms, attempts=attempts,
            error=f"타임아웃 ({config.timeout_seconds}초) — 로그만 기록",
        )
