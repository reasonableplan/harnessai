"""Git Agent (Level 2) — Git/인프라 작업 처리 + LLM 범용 코드 생성."""
from __future__ import annotations

import asyncio
import re
from typing import Any

from src.core.agent.base_code_generator import BaseCodeGeneratorAgent
from src.core.logging.logger import get_logger
from src.core.messaging.message_bus import MessageBus
from src.core.state.state_store import StateStore
from src.core.types import AgentConfig, Task, TaskResult

log = get_logger("GitAgent")


class GitAgent(BaseCodeGeneratorAgent):
    """Git/인프라 전문 에이전트.

    branch/commit/pr 태스크는 전용 핸들러로 처리하고,
    그 외(저장소 초기화, Docker 설정 등)는 LLM 코드 생성으로 처리한다.
    """

    _role_description = (
        "You are a senior DevOps/Infrastructure engineer. "
        "Generate production-quality infrastructure files: "
        "Dockerfiles, docker-compose, CI/CD configs, project scaffolding, .gitignore, Makefiles, shell scripts."
    )

    def __init__(
        self,
        config: AgentConfig,
        message_bus: MessageBus,
        state_store: StateStore,
        git_service: Any,
        llm_client: Any,
        work_dir: str = "./workspace",
        code_search: Any = None,
    ) -> None:
        super().__init__(
            config, message_bus, state_store, git_service,
            llm_client, work_dir, temperature=0.2, code_search=code_search,
        )

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
                # LLM 범용 코드 생성 (BaseCodeGeneratorAgent)
                log.info("Using LLM code generation", task_id=task.id, title=task.title)
                return await super().execute_task(task)
        except Exception as e:
            log.error("Git task failed", task_id=task.id, err=str(e))
            return TaskResult(success=False, error={"message": f"Git task failed: {e}"}, artifacts=[])

    _TYPE_PATTERNS = {
        "branch": re.compile(r'\bbranch\b'),
        "commit": re.compile(r'\bcommit\b'),
        "pr": re.compile(r'\bpr\b|\bpull\s+request\b'),
    }

    def _detect_type(self, labels: list[str], title: str) -> str:
        combined = " ".join(labels).lower() + " " + title.lower()
        for task_type, pattern in self._TYPE_PATTERNS.items():
            if pattern.search(combined):
                return task_type
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
        commit_msg = re.sub(r'[\x00-\x1f]', ' ', task.title[:250]).strip() or f"chore: task {task.id[:8]}"
        await self._run_git(work_dir, "add", "-u")
        await self._run_git(work_dir, "commit", "-m", commit_msg)
        return TaskResult(success=True, data={"committed": True}, artifacts=[])

    @staticmethod
    async def _run_git(work_dir: str, *args: str, timeout_s: float = 60.0) -> str:
        """비동기 git 명령 실행."""
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", work_dir, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError(f"git {args[0] if args else ''} timed out after {timeout_s}s")
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
