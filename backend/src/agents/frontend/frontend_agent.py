"""Frontend Agent (Level 2) — React/TypeScript 프론트엔드 코드 생성."""
from __future__ import annotations

from src.core.agent.base_code_generator import BaseCodeGeneratorAgent


class FrontendAgent(BaseCodeGeneratorAgent):
    _role_description = "You are an expert React/TypeScript frontend engineer. Generate production-quality code."
