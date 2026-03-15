"""Director Agent (Level 0) — 사용자 입력을 에픽/태스크로 변환하고 리뷰를 처리."""
from __future__ import annotations

import uuid
import xml.sax.saxutils as saxutils
from datetime import datetime, timezone
from typing import Any

from src.core.agent.base_agent import BaseAgent
from src.core.logging.logger import get_logger
from src.core.messaging.message_bus import MessageBus
from src.core.state.state_store import StateStore
from src.core.types import (
    AgentConfig,
    AgentLevel,
    IssueSpec,
    Message,
    MessageType,
    Task,
    TaskResult,
    UserInput,
)

log = get_logger("DirectorAgent")


class DirectorAgent(BaseAgent):
    def __init__(
        self,
        config: AgentConfig,
        message_bus: MessageBus,
        state_store: StateStore,
        git_service: Any,
        llm_client: Any,
    ) -> None:
        super().__init__(config, message_bus, state_store, git_service)
        self._llm = llm_client

        # review.request 구독
        async def _on_review(msg: Message) -> None:
            await self._handle_review(msg)

        self._subscribe(MessageType.REVIEW_REQUEST, _on_review)

    async def handle_user_input(self, user_input: UserInput) -> None:
        """CLI/Dashboard에서 받은 사용자 입력을 처리한다."""
        # Prompt injection 방어: XML 딜리미터로 사용자 입력 감쌈
        safe_content = saxutils.escape(user_input.content)

        action = await self._classify_input(safe_content)
        log.info("User input classified", action=action, source=user_input.source)

        if action == "create_epic":
            await self._create_epic(safe_content)
        elif action == "status_query":
            await self._handle_status_query(safe_content)
        else:
            log.info("Clarification needed", content=safe_content[:100])

    async def _classify_input(self, content: str) -> str:
        prompt = (
            "Classify the following user request into one of: create_epic, status_query, clarify.\n"
            "Respond with only the classification word.\n\n"
            f"<request>{content}</request>"
        )
        text, _, _ = await self._llm.chat(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10,
            temperature=0.0,
        )
        result = text.strip().lower()
        if result not in {"create_epic", "status_query", "clarify"}:
            return "clarify"
        return result

    async def _create_epic(self, content: str) -> None:
        prompt = (
            "You are a project planner. Break down the following request into a structured epic with tasks.\n"
            "Respond in JSON: {\"title\": str, \"description\": str, \"tasks\": [{\"title\", \"description\", \"agent\", \"priority\"}]}\n\n"
            f"<request>{content}</request>"
        )
        data, input_tokens, output_tokens = await self._llm.chat_json(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
            temperature=0.3,
        )
        await self._publish_token_usage(input_tokens, output_tokens)

        epic_id = str(uuid.uuid4())
        await self._state_store.create_epic({
            "id": epic_id,
            "title": data.get("title", "Untitled Epic"),
            "description": data.get("description", ""),
            "status": "active",
        })

        for task_spec in data.get("tasks", []):
            task_id = str(uuid.uuid4())
            issue_number = await self._git_service.create_issue(
                IssueSpec(
                    title=task_spec.get("title", ""),
                    body=task_spec.get("description", ""),
                    labels=["agent-task"],
                )
            )
            await self._state_store.create_task({
                "id": task_id,
                "epic_id": epic_id,
                "title": task_spec.get("title", ""),
                "description": task_spec.get("description", ""),
                "assigned_agent": task_spec.get("agent"),
                "status": "backlog",
                "board_column": "Backlog",
                "github_issue_number": issue_number,
                "priority": task_spec.get("priority", 3),
            })

        log.info("Epic created", epic_id=epic_id, task_count=len(data.get("tasks", [])))

    async def _handle_status_query(self, content: str) -> None:
        agents = await self._state_store.get_all_agents()
        tasks = await self._state_store.get_all_tasks()
        log.info(
            "Status query",
            agents=len(agents),
            tasks=len(tasks),
            content=content[:50],
        )

    async def _handle_review(self, msg: Message) -> None:
        payload = msg.payload or {}
        if not isinstance(payload, dict):
            return
        task_id = payload.get("taskId")
        result = payload.get("result", {})
        if not task_id:
            return

        success = result.get("success", False) if isinstance(result, dict) else False
        if success:
            await self._state_store.update_task(task_id, {"status": "done", "board_column": "Done"})
            log.info("Task approved", task_id=task_id)
        else:
            await self._state_store.update_task(
                task_id,
                {"status": "ready", "board_column": "Ready", "retry_count_increment": 1},
            )
            log.info("Task sent back to Ready", task_id=task_id)

    async def execute_task(self, task: Task) -> TaskResult:
        """Director는 Board 태스크를 직접 실행하지 않는다."""
        log.warn("DirectorAgent.execute_task called — not expected", task_id=task.id)
        return TaskResult(success=False, error={"message": "Director does not execute tasks"}, artifacts=[])
