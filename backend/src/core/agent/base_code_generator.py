"""LLM으로 파일을 생성하는 에이전트의 공통 기반 클래스."""
from __future__ import annotations

import asyncio
import hashlib
import uuid
import xml.sax.saxutils as saxutils
from pathlib import Path
from typing import Any

from src.core.agent.base_agent import BaseAgent
from src.core.errors import SandboxEscapeError
from src.core.messaging.message_bus import MessageBus
from src.core.state.state_store import StateStore
from src.core.types import AgentConfig, Task, TaskResult

MAX_TOKENS = 16_000
TOKEN_BUDGET = 100_000_000
_MAX_CONTEXT_CHARS = 12_000  # 워크스페이스 컨텍스트 최대 길이
_MAX_FILE_CHARS = 2_000      # 개별 파일 최대 읽기 길이

# 에이전트 도메인별 관심 파일 패턴
_DOMAIN_FILE_PATTERNS: dict[str, list[str]] = {
    "backend": [
        "**/*.py", "**/requirements.txt", "**/pyproject.toml",
        "**/alembic.ini", "**/docker-compose.yml",
    ],
    "frontend": [
        "**/*.ts", "**/*.tsx", "**/package.json", "**/tsconfig.json",
        "**/*.css", "**/vite.config.*",
    ],
    "git": [
        "**/docker-compose.yml", "**/Dockerfile", "**/.gitignore",
        "**/Makefile", "**/*.sh", "**/*.yml", "**/*.yaml",
    ],
    "docs": [
        "**/*.md", "**/*.py", "**/*.ts",  # 문서 작성 시 코드 참조
    ],
}

# 모든 에이전트가 참조해야 하는 공유 파일 패턴
_SHARED_PATTERNS = [
    "**/types/**", "**/models/**", "**/schemas/**",
    "**/domain.ts", "**/base.py", "**/config.py",
]


