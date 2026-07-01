"""agents.yaml 로더 테스트."""

from pathlib import Path

import pytest
import yaml

from src.orchestrator.config import (
    AgentConfig,
    OnTimeout,
    OrchestratorConfig,
    Provider,
    _resolve_model_tiers,
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
        "mobile_coder_rn": agent,
        "mobile_coder_flutter": agent,
        "mobile_coder_android": agent,
        "mobile_coder_ios": agent,
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
        with pytest.raises(ValueError, match="unknown agent"):
            cfg.get_agent("unknown_agent")

    def test_all_agents(self) -> None:
        data = _make_valid_yaml()
        cfg = OrchestratorConfig(**data)
        agents = cfg.all_agents()
        assert len(agents) == 11
        assert "architect" in agents
        assert "mobile_coder_rn" in agents
        assert "mobile_coder_flutter" in agents
        assert "mobile_coder_android" in agents
        assert "mobile_coder_ios" in agents
        assert "qa" in agents

    @pytest.mark.parametrize(
        "agent_name",
        ["mobile_coder_rn", "mobile_coder_flutter", "mobile_coder_android", "mobile_coder_ios"],
    )
    def test_mobile_coder_loadable(self, agent_name: str) -> None:
        """4개 mobile_coder 모두 OrchestratorConfig 정식 필드.

        get_agent(name) 가 ValueError 없이 AgentConfig 반환해야 Orchestrator
        가 task.agent=<mobile_coder_*> 로 dispatch 가능.
        """
        data = _make_valid_yaml()
        cfg = OrchestratorConfig(**data)
        agent_cfg = cfg.get_agent(agent_name)
        assert isinstance(agent_cfg, AgentConfig)
        assert agent_cfg.provider == Provider.CLAUDE_CLI


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

        with pytest.raises(ValueError, match="expected dict"):
            load_agents_config(yaml_path)

    def test_load_real_agents_yaml(self) -> None:
        """실제 agents.yaml 파일 로딩 테스트."""
        real_path = Path(__file__).parent.parent.parent / "agents.yaml"
        if not real_path.exists():
            pytest.skip("agents.yaml 없음")

        cfg = load_agents_config(real_path)
        assert cfg.architect.model == "claude-opus-4-8"
        assert cfg.backend_coder.model == "claude-sonnet-5"
        assert cfg.orchestrator.on_timeout == OnTimeout.RETRY

    def test_all_prompt_paths_resolve(self) -> None:
        """agents.yaml 의 모든 prompt_path 가 실재 파일이어야 한다.

        회귀 가드 (2026-06-01): mobile_coder_* 4개 프롬프트가 .gitignore 의
        bare ``CLAUDE.md`` 패턴에 걸려 커밋되지 않아 fresh clone 에서 누락됐던
        버그 재발 방지. prompt_path 가 없으면 ``runner._resolve_prompt_path`` 가
        None 을 반환해 역할 프롬프트 없이 silent degrade 하므로 가시화한다.
        """
        backend_dir = Path(__file__).parent.parent.parent
        real_path = backend_dir / "agents.yaml"
        if not real_path.exists():
            pytest.skip("agents.yaml 없음")

        cfg = load_agents_config(real_path)
        missing = [
            f"{name}: {agent.prompt_path}"
            for name, agent in cfg.all_agents().items()
            if not (backend_dir / agent.prompt_path).exists()
        ]
        assert not missing, "prompt_path 파일이 없습니다 (.gitignore 누락 의심):\n" + "\n".join(
            missing
        )


class TestModelTierResolution:
    """model_tier 별칭 해석 (`_resolve_model_tiers`)."""

    def test_tier_maps_to_concrete_model(self) -> None:
        raw = {
            "models": {"judge": "claude-opus-4-8", "code": "claude-sonnet-5"},
            "architect": {"provider": "claude-cli", "model_tier": "judge", "prompt_path": "a"},
            "backend_coder": {"provider": "claude-cli", "model_tier": "code", "prompt_path": "b"},
            "max_concurrent": 2,
        }
        out = _resolve_model_tiers(raw)
        assert out["architect"]["model"] == "claude-opus-4-8"
        assert out["backend_coder"]["model"] == "claude-sonnet-5"
        assert "models" not in out  # 별칭 블록은 소비됨
        assert out["max_concurrent"] == 2  # 스칼라는 그대로

    def test_explicit_model_overrides_tier(self) -> None:
        raw = {
            "models": {"code": "claude-sonnet-5"},
            "backend_coder": {
                "provider": "claude-cli",
                "model": "custom-model",
                "model_tier": "code",
                "prompt_path": "b",
            },
        }
        out = _resolve_model_tiers(raw)
        assert out["backend_coder"]["model"] == "custom-model"  # 명시적 model 우선

    def test_unknown_tier_raises(self) -> None:
        raw = {
            "models": {"judge": "claude-opus-4-8"},
            "architect": {
                "provider": "claude-cli",
                "model_tier": "nonexistent",
                "prompt_path": "a",
            },
        }
        with pytest.raises(ValueError, match="model_tier"):
            _resolve_model_tiers(raw)

    def test_missing_model_and_tier_raises(self) -> None:
        raw = {"models": {}, "architect": {"provider": "claude-cli", "prompt_path": "a"}}
        with pytest.raises(ValueError, match="필요"):
            _resolve_model_tiers(raw)

    def test_legacy_concrete_model_without_models_block(self) -> None:
        """models 블록 없는 구형 yaml — concrete model 그대로 동작."""
        raw = {
            "architect": {"provider": "claude-cli", "model": "claude-opus-4-8", "prompt_path": "a"}
        }
        out = _resolve_model_tiers(raw)
        assert out["architect"]["model"] == "claude-opus-4-8"
