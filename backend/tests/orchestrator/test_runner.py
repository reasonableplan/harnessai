"""CLI subprocess 실행기 테스트."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.orchestrator.config import AgentConfig, OnTimeout, OrchestratorConfig
from src.orchestrator.logger import AgentLogger
from src.orchestrator.runner import AgentRunner, RunResult


def _make_config(**overrides: object) -> OrchestratorConfig:
    """테스트용 OrchestratorConfig 생성."""
    base = {
        "provider": "claude-cli",
        "model": "opus",
        "prompt_path": "agents/test/CLAUDE.md",
        "timeout_seconds": 10,
        "on_timeout": "escalate",
        "max_retries_on_timeout": 0,
        "max_tokens": 4096,
    }
    agent = {**base, **overrides}
    return OrchestratorConfig(
        architect=AgentConfig(**agent),
        designer=AgentConfig(**agent),
        orchestrator=AgentConfig(**agent),
        backend_coder=AgentConfig(**agent),
        frontend_coder=AgentConfig(**agent),
        reviewer=AgentConfig(**agent),
        qa=AgentConfig(**agent),
    )


class TestRun:
    async def test_successful_run(self, tmp_path: Path) -> None:
        config = _make_config()
        runner = AgentRunner(config=config, project_dir=tmp_path, logger=AgentLogger(tmp_path / "logs"))

        with patch.object(runner, "_run_with_retry") as mock_run:
            mock_run.return_value = RunResult(
                agent="architect", output="result", success=True,
                duration_ms=100, attempts=1,
            )
            result = await runner.run("architect", "설계해줘")

        assert result.success is True
        assert result.output == "result"

    async def test_timeout_escalate(self, tmp_path: Path) -> None:
        config = _make_config(timeout_seconds=1, on_timeout="escalate", max_retries_on_timeout=0)
        runner = AgentRunner(config=config, project_dir=tmp_path, logger=AgentLogger(tmp_path / "logs"))

        # provider.execute가 TimeoutError를 raise
        mock_provider = AsyncMock()
        mock_provider.execute = AsyncMock(side_effect=TimeoutError("타임아웃"))
        runner._providers["architect"] = mock_provider

        result = await runner.run("architect", "설계해줘")

        assert result.success is False
        assert result.escalated is True
        assert result.attempts == 1

    async def test_timeout_retry(self, tmp_path: Path) -> None:
        config = _make_config(timeout_seconds=1, on_timeout="retry", max_retries_on_timeout=2)
        runner = AgentRunner(config=config, project_dir=tmp_path, logger=AgentLogger(tmp_path / "logs"))

        mock_provider = AsyncMock()
        mock_provider.execute = AsyncMock(side_effect=TimeoutError("타임아웃"))
        runner._providers["architect"] = mock_provider

        result = await runner.run("architect", "설계해줘")

        assert result.success is False
        assert result.attempts == 3  # 1 + 2 retries

    async def test_timeout_retry_succeeds_on_second(self, tmp_path: Path) -> None:
        config = _make_config(timeout_seconds=1, on_timeout="retry", max_retries_on_timeout=2)
        runner = AgentRunner(config=config, project_dir=tmp_path, logger=AgentLogger(tmp_path / "logs"))

        mock_provider = AsyncMock()
        mock_provider.execute = AsyncMock(side_effect=[TimeoutError("타임아웃"), "success"])
        runner._providers["architect"] = mock_provider

        result = await runner.run("architect", "설계해줘")

        assert result.success is True
        assert result.output == "success"
        assert result.attempts == 2

    async def test_cli_error(self, tmp_path: Path) -> None:
        config = _make_config()
        runner = AgentRunner(config=config, project_dir=tmp_path, logger=AgentLogger(tmp_path / "logs"))

        mock_provider = AsyncMock()
        mock_provider.execute = AsyncMock(side_effect=RuntimeError("CLI 실패"))
        runner._providers["architect"] = mock_provider

        result = await runner.run("architect", "설계해줘")

        assert result.success is False
        assert "CLI 실패" in result.error

    async def test_semaphore_limits_concurrency(self, tmp_path: Path) -> None:
        config = _make_config()
        runner = AgentRunner(
            config=config, project_dir=tmp_path,
            logger=AgentLogger(tmp_path / "logs"), max_concurrent=1,
        )

        call_count = 0
        max_concurrent_seen = 0

        async def slow_execute(**kwargs: object) -> str:
            nonlocal call_count, max_concurrent_seen
            call_count += 1
            current = call_count
            if current > max_concurrent_seen:
                max_concurrent_seen = current
            await asyncio.sleep(0.05)
            call_count -= 1
            return "done"

        mock_provider = AsyncMock()
        mock_provider.execute = slow_execute
        runner._providers["architect"] = mock_provider
        runner._providers["designer"] = mock_provider

        results = await runner.run_many([
            ("architect", "작업1"),
            ("designer", "작업2"),
        ])

        assert len(results) == 2
        assert all(r.success for r in results)
        # max_concurrent=1이므로 동시에 1개만 실행
        assert max_concurrent_seen <= 1


class TestRunMany:
    async def test_parallel_execution(self, tmp_path: Path) -> None:
        config = _make_config()
        runner = AgentRunner(
            config=config, project_dir=tmp_path,
            logger=AgentLogger(tmp_path / "logs"), max_concurrent=2,
        )

        mock_provider = AsyncMock()
        mock_provider.execute = AsyncMock(return_value="done")
        runner._providers["architect"] = mock_provider
        runner._providers["designer"] = mock_provider

        results = await runner.run_many([
            ("architect", "작업1"),
            ("designer", "작업2"),
        ])

        assert len(results) == 2
        assert all(r.success for r in results)


    async def test_partial_failure(self, tmp_path: Path) -> None:
        """한 에이전트 실패해도 나머지 결과가 살아있는지 확인."""
        config = _make_config()
        runner = AgentRunner(
            config=config, project_dir=tmp_path,
            logger=AgentLogger(tmp_path / "logs"), max_concurrent=2,
        )

        ok_provider = AsyncMock()
        ok_provider.execute = AsyncMock(return_value="success")

        fail_provider = AsyncMock()
        fail_provider.execute = AsyncMock(side_effect=RuntimeError("폭발"))

        runner._providers["architect"] = ok_provider
        runner._providers["designer"] = fail_provider

        results = await runner.run_many([
            ("architect", "작업1"),
            ("designer", "작업2"),
        ])

        assert len(results) == 2
        # architect 성공
        assert results[0].success is True
        assert results[0].output == "success"
        # designer 실패 — 하지만 결과 객체는 존재
        assert results[1].success is False
        assert "폭발" in results[1].error

    async def test_all_failure(self, tmp_path: Path) -> None:
        """모든 에이전트 실패 시 전부 RunResult로 반환."""
        config = _make_config()
        runner = AgentRunner(
            config=config, project_dir=tmp_path,
            logger=AgentLogger(tmp_path / "logs"), max_concurrent=2,
        )

        fail_provider = AsyncMock()
        fail_provider.execute = AsyncMock(side_effect=RuntimeError("에러"))

        runner._providers["architect"] = fail_provider
        runner._providers["designer"] = fail_provider

        results = await runner.run_many([
            ("architect", "작업1"),
            ("designer", "작업2"),
        ])

        assert len(results) == 2
        assert all(not r.success for r in results)


class TestContextInjection:
    async def test_system_prompt_passed_to_provider(self, tmp_path: Path) -> None:
        """runner가 build_context 결과를 provider에 전달하는지 확인."""
        prompt_dir = tmp_path / "agents" / "test"
        prompt_dir.mkdir(parents=True)
        (prompt_dir / "CLAUDE.md").write_text("You are an architect.", encoding="utf-8")

        config = _make_config()
        runner = AgentRunner(config=config, project_dir=tmp_path, logger=AgentLogger(tmp_path / "logs"))

        mock_provider = AsyncMock()
        mock_provider.execute = AsyncMock(return_value="done")
        runner._providers["architect"] = mock_provider

        await runner.run("architect", "설계해줘")

        # provider.execute에 system_prompt가 전달되었는지 확인
        call_kwargs = mock_provider.execute.call_args
        assert call_kwargs.kwargs["system_prompt"] is not None
        assert "You are an architect." in call_kwargs.kwargs["system_prompt"]

    async def test_no_context_files_passes_none(self, tmp_path: Path) -> None:
        """컨텍스트 파일이 없으면 system_prompt=None 전달."""
        config = _make_config()
        runner = AgentRunner(config=config, project_dir=tmp_path, logger=AgentLogger(tmp_path / "logs"))

        mock_provider = AsyncMock()
        mock_provider.execute = AsyncMock(return_value="done")
        runner._providers["architect"] = mock_provider

        await runner.run("architect", "설계해줘")

        call_kwargs = mock_provider.execute.call_args
        assert call_kwargs.kwargs["system_prompt"] is None
