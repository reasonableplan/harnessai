"""agents.yaml 로더 테스트."""

from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest
import yaml

from src.orchestrator.config import (
    AgentConfig,
    OnTimeout,
    OrchestratorConfig,
    Provider,
    load_agents_config,
)


def _make_valid_yaml() -> dict:
    """유효한 agents.yaml 데이터."""
    agent = {
        "provider": "claude-cli",
        "model": "opus",
        "prompt_path": "agents/test/CLAUDE.md",
        "timeout_seconds": 300,
        "on_timeout": "escalate",
        "max_retries_on_timeout": 0,
        "max_tokens": 8192,
    }
    return {
        "architect": agent,
        "designer": agent,
        "orchestrator": agent,
        "backend_coder": agent,
        "frontend_coder": agent,
        "reviewer": agent,
        "qa": agent,
    }


class TestAgentConfig:
    def test_valid_config(self) -> None:
        cfg = AgentConfig(
            provider="claude-cli",
            model="opus",
            prompt_path="agents/architect/CLAUDE.md",
        )
        assert cfg.provider == Provider.CLAUDE_CLI
        assert cfg.timeout_seconds == 300
        assert cfg.on_timeout == OnTimeout.ESCALATE

    def test_local_provider_requires_api_base(self) -> None:
        with pytest.raises(ValueError, match="api_base"):
            AgentConfig(
                provider="local",
                model="qwen-2.5",
                prompt_path="agents/test/CLAUDE.md",
            )

    def test_local_provider_with_api_base(self) -> None:
        cfg = AgentConfig(
            provider="local",
            model="qwen-2.5",
            prompt_path="agents/test/CLAUDE.md",
            api_base="http://localhost:11434/v1",
        )
        assert cfg.provider == Provider.LOCAL
        assert cfg.api_base == "http://localhost:11434/v1"

    def test_retry_count_reset_when_not_retry_policy(self) -> None:
        cfg = AgentConfig(
            provider="claude-cli",
            model="opus",
            prompt_path="agents/test/CLAUDE.md",
            on_timeout="escalate",
            max_retries_on_timeout=3,
        )
        assert cfg.max_retries_on_timeout == 0

    def test_retry_count_kept_when_retry_policy(self) -> None:
        cfg = AgentConfig(
            provider="claude-cli",
            model="opus",
            prompt_path="agents/test/CLAUDE.md",
            on_timeout="retry",
            max_retries_on_timeout=3,
        )
        assert cfg.max_retries_on_timeout == 3


class TestOrchestratorConfig:
    def test_get_agent(self) -> None:
        data = _make_valid_yaml()
        cfg = OrchestratorConfig(**data)
        architect = cfg.get_agent("architect")
        assert architect.model == "opus"

    def test_get_agent_unknown(self) -> None:
        data = _make_valid_yaml()
        cfg = OrchestratorConfig(**data)
        with pytest.raises(ValueError, match="알 수 없는 에이전트"):
            cfg.get_agent("unknown_agent")

    def test_all_agents(self) -> None:
        data = _make_valid_yaml()
        cfg = OrchestratorConfig(**data)
        agents = cfg.all_agents()
        assert len(agents) == 7
        assert "architect" in agents
        assert "qa" in agents


class TestLoadAgentsConfig:
    def test_load_valid_yaml(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "agents.yaml"
        yaml_path.write_text(yaml.dump(_make_valid_yaml()), encoding="utf-8")

        cfg = load_agents_config(yaml_path)
        assert isinstance(cfg, OrchestratorConfig)
        assert cfg.architect.provider == Provider.CLAUDE_CLI

    def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_agents_config("/nonexistent/agents.yaml")

    def test_invalid_yaml_format(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "agents.yaml"
        yaml_path.write_text("just a string", encoding="utf-8")

        with pytest.raises(ValueError, match="dict 예상"):
            load_agents_config(yaml_path)

    def test_load_real_agents_yaml(self) -> None:
        """실제 agents.yaml 파일 로딩 테스트."""
        real_path = Path(__file__).parent.parent.parent / "agents.yaml"
        if not real_path.exists():
            pytest.skip("agents.yaml 없음")

        cfg = load_agents_config(real_path)
        assert cfg.architect.model == "claude-opus-4-6"
        assert cfg.backend_coder.model == "claude-sonnet-4-6"
        assert cfg.orchestrator.on_timeout == OnTimeout.RETRY
