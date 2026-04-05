"""대시보드 의존성 주입."""
from __future__ import annotations

from pathlib import Path

from src.orchestrator.config import OrchestratorConfig
from src.orchestrator.orchestrate import Orchestra
from src.orchestrator.phase import PhaseManager
from src.orchestrator.runner import AgentRunner
from src.orchestrator.state import StateManager

# Orchestra 싱글톤 — 모든 컴포넌트의 단일 출처
_orchestra: Orchestra | None = None


def init_deps(project_dir: str | Path) -> None:
    """앱 시작 시 호출 — 의존성 초기화."""
    global _orchestra
    _orchestra = Orchestra(project_dir=Path(project_dir))


def get_orchestra() -> Orchestra:
    if _orchestra is None:
        raise RuntimeError("Orchestra not initialized — call init_deps() first")
    return _orchestra


def get_state_manager() -> StateManager:
    return get_orchestra().state


def get_phase_manager() -> PhaseManager:
    return get_orchestra().phase_manager


def get_runner() -> AgentRunner:
    return get_orchestra().runner


def get_config() -> OrchestratorConfig:
    return get_orchestra().config
