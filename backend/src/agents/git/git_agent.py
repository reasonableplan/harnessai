"""Git Agent (Level 2) — branch, commit, PR 작업 처리."""
from __future__ import annotations

import asyncio
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
            return TaskResult(success=False, error={"message": "Git task failed"}, artifacts=[])

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
        work_dir = self._git_service.work_dir
        if not work_dir:
            raise RuntimeError("git_service.work_dir is not configured")
        # 커밋 메시지: 250자 초과 시 자름
        commit_msg = task.title[:250].strip() or f"chore: task {task.id[:8]}"

        # -u: 이미 추적 중인 파일만 스테이징 (.env 등 미추적 파일 제외)
        await self._run_git(work_dir, "add", "-u")
        await self._run_git(work_dir, "commit", "-m", commit_msg)
        return TaskResult(success=True, data={"committed": True}, artifacts=[])

    @staticmethod
    async def _run_git(work_dir: str, *args: str) -> str:
        """비동기 git 명령 실행. 이벤트 루프를 블로킹하지 않는다."""
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", work_dir, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(stderr.decode().strip())
        return stdout.decode().strip()

    async def _handle_pr(self, task: Task) -> TaskResult:
        pr_number = await self._git_service.create_pr(
            title=task.title,
            body=task.description or "",
            head=f"feat/{task.id[:8]}",
            linked_issues=[task.github_issue_number] if task.github_issue_number else [],
        )
        log.info("PR created", pr=pr_number, task_id=task.id)
        return TaskResult(success=True, data={"pr_number": pr_number}, artifacts=[])
