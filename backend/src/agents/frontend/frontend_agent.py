"""Frontend Agent (Level 2) — React/TypeScript 프론트엔드 코드 생성."""
from __future__ import annotations

from src.core.agent.base_code_generator import BaseCodeGeneratorAgent
from src.core.types import Task


class FrontendAgent(BaseCodeGeneratorAgent):
    def _build_prompt(self, task: Task) -> str:
        return (
            "You are an expert React/TypeScript frontend engineer. Generate production-quality code.\n"
            "Respond with JSON: {\"files\": [{\"path\": str, \"content\": str, \"action\": str}], \"summary\": str}\n\n"
            f"<task>\nTitle: {task.title}\nDescription: {task.description}\n</task>"
        )