class BaseCodeGeneratorAgent(BaseAgent):
    """LLM으로 파일을 생성하는 에이전트의 공통 로직.

    서브클래스는 _role_description만 설정하면 된다.
    """

    def __init__(
        self,
        config: AgentConfig,
        message_bus: MessageBus,
        state_store: StateStore,
        git_service: Any,
        llm_client: Any,
        work_dir: str = "./workspace",
        temperature: float = 0.2,
        code_search: Any = None,
    ) -> None:
        super().__init__(config, message_bus, state_store, git_service)
        self._llm = llm_client
        self._work_dir = Path(work_dir).resolve()
        self._temperature = temperature
        self._code_search = code_search

    # 서브클래스에서 오버라이드할 role description
    _role_description: str = "You are a code generation assistant."

    def _build_prompt(self, task: Task, context: str = "") -> str:
        """공통 프롬프트 템플릿. 서브클래스는 _role_description만 설정하면 된다."""
        ctx_section = ""
        if context:
            ctx_section = (
                "\n## Existing codebase (follow these patterns and conventions)\n"
                "<existing_code>\n"
                f"{saxutils.escape(context)}\n"
                "</existing_code>\n\n"
                "IMPORTANT: Follow the existing file structure and naming conventions. "
                "Generate files that are consistent with the codebase above.\n\n"
            )
        return (
            f"{self._role_description}\n"
            'Respond with JSON: {"files": [{"path": str, "content": str, "action": str}], "summary": str}\n\n'
            f"{ctx_section}"
            f"<task>\nTitle: {saxutils.escape(task.title)}\n"
            f"Description: {saxutils.escape(task.description)}\n</task>"
        )

    async def execute_task(self, task: Task) -> TaskResult:
        try:
            # 1. RAG 검색 시도
            context = await self._search_codebase(task)
            # 2. RAG 실패 시 workspace 직접 스캔
            if not context:
                context = await self._scan_workspace_context(task)
            prompt = self._build_prompt(task, context=context)
            data, input_tokens, output_tokens = await self._llm.chat_json(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=MAX_TOKENS,
                temperature=self._temperature,
                token_budget=TOKEN_BUDGET,
            )
            await self._publish_token_usage(input_tokens, output_tokens)

            files = data.get("files", []) if isinstance(data, dict) else []
            artifact_paths: list[str] = []

            for f in files:
                path = f.get("path", "")
                content = f.get("content", "")
                if not path or not content:
                    continue
                abs_path = self._safe_resolve(path)
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                await asyncio.to_thread(abs_path.write_text, content, "utf-8")

                await self._state_store.save_artifact({
                    "id": str(uuid.uuid4()),
                    "task_id": task.id,
                    "file_path": str(abs_path),
                    "content_hash": hashlib.sha256(content.encode()).hexdigest(),
                    "created_by": self.id,
                })
                artifact_paths.append(str(abs_path))

            summary = data.get("summary", "") if isinstance(data, dict) else ""
            self._log.info("Files generated", task_id=task.id, files=len(artifact_paths))
            return TaskResult(
                success=True,
                data={"files": artifact_paths, "summary": summary},
                artifacts=artifact_paths,
            )
        except SandboxEscapeError as e:
            self._log.error(
                "SECURITY: sandbox escape attempted",
                task_id=task.id, path=e.path, sandbox=e.sandbox,
            )
            return TaskResult(
                success=False,
                error={"message": "Security violation: path outside workspace"},
                artifacts=[],
            )
        except Exception as e:
            self._log.error("Code generation failed", task_id=task.id, err=str(e))
            return TaskResult(
                success=False,
                error={"message": f"Code generation failed: {type(e).__name__}"},
                artifacts=[],
            )

    async def _search_codebase(self, task: Task) -> str:
        """RAG: 태스크와 관련된 기존 코드를 검색한다."""
        if not self._code_search:
            return ""
        try:
            query = f"{task.title} {task.description or ''}"
            return await self._code_search.search_formatted(query, top_k=5, min_score=0.3)
        except Exception as e:
            self._log.warning("Code search failed, falling back to workspace scan", err=str(e))
            return ""

    async def _scan_workspace_context(self, task: Task) -> str:
        """workspace 디렉토리의 기존 파일을 스캔하여 컨텍스트로 반환한다.

        에이전트 도메인에 맞는 파일 + 공유 타입/스키마 파일을 읽어서
        다른 에이전트가 생성한 코드를 참조할 수 있게 한다.
        """
        if not self._work_dir.exists():
            return ""

        # 도메인별 패턴 + 공유 패턴
        patterns = list(_SHARED_PATTERNS)
        domain_patterns = _DOMAIN_FILE_PATTERNS.get(self.domain, [])
        patterns.extend(domain_patterns)

        # 파일 수집 (중복 제거)
        collected_files: dict[str, str] = {}  # rel_path → content
        total_chars = 0

        for pattern in patterns:
            for file_path in sorted(self._work_dir.glob(pattern)):
                if not file_path.is_file():
                    continue
                rel = str(file_path.relative_to(self._work_dir))
                if rel in collected_files:
                    continue
                # 바이너리/큰 파일 스킵
                if file_path.suffix in (".png", ".jpg", ".ico", ".woff", ".lock"):
                    continue
                if file_path.stat().st_size > 50_000:
                    continue
                try:
                    content = await asyncio.to_thread(
                        file_path.read_text, "utf-8", "replace"
                    )
                    truncated = content[:_MAX_FILE_CHARS]
                    if total_chars + len(truncated) > _MAX_CONTEXT_CHARS:
                        break
                    collected_files[rel] = truncated
                    total_chars += len(truncated)
                except Exception:
                    continue
            if total_chars >= _MAX_CONTEXT_CHARS:
                break

        if not collected_files:
            return ""

        parts = []
        for rel_path, content in collected_files.items():
            parts.append(f"### {rel_path}\n```\n{content}\n```")

        self._log.info("Workspace context loaded",
                       files=len(collected_files), chars=total_chars)
        return "\n\n".join(parts)

    def _safe_resolve(self, rel_path: str) -> Path:
        """Sandbox escape 방지: work_dir 밖 경로 차단."""
        resolved = (self._work_dir / rel_path).resolve()
        if not resolved.is_relative_to(self._work_dir):
            raise SandboxEscapeError(rel_path, str(self._work_dir))
        return resolved
