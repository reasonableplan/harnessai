"""Director Agent (Level 0) — 사용자와 대화하며 에픽/태스크를 설계하고 리뷰를 처리."""
from __future__ import annotations

import uuid
import xml.sax.saxutils as saxutils
from datetime import datetime, timezone
from typing import Any

from src.agents.director.prompts import (
    CONFIRMING_SYSTEM_PROMPT,
    GATHERING_SYSTEM_PROMPT,
    REVISING_SYSTEM_PROMPT,
    STRUCTURING_SYSTEM_PROMPT,
)
from src.core.agent.base_agent import BaseAgent
from src.core.logging.logger import get_logger
from src.core.messaging.message_bus import MessageBus
from src.core.state.state_store import StateStore
from src.core.types import (
    AgentConfig,
    EpicPlan,
    IssueSpec,
    Message,
    MessageType,
    PlanStage,
    Task,
    TaskDraft,
    TaskResult,
    UserInput,
)

log = get_logger("DirectorAgent")

_MAX_DECISIONS = 10
_MAX_CONVERSATION_TURNS = 5

_VALID_AGENTS = {"director", "agent-git", "agent-backend", "agent-frontend", "agent-docs"}
_AGENT_KEYWORDS: dict[str, str] = {
    "git": "agent-git",
    "backend": "agent-backend",
    "frontend": "agent-frontend",
    "docs": "agent-docs",
    "documentation": "agent-docs",
    "api": "agent-backend",
    "database": "agent-backend",
    "ui": "agent-frontend",
    "ux": "agent-frontend",
}


