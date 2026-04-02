"""대시보드 의존성 주입."""
from __future__ import annotations

from pathlib import Path

from src.orchestrator.config import OrchestratorConfig, load_agents_config
from src.orchestrator.phase import PhaseManager
from src.orchestrator.runner import AgentRunner
from src.orchestrator.state import StateManager

# 싱글톤 인스턴스 (create_app에서 초기화)
_state_manager: StateManager | None = None
_phase_manager: PhaseManager | None = None
_runner: AgentRunner | None = None
_config: OrchestratorConfig | None = None


def init_deps(project_dir: str | Path) -> None:
    """앱 시작 시 호출 — 의존성 초기화."""
    global _state_manager, _phase_manager, _runner, _config
    project = Path(project_dir).resolve()
    _config = load_agents_config(project / "agents.yaml")
    _state_manager = StateManager(project)
    _phase_manager = PhaseManager(_state_manager)
    _runner = AgentRunner(config=_config, project_dir=project)


def get_state_manager() -> StateManager:
    if _state_manager is None:
        raise RuntimeError("StateManager not initialized — call init_deps() first")
    return _state_manager


def get_phase_manager() -> PhaseManager:
    if _phase_manager is None:
        raise RuntimeError("PhaseManager not initialized — call init_deps() first")
    return _phase_manager


def get_runner() -> AgentRunner:
    if _runner is None:
        raise RuntimeError("AgentRunner not initialized — call init_deps() first")
    return _runner


def get_config() -> OrchestratorConfig:
    if _config is None:
        raise RuntimeError("Config not initialized — call init_deps() first")
    return _config
