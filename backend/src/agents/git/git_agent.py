"""Git Agent (Level 2) — branch, commit, PR 작업 처리."""
from __future__ import annotations

import subprocess
from typing import Any

from src.core.agent.base_agent import BaseAgent
from src.core.logging.logger import get_logger
from src.core.messaging.message_bus import MessageBus
from src.core.state.state_store import StateStore
from src.core.types import AgentConfig, Task, TaskResult

log = get_logger("GitAgent")


class GitAgent(BaseAgent):
    def __init__(
        self,
        config: AgentConfig,
        message_bus: MessageBus,
        state_store: StateStore,
        git_service: Any,
    ) -> None:
        super().__init__(config, message_bus, state_store, git_service)

    async def execute_task(self, task: Task) -> TaskResult:
        label = task.labels or []
        task_type = self._detect_type(label, task.title)

        try:
            if task_type == "branch":
                return await self._handle_branch(task)
            elif task_type == "commit":
                return await self._handle_commit(task)
            elif task_type == "pr":
                return await self._handle_pr(task)
            else:
                return TaskResult(
                    success=False,
                    error={"message": f"Unknown git task type for: {task.title}"},
                    artifacts=[],
                )
        except Exception as e:
            log.error("Git task failed", task_id=task.id, err=str(e))
            return TaskResult(success=False, error={"message": str(e)}, artifacts=[])

    def _detect_type(self, labels: list[str], title: str) -> str:
        combined = " ".join(labels).lower() + " " + title.lower()
        if "branch" in combined:
            return "branch"
        if "commit" in combined:
            return "commit"
        if "pr" in combined or "pull request" in combined:
            return "pr"
        return "unknown"

    async def _handle_branch(self, task: Task) -> TaskResult:
        branch_name = f"feat/{task.id[:8]}"
        await self._git_service.create_branch(branch_name)
        log.info("Branch created", branch=branch_name, task_id=task.id)
        return TaskResult(success=True, data={"branch": branch_name}, artifacts=[])

    async def _handle_commit(self, task: Task) -> TaskResult:
        work_dir = self._git_service._work_dir
        try:
            subprocess.run(["git", "-C", work_dir, "add", "-A"], check=True, capture_output=True)
            subprocess.run(
                ["git", "-C", work_dir, "commit", "-m", task.title],
                check=True, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(e.stderr) from e
        return TaskResult(success=True, data={"committed": True}, artifacts=[])

    async def _handle_pr(self, task: Task) -> TaskResult:
        pr_number = await self._git_service.create_pr(
            title=task.title,
            body=task.description or "",
            head=f"feat/{task.id[:8]}",
            linked_issues=[task.github_issue_number] if task.github_issue_number else [],
        )
        log.info("PR created", pr=pr_number, task_id=task.id)
        return TaskResult(success=True, data={"pr_number": pr_number}, artifacts=[])
