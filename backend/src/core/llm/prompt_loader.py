"""에이전트 프롬프트 마크다운 파일 로더 (싱글톤)."""
from __future__ import annotations

import os
from pathlib import Path

from src.core.logging.logger import get_logger

log = get_logger("PromptLoader")

# prompts/ 디렉토리는 프로젝트 루트 기준
_PROMPTS_DIR = Path(__file__).parent.parent.parent.parent.parent / "prompts"


class PromptLoader:
    _instance: PromptLoader | None = None

    def __new__(cls) -> PromptLoader:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cache: dict[str, str] = {}
            cls._instance._prompts_dir = _PROMPTS_DIR
        return cls._instance

    def load_agent_prompt(self, agent_name: str) -> str:
        """shared.md + {agent_name}.md 를 합쳐서 반환. 캐시 적용."""
        if agent_name in self._cache:
            return self._cache[agent_name]

        parts: list[str] = []

        shared_path = self._resolve_path("shared.md")
        if shared_path and shared_path.exists():
            parts.append(shared_path.read_text(encoding="utf-8"))

        agent_path = self._resolve_path(f"{agent_name}.md")
        if agent_path and agent_path.exists():
            parts.append(agent_path.read_text(encoding="utf-8"))
        else:
            log.warn("Agent prompt file not found", agent=agent_name)

        result = "\n\n".join(parts)
        self._cache[agent_name] = result
        return result

    def _resolve_path(self, filename: str) -> Path | None:
        """Path traversal 방지: prompts/ 디렉토리 밖 접근 차단."""
        resolved = (self._prompts_dir / filename).resolve()
        prompts_resolved = self._prompts_dir.resolve()
        if not str(resolved).startswith(str(prompts_resolved)):
            log.error("Path traversal attempt blocked", filename=filename)
            return None
        return resolved

    def invalidate_cache(self) -> None:
        self._cache.clear()


def get_prompt_loader() -> PromptLoader:
    return PromptLoader()
