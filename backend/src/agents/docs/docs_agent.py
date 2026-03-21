"""Docs Agent (Level 2) — 문서 생성."""
from __future__ import annotations

from typing import Any

from src.core.agent.base_code_generator import BaseCodeGeneratorAgent
from src.core.messaging.message_bus import MessageBus
from src.core.state.state_store import StateStore
from src.core.types import AgentConfig


class DocsAgent(BaseCodeGeneratorAgent):
    _role_description = "You are a technical documentation specialist. Generate clear, comprehensive documentation."

    def __init__(
        self,
        config: AgentConfig,
        message_bus: MessageBus,
        state_store: StateStore,
        git_service: Any,
        llm_client: Any,
        work_dir: str = "./workspace",
        code_search: Any = None,
    ) -> None:
        # Docs uses slightly higher temperature for more natural writing
        super().__init__(
            config, message_bus, state_store, git_service, llm_client, work_dir,
            temperature=0.3, code_search=code_search,
        )
