"""LLM으로 파일을 생성하는 에이전트의 공통 기반 클래스."""
from __future__ import annotations

import hashlib
import uuid
from abc import abstractmethod
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
    ) -> None:
        super().__init__(config, message_bus, state_store, git_service)
        self._llm = llm_client
        self._work_dir = Path(work_dir).resolve()
        self._temperature = temperature

    async def execute_task(self, task: Task) -> TaskResult:
        try:
            prompt = self._build_prompt(task)
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
                abs_path.write_text(content, encoding="utf-8")

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
        except Exception as e:
            self._log.error("Code generation failed", task_id=task.id, err=str(e))
            return TaskResult(success=False, error={"message": str(e)}, artifacts=[])

    @abstractmethod
    def _build_prompt(self, task: Task) -> str:
        """에이전트별 시스템 프롬프트 생성."""
        ...

    def _safe_resolve(self, rel_path: str) -> Path:
        """Sandbox escape 방지: work_dir 밖 경로 차단."""
        resolved = (self._work_dir / rel_path).resolve()
        if not str(resolved).startswith(str(self._work_dir)):
            raise SandboxEscapeError(rel_path, str(self._work_dir))
        return resolved
