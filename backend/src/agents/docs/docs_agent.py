"""Docs Agent (Level 2) — 문서 생성."""
from __future__ import annotations

import xml.sax.saxutils as saxutils
from typing import Any

from src.core.agent.base_code_generator import BaseCodeGeneratorAgent
from src.core.messaging.message_bus import MessageBus
from src.core.state.state_store import StateStore
from src.core.types import AgentConfig, Task


class DocsAgent(BaseCodeGeneratorAgent):
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

    def _build_prompt(self, task: Task, context: str = "") -> str:
        ctx_section = ""
        if context:
            ctx_section = (
                "\n## Existing codebase (reference for documentation)\n"
                f"<existing_code>\n{context}\n</existing_code>\n\n"
            )
        return (
            "You are a technical documentation specialist. Generate clear, comprehensive documentation.\n"
            "Respond with JSON: {\"files\": [{\"path\": str, \"content\": str, \"action\": str}], \"summary\": str}\n\n"
            f"{ctx_section}"
            f"<task>\nTitle: {saxutils.escape(task.title)}\nDescription: {saxutils.escape(task.description)}\n</task>"
        )
