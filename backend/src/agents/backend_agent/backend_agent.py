"""Backend Agent (Level 2) — Python/TypeScript 백엔드 코드 생성."""
from __future__ import annotations

from src.core.agent.base_code_generator import BaseCodeGeneratorAgent


class BackendAgent(BaseCodeGeneratorAgent):
    _role_description = "You are an expert backend engineer. Generate production-quality code."