def _resolve_agent_id(raw: str) -> str | None:
    """LLM이 반환한 에이전트 이름을 실제 에이전트 ID로 변환한다."""
    if not raw:
        return None
    normalized = raw.strip().lower()
    if normalized in _VALID_AGENTS:
        return normalized
    for keyword, agent_id in _AGENT_KEYWORDS.items():
        if keyword in normalized:
            return agent_id
    return None


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
        self._active_plan: EpicPlan | None = None
        self._conversation: list[dict[str, str]] = []

        async def _on_review(msg: Message) -> None:
            await self._handle_review(msg)

        self._subscribe(MessageType.REVIEW_REQUEST, _on_review)

    # ===== Public API =====

    @property
    def active_plan(self) -> EpicPlan | None:
        return self._active_plan

    async def handle_user_input(self, user_input: UserInput) -> None:
        """사용자 메시지를 받아 현재 Stage에 맞게 처리한다."""
        safe_content = saxutils.escape(user_input.content)

        try:
            await self._route_input(safe_content, user_input)
        except Exception as e:
            log.error("handle_user_input failed", err=str(e))
            await self._broadcast_director_message(
                f"처리 중 오류가 발생했습니다: {str(e)[:200]}"
            )

    async def _route_input(self, safe_content: str, user_input: UserInput) -> None:
        """분류 → Stage 라우팅. handle_user_input에서 호출."""
        # 활성 플랜이 없으면 먼저 분류
        if self._active_plan is None:
            action = await self._classify_input(safe_content)
            log.info("User input classified", action=action, source=user_input.source)

            if action == "create_epic":
                self._active_plan = EpicPlan(
                    session_id=str(uuid.uuid4()),
                    goal=safe_content,
                )
                await self._handle_gathering(safe_content)
            elif action == "status_query":
                await self._handle_status_query(safe_content)
            else:
                await self._broadcast_director_message(
                    "요청을 좀 더 구체적으로 말씀해주시겠어요? "
                    "프로젝트를 만들거나 현재 상태를 확인할 수 있습니다."
                )
            return

        # 활성 플랜이 있으면 Stage별 처리
        plan = self._active_plan
        if plan.stage == PlanStage.COMMITTED:
            # 이미 확정된 플랜 — 새 세션으로 리셋 후 재분류 (재귀 방지)
            self._active_plan = None
            self._conversation.clear()
            action = await self._classify_input(safe_content)
            log.info("User input classified (post-commit)", action=action)
            if action == "create_epic":
                self._active_plan = EpicPlan(
                    session_id=str(uuid.uuid4()),
                    goal=safe_content,
                )
                await self._handle_gathering(safe_content)
            elif action == "status_query":
                await self._handle_status_query(safe_content)
            else:
                await self._broadcast_director_message(
                    "요청을 좀 더 구체적으로 말씀해주시겠어요?"
                )
            return

        self._append_conversation("user", safe_content)

        if plan.stage == PlanStage.GATHERING:
            await self._handle_gathering(safe_content)
        elif plan.stage == PlanStage.STRUCTURING:
            await self._handle_structuring(safe_content)
        elif plan.stage == PlanStage.CONFIRMING:
            await self._handle_confirming(safe_content)

    async def handle_plan_action(self, action: str, content: str = "") -> None:
        """WS에서 받은 plan.approve / plan.revise / plan.commit 처리."""
        if self._active_plan is None:
            await self._broadcast_director_message("활성화된 프로젝트 계획이 없습니다.")
            return

        plan = self._active_plan

        if action == "approve":
            if plan.stage == PlanStage.STRUCTURING:
                plan.stage = PlanStage.CONFIRMING
                plan.updated_at = datetime.now(timezone.utc)
                await self._broadcast_plan()
                await self._broadcast_director_message(
                    "좋습니다! 최종 확인 단계입니다.\n"
                    "이대로 GitHub Issues를 생성할까요? "
                    "'진행해'라고 하시면 생성을 시작합니다."
                )
            elif plan.stage == PlanStage.CONFIRMING:
                await self._commit_plan()

        elif action == "revise":
            if content:
                self._append_conversation("user", saxutils.escape(content))
            if plan.stage in (PlanStage.STRUCTURING, PlanStage.CONFIRMING):
                plan.stage = PlanStage.STRUCTURING
                plan.updated_at = datetime.now(timezone.utc)
                await self._handle_structuring(content or "수정해주세요")

        elif action == "commit":
            if plan.stage == PlanStage.CONFIRMING:
                await self._commit_plan()
            else:
                await self._broadcast_director_message(
                    "아직 확인 단계가 아닙니다. 먼저 태스크 분해를 완료해주세요."
                )

    # ===== Stage Handlers =====

    async def _handle_gathering(self, content: str) -> None:
        """Stage 1: 요구사항 수집 대화."""
        plan = self._active_plan
        if plan is None:
            return

        plan_context = plan.model_dump(
            include={"goal", "project", "decisions"},
        )

        messages = [
            {"role": "user", "content": (
                f"<plan_context>\n{plan_context}\n</plan_context>\n\n"
                f"<conversation>\n{self._format_conversation()}\n</conversation>\n\n"
                f"<user_message>{content}</user_message>"
            )},
        ]

        data, input_tokens, output_tokens = await self._llm.chat_json(
            messages=messages, system=GATHERING_SYSTEM_PROMPT,
            max_tokens=1024, temperature=0.3,
        )
        await self._publish_token_usage(input_tokens, output_tokens)

        # ProjectContext 업데이트
        project_update = data.get("project_update", {})
        if project_update:
            self._apply_project_update(plan, project_update)

        # Decisions 추가
        for decision in data.get("decisions_append", []):
            if decision and len(plan.decisions) < _MAX_DECISIONS:
                plan.decisions.append(decision)

        plan.updated_at = datetime.now(timezone.utc)

        response = data.get("response", "")
        self._append_conversation("assistant", response)

        action = data.get("action", "continue")
        if action == "lock":
            plan.stage = PlanStage.STRUCTURING
            log.info("Requirements locked", session_id=plan.session_id)
            await self._broadcast_director_message(response)
            await self._broadcast_plan()
            # 자동으로 태스크 분해 시작
            await self._generate_task_breakdown()
        else:
            await self._broadcast_director_message(response)

    async def _handle_structuring(self, content: str) -> None:
        """Stage 2: 태스크 분해 / 수정."""
        plan = self._active_plan
        if plan is None:
            return

        # 이미 태스크가 있으면 수정 모드
        if plan.tasks:
            await self._revise_task_breakdown(content)
        else:
            await self._generate_task_breakdown()

    async def _handle_confirming(self, content: str) -> None:
        """Stage 3: 최종 확인."""
        plan = self._active_plan
        if plan is None:
            return

        plan_json = plan.model_dump(
            include={"epic_title", "epic_description", "tasks", "project", "decisions"},
        )
        system = CONFIRMING_SYSTEM_PROMPT.format(plan_json=plan_json)
        messages = [
            {"role": "user", "content": (
                f"<conversation>\n{self._format_conversation()}\n</conversation>\n\n"
                f"<user_message>{content}</user_message>"
            )},
        ]

        data, input_tokens, output_tokens = await self._llm.chat_json(
            messages=messages, system=system, max_tokens=2048, temperature=0.3,
        )
        await self._publish_token_usage(input_tokens, output_tokens)

        response = data.get("response", "")
        action = data.get("action", "revise")
        self._append_conversation("assistant", response)

        if action == "commit":
            await self._broadcast_director_message(response)
            await self._commit_plan()
        elif action == "revise":
            self._apply_task_update(plan, data)
            plan.stage = PlanStage.STRUCTURING
            plan.updated_at = datetime.now(timezone.utc)
            await self._broadcast_director_message(response)
            await self._broadcast_plan()

    # ===== Task Breakdown =====

    async def _generate_task_breakdown(self) -> None:
        """LLM에 태스크 분해를 요청한다."""
        plan = self._active_plan
        if plan is None:
            return

        plan_json = plan.model_dump(
            include={"goal", "project", "decisions"},
        )
        system = STRUCTURING_SYSTEM_PROMPT.format(plan_json=plan_json)
        messages = [
            {"role": "user", "content": "위 요구사항을 기반으로 에픽과 태스크를 분해해주세요."},
        ]

        data, input_tokens, output_tokens = await self._llm.chat_json(
            messages=messages, system=system, max_tokens=2048, temperature=0.3,
        )
        await self._publish_token_usage(input_tokens, output_tokens)

        self._apply_task_update(plan, data)
        plan.updated_at = datetime.now(timezone.utc)

        response = data.get("response", "태스크 분해가 완료되었습니다.")
        self._append_conversation("assistant", response)
        await self._broadcast_director_message(response)
        await self._broadcast_plan()

    async def _revise_task_breakdown(self, feedback: str) -> None:
        """사용자 피드백으로 태스크 분해를 수정한다."""
        plan = self._active_plan
        if plan is None:
            return

        plan_json = plan.model_dump(
            include={"epic_title", "epic_description", "tasks", "project", "decisions"},
        )
        system = REVISING_SYSTEM_PROMPT.format(
            plan_json=plan_json, user_feedback=feedback,
        )
        messages = [
            {"role": "user", "content": f"<user_message>{feedback}</user_message>"},
        ]

        data, input_tokens, output_tokens = await self._llm.chat_json(
            messages=messages, system=system, max_tokens=2048, temperature=0.3,
        )
        await self._publish_token_usage(input_tokens, output_tokens)

        self._apply_task_update(plan, data)
        plan.updated_at = datetime.now(timezone.utc)

        response = data.get("response", "태스크를 수정했습니다.")
        self._append_conversation("assistant", response)
        await self._broadcast_director_message(response)
        await self._broadcast_plan()

    # ===== Commit (GitHub Issues 생성) =====

    async def _commit_plan(self) -> None:
        """확정된 플랜을 GitHub Issues(Board) 먼저 → DB 나중으로 변환한다."""
        plan = self._active_plan
        if plan is None:
            return

        if not plan.tasks:
            await self._broadcast_director_message("태스크가 없어서 생성할 수 없습니다.")
            return

        # temp_id → 실제 task_id 매핑 (의존성 해소용)
        temp_to_real: dict[str, str] = {}
        for draft in plan.tasks:
            temp_to_real[draft.temp_id] = str(uuid.uuid4())

        # ---- Phase 1: Board-first — GitHub Issues 모두 생성 ----
        issue_results: list[dict[str, Any]] = []
        for draft in plan.tasks:
            body_parts = [draft.description]
            if draft.dependencies:
                body_parts.append(
                    "\n\n**Dependencies:** " + ", ".join(draft.dependencies)
                )

            try:
                issue_number = await self._git_service.create_issue(
                    IssueSpec(
                        title=draft.title,
                        body="\n".join(body_parts),
                        labels=["agent-task"],
                    )
                )
            except Exception as e:
                log.error("Failed to create issue, aborting commit", title=draft.title, err=str(e))
                # 롤백: 이미 생성된 Issues를 close
                for created in issue_results:
                    try:
                        await self._git_service.close_issue(created["issue_number"])
                    except Exception as rollback_err:
                        log.warning("Rollback: failed to close issue",
                                    issue=created["issue_number"], err=str(rollback_err))
                await self._broadcast_director_message(
                    f"GitHub Issue 생성 실패: {draft.title}. "
                    f"이미 생성된 {len(issue_results)}개 Issue를 정리했습니다."
                )
                return

            issue_results.append({
                "temp_id": draft.temp_id,
                "issue_number": issue_number,
                "title": draft.title,
                "agent": draft.agent,
                "priority": draft.priority,
                "complexity": draft.complexity,
                "description": draft.description,
                "dependencies": draft.dependencies,
            })

        # ---- Phase 2: DB — Epic + Tasks 생성 (Board 성공 후) ----
        epic_id = str(uuid.uuid4())
        await self._state_store.create_epic({
            "id": epic_id,
            "title": plan.epic_title or plan.project.topic or "Untitled Epic",
            "description": plan.epic_description or plan.project.purpose or "",
            "status": "active",
        })

        created_issues: list[dict[str, Any]] = []
        for item in issue_results:
            task_id = temp_to_real[item["temp_id"]]
            assigned = _resolve_agent_id(item["agent"] or "")

            await self._state_store.create_task({
                "id": task_id,
                "epic_id": epic_id,
                "title": item["title"],
                "description": item["description"],
                "assigned_agent": assigned,
                "status": "backlog",
                "board_column": "Backlog",
                "github_issue_number": item["issue_number"],
                "priority": item["priority"],
                "complexity": item["complexity"],
                "dependencies": [
                    temp_to_real[d] for d in item["dependencies"] if d in temp_to_real
                ],
            })

            created_issues.append({
                "task_id": task_id,
                "title": item["title"],
                "agent": assigned,
                "issue_number": item["issue_number"],
            })

        plan.stage = PlanStage.COMMITTED
        plan.updated_at = datetime.now(timezone.utc)

        log.info(
            "Epic committed",
            epic_id=epic_id,
            task_count=len(created_issues),
            session_id=plan.session_id,
        )

        # 결과 브로드캐스트
        await self._message_bus.publish(
            Message(
                id=str(uuid.uuid4()),
                type=MessageType.DIRECTOR_COMMITTED,
                from_agent=self.id,
                payload={
                    "epicId": epic_id,
                    "epicTitle": plan.epic_title,
                    "issues": created_issues,
                    "sessionId": plan.session_id,
                },
                trace_id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
            )
        )

        summary = (
            f"GitHub Issues {len(created_issues)}개가 생성되었습니다!\n\n"
            + "\n".join(
                f"- #{i.get('issue_number', '?')} {i['title']} → {i.get('agent', 'unassigned')}"
                for i in created_issues
            )
        )
        await self._broadcast_director_message(summary)
        self._conversation.clear()

    # ===== Classification =====

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
        lower = text.strip().lower()
        log.info("Classification raw response", text=repr(text[:100]))
        if "create_epic" in lower:
            return "create_epic"
        if "status_query" in lower:
            return "status_query"
        return "clarify"

    # ===== Status Query =====

    async def _handle_status_query(self, content: str) -> None:
        agents = await self._state_store.get_all_agents()
        tasks = await self._state_store.get_all_tasks()

        busy = [a for a in agents if a.status == "busy"]
        in_progress = [t for t in tasks if t.status == "in-progress"]
        done = [t for t in tasks if t.status == "done"]

        status_msg = (
            f"에이전트 {len(agents)}명 (작업 중: {len(busy)}명)\n"
            f"태스크 {len(tasks)}개 (진행 중: {len(in_progress)}, 완료: {len(done)})"
        )
        await self._broadcast_director_message(status_msg)

    # ===== Review Handler =====

    async def _handle_review(self, msg: Message) -> None:
        payload = msg.payload or {}
        if not isinstance(payload, dict):
            return
        task_id = payload.get("taskId")
        result = payload.get("result", {})
        if not task_id:
            return

        success = result.get("success", False) if isinstance(result, dict) else False
        target_column = "Done" if success else "Ready"
        target_status = "done" if success else "ready"

        task = await self._state_store.get_task(task_id)
        if task and task.github_issue_number:
            try:
                await self._git_service.move_issue_to_column(
                    task.github_issue_number, target_column
                )
            except Exception as e:
                log.error("Review: Board move failed", task_id=task_id, err=str(e))
                return

        updates: dict[str, Any] = {"status": target_status, "board_column": target_column}
        if not success:
            updates["retry_count_increment"] = 1
        await self._state_store.update_task(task_id, updates)
        log.info("Task review processed", task_id=task_id, approved=success)

    # ===== Helpers =====

    def _apply_project_update(self, plan: EpicPlan, update: dict[str, Any]) -> None:
        """LLM 응답의 project_update를 EpicPlan.project에 반영한다."""
        project = plan.project

        for field in ("topic", "purpose", "target_users", "scope", "existing_system"):
            if field in update and update[field]:
                setattr(project, field, update[field])

        if "tech_stack" in update and isinstance(update["tech_stack"], dict):
            stack = project.tech_stack
            for key in ("frontend", "backend", "database", "infra", "etc"):
                if key in update["tech_stack"] and update["tech_stack"][key]:
                    val = update["tech_stack"][key]
                    existing = getattr(stack, key)
                    if isinstance(val, list):
                        merged = list(dict.fromkeys(existing + val))
                        setattr(stack, key, merged)
                    elif isinstance(val, str):
                        if val not in existing:
                            existing.append(val)

        if "constraints" in update and isinstance(update["constraints"], list):
            for c in update["constraints"]:
                if c and c not in project.constraints:
                    project.constraints.append(c)

        if "non_goals" in update and isinstance(update["non_goals"], list):
            for ng in update["non_goals"]:
                if ng and ng not in project.non_goals:
                    project.non_goals.append(ng)

    def _apply_task_update(self, plan: EpicPlan, data: dict[str, Any]) -> None:
        """LLM 응답의 태스크 분해 결과를 EpicPlan에 반영한다."""
        if "epic_title" in data:
            plan.epic_title = data["epic_title"]
        if "epic_description" in data:
            plan.epic_description = data["epic_description"]
        if "tasks" in data and isinstance(data["tasks"], list):
            plan.tasks = [
                TaskDraft(
                    temp_id=t.get("temp_id", f"draft-{i+1}"),
                    title=t.get("title", ""),
                    description=t.get("description", ""),
                    agent=t.get("agent"),
                    priority=int(t.get("priority", 3)),
                    complexity=t.get("complexity", "medium"),
                    dependencies=list(t.get("dependencies", [])),
                )
                for i, t in enumerate(data["tasks"])
            ]

    def _append_conversation(self, role: str, content: str) -> None:
        """Sliding window 대화 기록 추가."""
        self._conversation.append({"role": role, "content": content})
        if len(self._conversation) > _MAX_CONVERSATION_TURNS * 2:
            self._conversation = self._conversation[-_MAX_CONVERSATION_TURNS * 2:]

    def _format_conversation(self) -> str:
        """대화 기록을 텍스트로 포맷."""
        if not self._conversation:
            return "(no previous conversation)"
        lines = []
        for turn in self._conversation:
            prefix = "User" if turn["role"] == "user" else "Director"
            lines.append(f"{prefix}: {turn['content']}")
        return "\n".join(lines)

    async def _broadcast_director_message(self, content: str) -> None:
        """사용자에게 Director 메시지를 WS로 전송한다."""
        await self._message_bus.publish(
            Message(
                id=str(uuid.uuid4()),
                type=MessageType.DIRECTOR_MESSAGE,
                from_agent=self.id,
                payload={"content": content},
                trace_id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
            )
        )

    async def _broadcast_plan(self) -> None:
        """현재 EpicPlan 상태를 WS로 전송한다."""
        if self._active_plan is None:
            return
        await self._message_bus.publish(
            Message(
                id=str(uuid.uuid4()),
                type=MessageType.DIRECTOR_PLAN,
                from_agent=self.id,
                payload=self._active_plan.model_dump(mode="json"),
                trace_id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
            )
        )

    async def execute_task(self, task: Task) -> TaskResult:
        """Director는 Board 태스크를 직접 실행하지 않는다."""
        log.warning("DirectorAgent.execute_task called — not expected", task_id=task.id)
        return TaskResult(
            success=False,
            error={"message": "Director does not execute tasks"},
            artifacts=[],
        )
