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


class BaseCodeGeneratorAgent(BaseAgent):
    """LLM으로 파일을 생성하는 에이전트의 공통 로직.

    서브클래스는 _build_prompt()만 구현하면 된다.
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
                f"<existing_code>\n{saxutils.escape(context)}\n</existing_code>\n\n"
            )
        return (
            f"{self._role_description}\n"
            'Respond with JSON: {"files": [{"path": str, "content": str, "action": str}], "summary": str}\n\n'
            f"{ctx_section}"
            f"<task>\nTitle: {saxutils.escape(task.title)}\nDescription: {saxutils.escape(task.description)}\n</task>"
        )

    async def execute_task(self, task: Task) -> TaskResult:
        try:
            # RAG: 기존 코드베이스에서 관련 코드 검색
            context = await self._search_codebase(task)
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
            self._log.warning("Code search failed, proceeding without context", err=str(e))
            return ""

    # _build_prompt는 위에서 기본 구현 제공. 서브클래스는 _role_description만 설정하면 됨.

    def _safe_resolve(self, rel_path: str) -> Path:
        """Sandbox escape 방지: work_dir 밖 경로 차단."""
        resolved = (self._work_dir / rel_path).resolve()
        if not resolved.is_relative_to(self._work_dir):
            raise SandboxEscapeError(rel_path, str(self._work_dir))
        return resolved
