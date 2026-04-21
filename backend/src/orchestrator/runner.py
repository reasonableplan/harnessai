"""Agent runner — delegate to providers with timeout, retry, and escalation."""

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
    """Result of a single agent execution."""

    agent: str
    output: str
    success: bool
    duration_ms: int
    attempts: int
    error: str | None = None
    escalated: bool = False


def _create_provider(config: AgentConfig) -> BaseProvider:
    """Instantiate the provider matching the agent config."""
    if config.provider == Provider.CLAUDE_CLI:
        return ClaudeCliProvider()
    if config.provider == Provider.GEMINI:
        return GeminiApiProvider()
    if config.provider == Provider.GEMINI_CLI:
        return GeminiCliProvider()
    raise NotImplementedError(f"provider '{config.provider}' is not supported yet.")


@dataclass
class AgentRunner:
    """Core agent execution engine.

    Delegates to the provider, enforces timeout / retry / escalation policies,
    limits concurrency via a semaphore, and injects skeleton context.
    """

    config: OrchestratorConfig
    project_dir: Path = field(default_factory=lambda: Path("."))
    logger: AgentLogger = field(default_factory=AgentLogger)

    def __post_init__(self) -> None:
        self.project_dir = Path(self.project_dir).resolve()
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent)
        self._providers: dict[str, BaseProvider] = {}

    def _get_provider(self, agent: str) -> BaseProvider:
        """Return a cached provider for the given agent."""
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
        """Run a single agent and return its result.

        The semaphore limits concurrency, skeleton context is auto-injected,
        and on timeout the ``on_timeout`` policy (retry / escalate / log_only)
        is applied.
        """
        async with self._semaphore:
            return await self._run_with_retry(agent, prompt, working_dir=working_dir)

    async def run_many(
        self,
        tasks: list[tuple[str, str]],
        *,
        working_dir: str | Path | None = None,
    ) -> list[RunResult]:
        """Run multiple agents in parallel under the concurrency semaphore.

        Args:
            tasks: list of ``(agent_name, prompt)`` tuples.
        """
        coros = [self.run(agent, prompt, working_dir=working_dir) for agent, prompt in tasks]
        results = await asyncio.gather(*coros, return_exceptions=True)
        # Convert exceptions to RunResult so one agent's failure doesn't affect others.
        # Only `Exception` is caught — `CancelledError` / `KeyboardInterrupt` /
        # `SystemExit` inherit directly from `BaseException` and are re-raised so
        # cancellation/shutdown propagates to the caller.
        converted: list[RunResult] = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                agent_name = tasks[i][0]
                converted.append(
                    RunResult(
                        agent=agent_name,
                        output="",
                        success=False,
                        duration_ms=0,
                        attempts=0,
                        error=str(r),
                    )
                )
            elif isinstance(r, BaseException):
                raise r  # Never swallow CancelledError and friends
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
        """Execute with retry logic according to the agent's on_timeout policy."""
        agent_config = self.config.get_agent(agent)
        provider = self._get_provider(agent)
        work_dir = Path(working_dir) if working_dir else self.project_dir

        # Assemble the system prompt context
        prompt_path = self.project_dir / agent_config.prompt_path
        skeleton_path = self.project_dir / "docs" / "skeleton.md"
        docs_dir = self.project_dir / "docs"

        system_prompt: str | None = None
        if prompt_path.exists() or skeleton_path.exists():
            system_prompt = (
                build_context(
                    agent=agent,
                    skeleton_path=skeleton_path,
                    docs_dir=docs_dir,
                    prompt_path=prompt_path if prompt_path.exists() else None,
                    project_root=self.project_dir,
                )
                or None
            )

        max_attempts = 1 + (
            agent_config.max_retries_on_timeout if agent_config.on_timeout == OnTimeout.RETRY else 0
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
                    agent=agent,
                    prompt=prompt,
                    status="success",
                    duration_ms=duration_ms,
                )
                return RunResult(
                    agent=agent,
                    output=output,
                    success=True,
                    duration_ms=duration_ms,
                    attempts=attempt,
                )

            except TimeoutError:
                duration_ms = int((time.monotonic() - start) * 1000)
                self.logger.log_run(
                    agent=agent,
                    prompt=prompt,
                    status="timeout",
                    duration_ms=duration_ms,
                    error=f"timeout ({agent_config.timeout_seconds}s)",
                )
                if attempt < max_attempts:
                    continue

                return self._handle_final_timeout(
                    agent,
                    agent_config,
                    duration_ms,
                    attempt,
                )

            except Exception as e:
                duration_ms = int((time.monotonic() - start) * 1000)
                self.logger.log_run(
                    agent=agent,
                    prompt=prompt,
                    status="error",
                    duration_ms=duration_ms,
                    error=str(e),
                )
                return RunResult(
                    agent=agent,
                    output="",
                    success=False,
                    duration_ms=duration_ms,
                    attempts=attempt,
                    error=str(e),
                )

        raise RuntimeError("unexpected loop termination")  # unreachable

    def _handle_final_timeout(
        self,
        agent: str,
        config: AgentConfig,
        duration_ms: int,
        attempts: int,
    ) -> RunResult:
        """Handle final timeout according to the agent's on_timeout policy."""
        if config.on_timeout == OnTimeout.ESCALATE:
            self.logger.log_escalation(
                agent=agent,
                reason=f"timeout x{attempts} — max retries exceeded",
                escalated_to="PM",
            )
            return RunResult(
                agent=agent,
                output="",
                success=False,
                duration_ms=duration_ms,
                attempts=attempts,
                error="timeout -> escalated to PM",
                escalated=True,
            )

        # log_only
        return RunResult(
            agent=agent,
            output="",
            success=False,
            duration_ms=duration_ms,
            attempts=attempts,
            error=f"timeout ({config.timeout_seconds}s) — logged only",
        )
