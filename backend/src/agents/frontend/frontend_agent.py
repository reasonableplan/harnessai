"""Frontend Agent (Level 2) — React/TypeScript 프론트엔드 코드 생성."""
from __future__ import annotations

import xml.sax.saxutils as saxutils

from src.core.agent.base_code_generator import BaseCodeGeneratorAgent
from src.core.types import Task


class FrontendAgent(BaseCodeGeneratorAgent):
    def _build_prompt(self, task: Task, context: str = "") -> str:
        ctx_section = ""
        if context:
            ctx_section = (
                "\n## Existing codebase (follow these patterns and conventions)\n"
                f"<existing_code>\n{saxutils.escape(context)}\n</existing_code>\n\n"
            )
        return (
            "You are an expert React/TypeScript frontend engineer. Generate production-quality code.\n"
            "Respond with JSON: {\"files\": [{\"path\": str, \"content\": str, \"action\": str}], \"summary\": str}\n\n"
            f"{ctx_section}"
            f"<task>\nTitle: {saxutils.escape(task.title)}\nDescription: {saxutils.escape(task.description)}\n</task>"
        )
