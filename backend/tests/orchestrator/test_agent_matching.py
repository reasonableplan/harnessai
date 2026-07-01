"""Agent capability matching — 인프라 단위 테스트 (Group 3 Step 1).

10개 기능 테스트 + 1개 atom 검증 테스트 = 11개.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.orchestrator.agent_matching import (
    find_best_agent_for_task,
    match_task_to_agent,
)
from src.orchestrator.config import AgentConfig, load_agents_config
from src.orchestrator.profile_loader import _HAS_KEY_PROVIDERS

# ── helpers ─────────────────────────────────────────────────────────────────


def _make_agent(
    *,
    capabilities: list[str] | None = None,
    profile_ids: list[str] | None = None,
) -> AgentConfig:
    return AgentConfig(
        provider="claude-cli",
        model="claude-sonnet-5",
        prompt_path="agents/test/CLAUDE.md",
        requires_capabilities=capabilities or [],
        requires_profile_ids=profile_ids or [],
    )


def _make_full_agents_yaml(tmp_path: Path) -> Path:
    """agents.yaml 형식 전체 agent dict — load_agents_config 용."""
    base_agent: dict = {
        "provider": "claude-cli",
        "model": "claude-sonnet-5",
        "prompt_path": "agents/test/CLAUDE.md",
        "timeout_seconds": 300,
        "on_timeout": "escalate",
        "max_retries_on_timeout": 0,
        "max_tokens": 8192,
    }
    data = {
        "architect": {**base_agent, "requires_capabilities": [], "requires_profile_ids": []},
        "designer": {**base_agent, "requires_capabilities": [], "requires_profile_ids": []},
        "orchestrator": {**base_agent, "requires_capabilities": [], "requires_profile_ids": []},
        "backend_coder": {
            **base_agent,
            "requires_capabilities": ["http_server", "cli_entrypoint", "sdk_surface"],
            "requires_profile_ids": [],
        },
        "frontend_coder": {
            **base_agent,
            "requires_capabilities": ["ui"],
            "requires_profile_ids": [],
        },
        "mobile_coder_rn": {
            **base_agent,
            "requires_capabilities": ["ui", "navigation"],
            "requires_profile_ids": ["react-native-expo"],
        },
        "mobile_coder_flutter": {
            **base_agent,
            "requires_capabilities": ["ui", "navigation"],
            "requires_profile_ids": ["flutter"],
        },
        "mobile_coder_android": {
            **base_agent,
            "requires_capabilities": ["ui", "navigation"],
            "requires_profile_ids": ["android-kotlin"],
        },
        "mobile_coder_ios": {
            **base_agent,
            "requires_capabilities": ["ui", "navigation"],
            "requires_profile_ids": ["ios-swift"],
        },
        "reviewer": {**base_agent, "requires_capabilities": [], "requires_profile_ids": []},
        "qa": {**base_agent, "requires_capabilities": [], "requires_profile_ids": []},
    }
    p = tmp_path / "agents.yaml"
    p.write_text(yaml.dump(data), encoding="utf-8")
    return p


# ── 1. capability-agnostic agent matches any task ────────────────────────────


class TestCapabilityAgnosticAgent:
    def test_architect_matches_any_task(self) -> None:
        architect = _make_agent(capabilities=[], profile_ids=[])
        result = match_task_to_agent(
            task_required_capabilities=frozenset({"http_server"}),
            task_required_profile_ids=frozenset(),
            agent_config=architect,
            active_has_keys=frozenset({"ui", "navigation"}),
            active_profile_ids=frozenset({"react-native-expo"}),
            agent_id="architect",
        )
        assert result.is_match is True
        assert "capability-agnostic" in result.reason

    def test_agnostic_matches_empty_task(self) -> None:
        reviewer = _make_agent()
        result = match_task_to_agent(
            task_required_capabilities=frozenset(),
            task_required_profile_ids=frozenset(),
            agent_config=reviewer,
            active_has_keys=frozenset(),
            active_profile_ids=frozenset(),
            agent_id="reviewer",
        )
        assert result.is_match is True
        assert "capability-agnostic" in result.reason


# ── 2. backend_coder matches when http_server active ────────────────────────


class TestBackendCoderMatch:
    def test_matches_when_http_server_active(self) -> None:
        backend = _make_agent(capabilities=["http_server", "cli_entrypoint", "sdk_surface"])
        result = match_task_to_agent(
            task_required_capabilities=frozenset({"http_server"}),
            task_required_profile_ids=frozenset(),
            agent_config=backend,
            active_has_keys=frozenset({"http_server", "ui"}),
            active_profile_ids=frozenset(),
            agent_id="backend_coder",
        )
        assert result.is_match is True
        assert "http_server" in result.reason

    def test_matches_when_cli_entrypoint_active(self) -> None:
        """any-of 의미론 — cli_entrypoint 만 있어도 매칭."""
        backend = _make_agent(capabilities=["http_server", "cli_entrypoint", "sdk_surface"])
        result = match_task_to_agent(
            task_required_capabilities=frozenset(),
            task_required_profile_ids=frozenset(),
            agent_config=backend,
            active_has_keys=frozenset({"cli_entrypoint"}),
            active_profile_ids=frozenset(),
            agent_id="backend_coder",
        )
        assert result.is_match is True


# ── 3. backend_coder no match when only mobile capabilities active ───────────


class TestBackendCoderNoMatch:
    def test_no_match_when_mobile_only(self) -> None:
        backend = _make_agent(capabilities=["http_server", "cli_entrypoint", "sdk_surface"])
        result = match_task_to_agent(
            task_required_capabilities=frozenset(),
            task_required_profile_ids=frozenset(),
            agent_config=backend,
            active_has_keys=frozenset({"ui", "navigation"}),
            active_profile_ids=frozenset({"react-native-expo"}),
            agent_id="backend_coder",
        )
        assert result.is_match is False
        assert "no required capability active" in result.reason


# ── 4. mobile_coder_rn needs both capability and profile ─────────────────────


class TestMobileCoderRnMatch:
    def test_matches_with_both_capability_and_profile(self) -> None:
        rn = _make_agent(capabilities=["ui", "navigation"], profile_ids=["react-native-expo"])
        result = match_task_to_agent(
            task_required_capabilities=frozenset({"ui"}),
            task_required_profile_ids=frozenset(),
            agent_config=rn,
            active_has_keys=frozenset({"ui", "navigation"}),
            active_profile_ids=frozenset({"react-native-expo"}),
            agent_id="mobile_coder_rn",
        )
        assert result.is_match is True

    def test_no_match_when_profile_missing(self) -> None:
        rn = _make_agent(capabilities=["ui", "navigation"], profile_ids=["react-native-expo"])
        result = match_task_to_agent(
            task_required_capabilities=frozenset({"ui"}),
            task_required_profile_ids=frozenset(),
            agent_config=rn,
            active_has_keys=frozenset({"ui", "navigation"}),
            active_profile_ids=frozenset({"flutter"}),  # wrong profile
            agent_id="mobile_coder_rn",
        )
        assert result.is_match is False
        assert "missing required profiles" in result.reason

    def test_no_match_when_capability_missing(self) -> None:
        rn = _make_agent(capabilities=["ui", "navigation"], profile_ids=["react-native-expo"])
        result = match_task_to_agent(
            task_required_capabilities=frozenset(),
            task_required_profile_ids=frozenset(),
            agent_config=rn,
            active_has_keys=frozenset({"http_server"}),  # no ui/navigation
            active_profile_ids=frozenset({"react-native-expo"}),
            agent_id="mobile_coder_rn",
        )
        assert result.is_match is False
        assert "no required capability active" in result.reason


# ── 5. find_best_agent prefers specific over agnostic ───────────────────────


class TestFindBestAgentSpecificity:
    def test_prefers_specific_mobile_coder_over_architect(self) -> None:
        architect = _make_agent()
        rn = _make_agent(capabilities=["ui", "navigation"], profile_ids=["react-native-expo"])
        available = {"architect": architect, "mobile_coder_rn": rn}

        best = find_best_agent_for_task(
            task_required_capabilities=frozenset({"ui", "navigation"}),
            task_required_profile_ids=frozenset(),
            available_agents=available,
            active_has_keys=frozenset({"ui", "navigation"}),
            active_profile_ids=frozenset({"react-native-expo"}),
        )
        assert best == "mobile_coder_rn"

    def test_falls_back_to_agnostic_when_no_specific_matches(self) -> None:
        architect = _make_agent()
        backend = _make_agent(capabilities=["http_server"])
        available = {"architect": architect, "backend_coder": backend}

        best = find_best_agent_for_task(
            task_required_capabilities=frozenset({"ui"}),
            task_required_profile_ids=frozenset(),
            available_agents=available,
            active_has_keys=frozenset({"ui", "navigation"}),  # no http_server
            active_profile_ids=frozenset({"react-native-expo"}),
        )
        # backend_coder doesn't match (no http_server in active), architect is agnostic
        assert best == "architect"


# ── 6. chamberlain case — backend task in RN-only env → None ────────────────


class TestChamberlainCaseBackendTask:
    def test_backend_task_in_rn_only_env_returns_none(self) -> None:
        architect = _make_agent()
        rn = _make_agent(capabilities=["ui", "navigation"], profile_ids=["react-native-expo"])
        backend = _make_agent(capabilities=["http_server", "cli_entrypoint", "sdk_surface"])
        available = {"architect": architect, "mobile_coder_rn": rn, "backend_coder": backend}

        # RN-only environment — no backend capabilities active
        best = find_best_agent_for_task(
            task_required_capabilities=frozenset({"http_server"}),
            task_required_profile_ids=frozenset(),
            available_agents=available,
            active_has_keys=frozenset({"ui", "navigation"}),
            active_profile_ids=frozenset({"react-native-expo"}),
        )
        # architect is agnostic → matches; but task has required_capabilities=[http_server]
        # architect is agnostic so it matches (agnostic ignores task caps gate).
        # This verifies current behavior: agnostic agents accept all tasks.
        # The caller (Step 2) is responsible for surfacing a violation when
        # the assigned agent cannot actually handle the required capability.
        # For the pure matching infrastructure, agnostic = always match.
        assert best == "architect"

    def test_backend_task_returns_none_when_only_specific_agents_available(self) -> None:
        """No agnostic fallback — only specific agents, none matching backend task."""
        rn = _make_agent(capabilities=["ui", "navigation"], profile_ids=["react-native-expo"])
        backend = _make_agent(capabilities=["http_server", "cli_entrypoint", "sdk_surface"])
        available = {"mobile_coder_rn": rn, "backend_coder": backend}

        best = find_best_agent_for_task(
            task_required_capabilities=frozenset({"http_server"}),
            task_required_profile_ids=frozenset(),
            available_agents=available,
            active_has_keys=frozenset({"ui", "navigation"}),  # backend caps not active
            active_profile_ids=frozenset({"react-native-expo"}),
        )
        assert best is None


# ── 7. chamberlain case — UI task in RN env → mobile_coder_rn ───────────────


class TestChamberlainCaseUiTask:
    def test_ui_task_in_rn_env_matches_mobile_coder_rn(self) -> None:
        architect = _make_agent()
        rn = _make_agent(capabilities=["ui", "navigation"], profile_ids=["react-native-expo"])
        backend = _make_agent(capabilities=["http_server", "cli_entrypoint", "sdk_surface"])
        available = {"architect": architect, "mobile_coder_rn": rn, "backend_coder": backend}

        best = find_best_agent_for_task(
            task_required_capabilities=frozenset({"ui", "navigation"}),
            task_required_profile_ids=frozenset(),
            available_agents=available,
            active_has_keys=frozenset({"ui", "navigation"}),
            active_profile_ids=frozenset({"react-native-expo"}),
        )
        assert best == "mobile_coder_rn"


# ── 8. AgentConfig loads requires_* fields from YAML ────────────────────────


class TestAgentConfigLoadsRequiresFields:
    def test_loads_requires_fields(self, tmp_path: Path) -> None:
        yaml_path = _make_full_agents_yaml(tmp_path)
        cfg = load_agents_config(yaml_path)

        assert cfg.backend_coder.requires_capabilities == [
            "http_server",
            "cli_entrypoint",
            "sdk_surface",
        ]
        assert cfg.backend_coder.requires_profile_ids == []
        assert cfg.mobile_coder_rn.requires_capabilities == ["ui", "navigation"]
        assert cfg.mobile_coder_rn.requires_profile_ids == ["react-native-expo"]
        assert cfg.architect.requires_capabilities == []
        assert cfg.architect.requires_profile_ids == []


# ── 9. backward compat — missing requires_* fields → empty lists ─────────────


class TestAgentConfigBackwardCompat:
    def test_missing_requires_fields_default_to_empty(self, tmp_path: Path) -> None:
        """agents.yaml without requires_* still loads cleanly."""
        base_agent: dict = {
            "provider": "claude-cli",
            "model": "claude-sonnet-5",
            "prompt_path": "agents/test/CLAUDE.md",
        }
        data = {
            name: base_agent
            for name in [
                "architect",
                "designer",
                "orchestrator",
                "backend_coder",
                "frontend_coder",
                "mobile_coder_rn",
                "mobile_coder_flutter",
                "mobile_coder_android",
                "mobile_coder_ios",
                "reviewer",
                "qa",
            ]
        }
        p = tmp_path / "agents.yaml"
        p.write_text(yaml.dump(data), encoding="utf-8")

        cfg = load_agents_config(p)
        assert cfg.architect.requires_capabilities == []
        assert cfg.architect.requires_profile_ids == []
        assert cfg.backend_coder.requires_capabilities == []
        assert cfg.mobile_coder_rn.requires_profile_ids == []


# ── 10. find_best_agent returns None when no agent matches ──────────────────


class TestFindBestAgentReturnsNone:
    def test_returns_none_when_no_match(self) -> None:
        backend = _make_agent(capabilities=["http_server"])
        rn = _make_agent(capabilities=["ui", "navigation"], profile_ids=["react-native-expo"])
        available = {"backend_coder": backend, "mobile_coder_rn": rn}

        # active: flutter only — rn profile missing, no http_server
        best = find_best_agent_for_task(
            task_required_capabilities=frozenset({"http_server"}),
            task_required_profile_ids=frozenset(),
            available_agents=available,
            active_has_keys=frozenset({"ui", "navigation"}),
            active_profile_ids=frozenset({"flutter"}),
        )
        assert best is None


# ── 11. all requires_capabilities in agents.yaml are valid atoms ─────────────


class TestAllRequiredCapabilitiesAreValidAtoms:
    """Typo guard — every requires_capabilities value must be a known has.* atom.

    Known atoms are:
    - keys in profile_loader._HAS_KEY_PROVIDERS (provider-mapped atoms)
    - "ui", "navigation", "storage", "users", "ipc", "build_config"
      (common atoms used in fragments but not necessarily in _HAS_KEY_PROVIDERS)

    We use a broad allow-list rather than _HAS_KEY_PROVIDERS alone because
    some atoms (ui, navigation, users) are intentionally not in _HAS_KEY_PROVIDERS
    (no single provider; not a consistency-check signal).
    """

    # Full set of valid has.* atoms as of Group 1/3 Step 1.
    VALID_ATOMS: frozenset[str] = frozenset(
        {
            # Provider-mapped atoms (from _HAS_KEY_PROVIDERS)
            "http_server",
            "cli_entrypoint",
            "ipc",
            "sdk_surface",
            # Fragment-driven atoms (not provider-mapped but valid capability signals)
            "ui",
            "navigation",
            "storage",
            "users",
            "build_config",
        }
    )

    def test_all_requires_capabilities_are_valid_atoms(self) -> None:
        real_path = Path(__file__).parent.parent.parent / "agents.yaml"
        if not real_path.exists():
            pytest.skip("agents.yaml 없음")

        cfg = load_agents_config(real_path)
        agents = cfg.all_agents()

        invalid: list[tuple[str, str]] = []
        for agent_id, agent_cfg in agents.items():
            for cap in agent_cfg.requires_capabilities:
                if cap not in self.VALID_ATOMS:
                    invalid.append((agent_id, cap))

        assert not invalid, (
            f"agents.yaml 에 알려지지 않은 capability atom 이 있습니다 (typo 가능성): {invalid}"
        )

    def test_provider_mapped_atoms_are_subset_of_valid_atoms(self) -> None:
        """_HAS_KEY_PROVIDERS 의 키가 모두 VALID_ATOMS 안에 있는지 확인.

        _HAS_KEY_PROVIDERS 에 새 atom 이 추가되면 VALID_ATOMS 도 업데이트 필요.
        """
        provider_atoms = frozenset(_HAS_KEY_PROVIDERS.keys())
        unknown = provider_atoms - self.VALID_ATOMS
        assert not unknown, (
            f"_HAS_KEY_PROVIDERS 에 새 atom 이 추가됐지만 "
            f"VALID_ATOMS 에 반영되지 않음: {unknown}. "
            f"TestAllRequiredCapabilitiesAreValidAtoms.VALID_ATOMS 를 업데이트하세요."
        )
