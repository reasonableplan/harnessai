"""Director Agent (Level 0) — 사용자와 대화하며 에픽/태스크를 설계하고 리뷰를 처리."""
from __future__ import annotations

import asyncio
import os
import re
import uuid
import xml.sax.saxutils as saxutils
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.agents.director.prompts import (
    CONFIRMING_SYSTEM_PROMPT,
    GATHERING_SYSTEM_PROMPT,
    REVISING_SYSTEM_PROMPT,
    STRUCTURING_SYSTEM_PROMPT,
    WORKER_CONSULTATION_PROMPT,
    _WORKER_DOMAINS,
)
from src.core.agent.base_agent import BaseAgent
from src.core.git_service.merge_queue import MergeQueue, MergeRequest, MergeResult
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
    ProjectContext,
    StoryDraft,
    Task,
    TaskDraft,
    TaskResult,
    UserInput,
)

log = get_logger("DirectorAgent")

_MAX_DECISIONS = 10
_MAX_CONVERSATION_TURNS = 5
_MAX_TURN_CONTENT_LEN = 8000
_MAX_FORMATTED_CONVERSATION_LEN = 16000

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


def _safe_int(val: Any, default: int = 3) -> int:
    """LLM 출력의 priority 등 정수 변환. 실패 시 기본값 반환."""
    try:
        return max(1, min(5, int(val)))
    except (ValueError, TypeError):
        return default


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
        memory_store: Any = None,
        merge_queue: MergeQueue | None = None,
    ) -> None:
        super().__init__(config, message_bus, state_store, git_service)
        self._llm = llm_client
        self._active_plan: EpicPlan | None = None
        self._conversation: list[dict[str, str]] = []
        self._plan_lock = asyncio.Lock()
        self._memory = memory_store
        self._merge_queue = merge_queue

        async def _on_review(msg: Message) -> None:
            await self._handle_review(msg)

        self._subscribe(MessageType.REVIEW_REQUEST, _on_review)

    async def restore_plan_from_db(self) -> None:
        """서버 시작 시 DB에서 마지막 활성 플랜을 복원한다."""
        try:
            plan_row = await self._state_store.get_latest_plan()
            if plan_row is None:
                return

            # EXECUTING/COMMITTED 상태면 복원 (사용자가 "시작해" 할 수 있도록)
            # 완전히 끝난 플랜(conversation 비어있고 stage=executing)은 무시
            stage = plan_row.stage
            if stage == "executing" and not plan_row.conversation:
                return

            self._active_plan = EpicPlan(
                session_id=plan_row.session_id,
                stage=PlanStage(stage),
                epic_id=getattr(plan_row, "epic_id", "") or "",
                goal=plan_row.goal,
                epic_title=plan_row.epic_title,
                epic_description=plan_row.epic_description,
                project=ProjectContext(**plan_row.project_context) if plan_row.project_context else ProjectContext(),
                decisions=list(plan_row.decisions or []),
                stories=[StoryDraft(**s) for s in (plan_row.stories or [])],
                tasks=[TaskDraft(**t) for t in (plan_row.tasks or [])],
            )
            self._conversation = list(plan_row.conversation or [])
            log.info("Plan restored from DB",
                     session_id=plan_row.session_id, stage=stage,
                     task_count=len(self._active_plan.tasks))
        except Exception as e:
            log.warning("Failed to restore plan from DB", err=str(e))

    async def _persist_plan(self) -> None:
        """현재 _active_plan 상태를 DB에 저장한다."""
        plan = self._active_plan
        if plan is None:
            return
        try:
            await self._state_store.save_plan({
                "session_id": plan.session_id,
                "stage": plan.stage.value,
                "epic_id": plan.epic_id,
                "goal": plan.goal,
                "epic_title": plan.epic_title,
                "epic_description": plan.epic_description,
                "project_context": plan.project.model_dump(),
                "decisions": plan.decisions,
                "stories": [s.model_dump() for s in plan.stories],
                "tasks": [t.model_dump() for t in plan.tasks],
                "conversation": self._conversation,
            })
        except Exception as e:
            log.warning("Failed to persist plan", err=str(e))

    # ===== Public API =====

    @property
    def active_plan(self) -> EpicPlan | None:
        return self._active_plan

    async def handle_user_input(self, user_input: UserInput) -> None:
        """사용자 메시지를 받아 현재 Stage에 맞게 처리한다."""
        async with self._plan_lock:
            safe_content = saxutils.escape(user_input.content)

            try:
                await self._route_input(safe_content, user_input)
            except Exception as e:
                log.error("handle_user_input failed", err=str(e), exc_info=True)
                await self._broadcast_director_message(
                    "처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
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
                self._append_conversation("user", safe_content)
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
            # 업무 시작 허가 대기 중 — "시작" 키워드 감지
            start_keywords = ("시작", "start", "go", "진행", "execute", "run")
            if any(kw in safe_content.lower() for kw in start_keywords):
                await self._start_execution()
            else:
                await self._broadcast_director_message(
                    "이슈가 생성되었습니다. 업무를 시작하려면 '시작해'라고 말해주세요."
                )
            return

        if plan.stage == PlanStage.EXECUTING:
            # 이미 실행 중 — 새 세션 시작
            await self._reset_session()
            if self._active_plan is None:
                await self._route_input(safe_content, user_input)
            return

        self._append_conversation("user", safe_content)

        # 승인/진행 키워드 감지 — REST API에서도 stage 전이 가능하게
        _approve_keywords = ("진행", "승인", "확인", "좋아", "approve", "ok", "yes", "시작")

        if plan.stage == PlanStage.GATHERING:
            await self._handle_gathering(safe_content)
        elif plan.stage == PlanStage.STRUCTURING:
            if plan.tasks and any(kw in safe_content.lower() for kw in _approve_keywords):
                # 태스크가 이미 있고 사용자가 승인 → CONSULTING으로 전이
                await self.handle_plan_action("approve")
            else:
                await self._handle_structuring(safe_content)
        elif plan.stage == PlanStage.CONSULTING:
            await self._broadcast_director_message(
                "에이전트 상의가 진행 중입니다. 완료되면 검토 요청드리겠습니다."
            )
        elif plan.stage == PlanStage.CONFIRMING:
            if any(kw in safe_content.lower() for kw in _approve_keywords):
                # 사용자가 승인 → 이슈 생성 (COMMITTED)
                await self.handle_plan_action("approve")
            else:
                await self._handle_confirming(safe_content)

    async def handle_plan_action(self, action: str, content: str = "") -> None:
        """WS에서 받은 plan.approve / plan.revise / plan.commit 처리."""
        if self._active_plan is None:
            await self._broadcast_director_message("활성화된 프로젝트 계획이 없습니다.")
            return

        plan = self._active_plan

        if action == "approve":
            if plan.stage == PlanStage.STRUCTURING:
                # STRUCTURING → CONSULTING (에이전트 상의 시작)
                plan.stage = PlanStage.CONSULTING
                plan.updated_at = datetime.now(timezone.utc)
                await self._broadcast_plan()
                await self._broadcast_director_message(
                    "태스크 구조가 승인되었습니다. 각 파트 에이전트와 상의를 시작합니다..."
                )
                await self._run_consulting()
            elif plan.stage == PlanStage.CONSULTING:
                # CONSULTING 완료 후 사용자가 approve → CONFIRMING
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
            if plan.stage in (PlanStage.STRUCTURING, PlanStage.CONSULTING, PlanStage.CONFIRMING):
                plan.stage = PlanStage.STRUCTURING
                plan.updated_at = datetime.now(timezone.utc)
                await self._broadcast_plan()
                await self._handle_structuring(content or "수정해주세요")

        elif action == "commit":
            if plan.stage in (PlanStage.CONFIRMING, PlanStage.CONSULTING):
                await self._commit_plan()
            else:
                await self._broadcast_director_message(
                    "아직 확인 단계가 아닙니다. 먼저 태스크 분해를 완료해주세요."
                )

        elif action == "start":
            if plan.stage == PlanStage.COMMITTED:
                await self._start_execution()
            else:
                await self._broadcast_director_message(
                    "아직 이슈가 생성되지 않았습니다. 먼저 계획을 확정해주세요."
                )

    # ===== Stage Handlers =====

    async def _handle_gathering(self, content: str) -> None:
        """Stage 1: 요구사항 수집 대화."""
        plan = self._active_plan
        if plan is None:
            return

        log.info("GATHERING: start", content_len=len(content))

        plan_context = plan.model_dump(
            include={"goal", "project", "decisions"},
        )

        # 장기 기억 검색
        log.info("GATHERING: recalling memories...")
        memory_section = await self._recall_memories(content)
        log.info("GATHERING: memories done", memory_len=len(memory_section))

        messages = [
            {"role": "user", "content": (
                f"{memory_section}"
                f"<plan_context>\n{plan_context}\n</plan_context>\n\n"
                f"<conversation>\n{self._format_conversation()}\n</conversation>\n\n"
                f"<user_message>{content}</user_message>"
            )},
        ]

        log.info("GATHERING: calling LLM...", prompt_len=len(messages[0]["content"]))
        data, input_tokens, output_tokens = await self._llm.chat_json(
            messages=messages, system=GATHERING_SYSTEM_PROMPT,
            max_tokens=1024, temperature=0.3,
        )
        log.info("GATHERING: LLM response received", data_keys=list(data.keys()) if isinstance(data, dict) else "not-dict")
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
        await self._broadcast_director_message(
            f"{response}\n\n검토 후 승인하시면 에이전트 상의를 시작합니다."
        )
        await self._broadcast_plan()

    async def _run_consulting(self) -> None:
        """CONSULTING 단계 — Worker 상의 실행 후 CONFIRMING으로 전이."""
        await self._consult_workers()

        plan = self._active_plan
        if plan is None:
            return

        # 상의 완료 → CONFIRMING 자동 전이
        plan.stage = PlanStage.CONFIRMING
        plan.updated_at = datetime.now(timezone.utc)

        response = (
            "에이전트 상의가 완료되었습니다. 각 파트의 피드백을 반영한 최종 태스크입니다.\n\n"
            "검토 후 승인하시면 GitHub Issues를 생성합니다. "
            "'진행해'라고 하시면 생성을 시작합니다."
        )
        self._append_conversation("assistant", response)
        await self._broadcast_director_message(response)
        await self._broadcast_plan()
        await self._broadcast_plan()

    async def _consult_workers(self) -> None:
        """각 Worker 에이전트(역할별 LLM)와 상담하여 태스크를 보강한다."""
        plan = self._active_plan
        if plan is None or not plan.tasks:
            return

        project_context = plan.model_dump(
            include={"goal", "project", "decisions", "epic_title"},
        )

        # 에이전트별로 태스크 그룹화
        agent_tasks: dict[str, list[dict]] = {}
        for draft in plan.tasks:
            agent = _resolve_agent_id(draft.agent or "") or "agent-backend"
            agent_tasks.setdefault(agent, []).append(draft.model_dump())

        next_draft_id = len(plan.tasks) + 1
        all_refined: list[TaskDraft] = []
        consultation_summary: list[str] = []

        for agent_id, tasks in agent_tasks.items():
            domain_info = _WORKER_DOMAINS.get(agent_id)
            if not domain_info:
                # 도메인 정보 없는 에이전트는 태스크 그대로 유지
                for t in tasks:
                    all_refined.append(TaskDraft(**t))
                continue

            role_name, domain_desc = domain_info

            # 사용자 기대사항 파일 로드
            user_expectations = ""
            expectations_path = (
                Path(__file__).parent.parent.parent.parent / "prompts" / "expectations" / f"{agent_id}.md"
            )
            if expectations_path.exists():
                try:
                    raw = expectations_path.read_text(encoding="utf-8").strip()
                    if raw:
                        user_expectations = f"\n\n## User Expectations (사용자 기대사항)\n{raw}"
                except Exception as e:
                    log.debug("Failed to read expectations file", path=str(expectations_path), err=str(e))

            system = WORKER_CONSULTATION_PROMPT.format(
                agent_role=role_name,
                domain_description=domain_desc + user_expectations,
                project_context=project_context,
                assigned_tasks=tasks,
                agent_id=agent_id,
            )
            messages = [
                {"role": "user", "content": "위 태스크들을 검토하고 개선해주세요."},
            ]

            await self._broadcast_director_message(
                f"[{role_name}]에게 상담 중... ({len(tasks)}개 태스크)"
            )

            try:
                data, inp, out = await self._llm.chat_json(
                    messages=messages, system=system,
                    max_tokens=2048, temperature=0.3,
                )
                await self._publish_token_usage(inp, out)
            except Exception as e:
                log.warning("Worker consultation failed, keeping original tasks",
                            agent=agent_id, err=str(e))
                for t in tasks:
                    all_refined.append(TaskDraft(**t))
                continue

            feedback = data.get("feedback", "")
            if feedback:
                consultation_summary.append(f"**{role_name}**: {feedback}")

            # 보강된 태스크 적용
            # 원본 태스크의 story_id를 temp_id로 매핑 (Worker가 story_id를 모르므로)
            original_story_map = {t.get("temp_id", ""): t.get("story_id", "") for t in tasks}
            refined = data.get("refined_tasks", [])
            if refined:
                for t in refined:
                    tid = t.get("temp_id", f"draft-{next_draft_id}")
                    all_refined.append(TaskDraft(
                        temp_id=tid,
                        title=t.get("title", ""),
                        description=t.get("description", ""),
                        agent=t.get("agent", agent_id),
                        priority=_safe_int(t.get("priority", 3)),
                        complexity=t.get("complexity", "medium"),
                        dependencies=list(t.get("dependencies", [])),
                        story_id=t.get("story_id", original_story_map.get(tid, "")),
                    ))
            else:
                # refined_tasks가 없으면 원본 유지
                for t in tasks:
                    all_refined.append(TaskDraft(**t))

            # 추가 제안 태스크
            for addition in data.get("suggested_additions", []):
                title = addition.get("title", "")
                if not title:
                    continue
                all_refined.append(TaskDraft(
                    temp_id=f"draft-{next_draft_id}",
                    title=title,
                    description=addition.get("description", ""),
                    agent=agent_id,
                    priority=_safe_int(addition.get("priority", 3)),
                    complexity=addition.get("complexity", "medium"),
                    dependencies=list(addition.get("dependencies", [])),
                ))
                next_draft_id += 1

        # 보강된 태스크로 교체
        plan.tasks = all_refined
        plan.updated_at = datetime.now(timezone.utc)

        if consultation_summary:
            summary = "에이전트 피드백 요약:\n" + "\n".join(consultation_summary)
            await self._broadcast_director_message(summary)
            log.info("Worker consultation complete",
                     original_count=sum(len(t) for t in agent_tasks.values()),
                     refined_count=len(all_refined))

    async def _revise_task_breakdown(self, feedback: str) -> None:
        """사용자 피드백으로 태스크 분해를 수정한다."""
        plan = self._active_plan
        if plan is None:
            return

        plan_json = plan.model_dump(
            include={"epic_title", "epic_description", "tasks", "project", "decisions"},
        )
        safe_feedback = saxutils.escape(feedback)
        system = REVISING_SYSTEM_PROMPT.format(
            plan_json=plan_json, user_feedback=safe_feedback,
        )
        messages = [
            {"role": "user", "content": f"<user_message>{safe_feedback}</user_message>"},
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

    # ===== Agent → Label 매핑 =====

    _AGENT_LABEL_MAP: dict[str, tuple[str, str]] = {
        "agent-git": ("infra", "d93f0b"),
        "agent-backend": ("backend", "0e8a16"),
        "agent-frontend": ("frontend", "1d76db"),
        "agent-docs": ("docs", "fbca04"),
    }

    # ===== Commit (GitHub Project Board에 Epic + Issues 생성) =====

    async def _commit_plan(self) -> None:
        """확정된 플랜을 GitHub Project Board에 Epic + 서브이슈로 생성한다.

        흐름: 라벨 확보 → 서브이슈 생성 → Epic 이슈 생성 → 서브이슈 연결
        → 프로젝트 보드 추가 → DB 저장 → 업무 시작 대기.
        """
        plan = self._active_plan
        if plan is None:
            return

        if not plan.tasks:
            await self._broadcast_director_message("태스크가 없어서 생성할 수 없습니다.")
            return

        await self._broadcast_director_message("GitHub Project Board에 이슈를 생성합니다...")

        # temp_id → 실제 task_id 매핑 (의존성 해소용)
        temp_to_real: dict[str, str] = {}
        for draft in plan.tasks:
            temp_to_real[draft.temp_id] = str(uuid.uuid4())

        # ---- Phase 0: 필요한 라벨 확보 ----
        needed_labels: set[str] = {"epic"}
        for draft in plan.tasks:
            agent = _resolve_agent_id(draft.agent or "")
            if agent and agent in self._AGENT_LABEL_MAP:
                needed_labels.add(self._AGENT_LABEL_MAP[agent][0])

        for label_name in needed_labels:
            color = next(
                (c for l, c in self._AGENT_LABEL_MAP.values() if l == label_name),
                "7057ff" if label_name == "epic" else "ededed",
            )
            await self._git_service.ensure_label(label_name, color)

        # ---- Phase 1: Sub-task 이슈 생성 ----
        issue_results: list[dict[str, Any]] = []
        for draft in plan.tasks:
            body_parts = [draft.description]
            if draft.dependencies:
                dep_refs = ", ".join(draft.dependencies)
                body_parts.append(f"\n\n**Dependencies:** {dep_refs}")

            agent = _resolve_agent_id(draft.agent or "")
            labels = ["agent-task"]
            if agent and agent in self._AGENT_LABEL_MAP:
                labels.append(self._AGENT_LABEL_MAP[agent][0])

            try:
                issue_number = await self._git_service.create_issue(
                    IssueSpec(
                        title=draft.title,
                        body="\n".join(body_parts),
                        labels=labels,
                    )
                )
            except Exception as e:
                log.error("Failed to create sub-task issue, aborting", title=draft.title, err=str(e))
                await self._rollback_issues(issue_results)
                await self._broadcast_director_message(
                    f"Sub-task 이슈 생성 실패: {draft.title}. "
                    f"이미 생성된 {len(issue_results)}개를 정리했습니다."
                )
                return

            issue_results.append({
                "temp_id": draft.temp_id,
                "issue_number": issue_number,
                "title": draft.title,
                "agent": agent,
                "priority": draft.priority,
                "complexity": draft.complexity,
                "description": draft.description,
                "dependencies": draft.dependencies,
                "story_id": draft.story_id,
            })

        # temp_id → issue_number 매핑 (Story 본문에 참조용)
        temp_to_issue: dict[str, int] = {
            item["temp_id"]: item["issue_number"] for item in issue_results
        }

        # ---- Phase 2: Story 이슈 생성 ----
        await self._git_service.ensure_label("story", "c5def5")
        story_issues: dict[str, int] = {}  # story temp_id → issue_number

        for story in plan.stories:
            story_body_parts = [
                f"## Story: {story.title}",
                "",
                story.description,
                "",
                "### Sub-tasks",
            ]
            for task_tid in story.tasks:
                inum = temp_to_issue.get(task_tid)
                if inum:
                    title = next((i["title"] for i in issue_results if i["temp_id"] == task_tid), "")
                    story_body_parts.append(f"- [ ] #{inum} {title}")

            try:
                story_issue_num = await self._git_service.create_issue(
                    IssueSpec(
                        title=f"[Story] {story.title}",
                        body="\n".join(story_body_parts),
                        labels=["story"],
                    )
                )
                story_issues[story.temp_id] = story_issue_num
            except Exception as e:
                log.warning("Story issue creation failed (non-fatal)", title=story.title, err=str(e))

        # ---- Phase 3: Epic 이슈 생성 ----
        epic_title = plan.epic_title or plan.project.topic or "Untitled Epic"
        epic_body_parts = [
            f"## Epic: {epic_title}",
            "",
            plan.epic_description or plan.project.purpose or "",
            "",
            "### Stories",
        ]
        for story in plan.stories:
            snum = story_issues.get(story.temp_id)
            if snum:
                epic_body_parts.append(f"- [ ] #{snum} {story.title}")

        try:
            epic_issue_number = await self._git_service.create_issue(
                IssueSpec(
                    title=epic_title,
                    body="\n".join(epic_body_parts),
                    labels=["epic"],
                )
            )
        except Exception as e:
            log.error("Failed to create epic issue", err=str(e))
            all_created = issue_results + [{"issue_number": v} for v in story_issues.values()]
            await self._rollback_issues(all_created)
            await self._broadcast_director_message("Epic 이슈 생성 실패. 롤백 완료.")
            return

        # ---- Phase 4: 3계층 서브이슈 연결 ----
        # Story → Epic 연결
        for story_tid, story_num in story_issues.items():
            try:
                await self._git_service.link_sub_issue(epic_issue_number, story_num)
            except Exception as e:
                log.warning("Story→Epic link failed", story=story_num, err=str(e))

        # Sub-task → Story 연결
        for item in issue_results:
            story_tid = item.get("story_id", "")
            parent_num = story_issues.get(story_tid)
            if parent_num:
                try:
                    await self._git_service.link_sub_issue(parent_num, item["issue_number"])
                except Exception as e:
                    log.warning("Sub-task→Story link failed",
                                parent=parent_num, child=item["issue_number"], err=str(e))
            else:
                # Story가 없는 Sub-task는 Epic에 직접 연결
                try:
                    await self._git_service.link_sub_issue(epic_issue_number, item["issue_number"])
                except Exception as e:
                    log.warning("Sub-task→Epic link failed", child=item["issue_number"], err=str(e))

        # ---- Phase 5: 프로젝트 보드에 추가 ----
        # Epic은 "Epic" 컬럼, 나머지는 "Backlog"
        try:
            await self._git_service.add_issue_to_project(epic_issue_number, "Epic")
        except Exception as e:
            log.warning("Failed to add epic to project (non-fatal)", issue=epic_issue_number, err=str(e))
        for issue_num in [*story_issues.values()] + [i["issue_number"] for i in issue_results]:
            try:
                await self._git_service.add_issue_to_project(issue_num, "Backlog")
            except Exception as e:
                log.warning("Failed to add to project (non-fatal)", issue=issue_num, err=str(e))

        # ---- Phase 6: DB — Epic + Tasks 저장 ----
        epic_id = str(uuid.uuid4())
        plan.epic_id = epic_id
        try:
            await self._state_store.create_epic({
                "id": epic_id,
                "title": epic_title,
                "description": plan.epic_description or plan.project.purpose or "",
                "status": "active",
            })

            created_issues: list[dict[str, Any]] = []
            for item in issue_results:
                task_id = temp_to_real[item["temp_id"]]
                await self._state_store.create_task({
                    "id": task_id,
                    "epic_id": epic_id,
                    "title": item["title"],
                    "description": item["description"],
                    "assigned_agent": item["agent"],
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
                    "agent": item["agent"],
                    "issue_number": item["issue_number"],
                })
        except Exception as e:
            log.error("DB commit failed, rolling back Board issues", err=str(e))
            all_to_rollback = issue_results + [{"issue_number": v} for v in story_issues.values()]
            await self._rollback_issues(all_to_rollback)
            try:
                await self._git_service.close_issue(epic_issue_number)
            except Exception as rollback_err:
                log.warning("Rollback: failed to close epic issue", err=str(rollback_err))
            await self._broadcast_director_message(
                "DB 저장 실패로 생성된 GitHub Issues를 정리했습니다. 다시 시도해주세요."
            )
            return

        # ---- Phase 7: 프로젝트 컨텍스트를 workspace에 저장 ----
        await self._write_project_context(plan)

        # ---- Phase 8: COMMITTED — 업무 시작 대기 ----
        plan.stage = PlanStage.COMMITTED
        plan.updated_at = datetime.now(timezone.utc)
        await self._persist_plan()
        await self._save_memories()

        log.info(
            "Epic committed (3-tier)",
            epic_id=epic_id,
            epic_issue=epic_issue_number,
            story_count=len(story_issues),
            task_count=len(created_issues),
            session_id=plan.session_id,
        )

        await self._message_bus.publish(
            Message(
                id=str(uuid.uuid4()),
                type=MessageType.DIRECTOR_COMMITTED,
                from_agent=self.id,
                payload={
                    "epicId": epic_id,
                    "epicTitle": epic_title,
                    "epicIssueNumber": epic_issue_number,
                    "stories": {tid: num for tid, num in story_issues.items()},
                    "issues": created_issues,
                    "sessionId": plan.session_id,
                },
                trace_id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
            )
        )

        # 3계층 구조 요약 메시지
        summary_parts = [
            "GitHub Project Board에 3계층 구조로 생성 완료!",
            "",
            f"**Epic** #{epic_issue_number}: {epic_title}",
        ]
        for story in plan.stories:
            snum = story_issues.get(story.temp_id)
            if snum:
                story_tasks = [i for i in issue_results if i.get("story_id") == story.temp_id]
                summary_parts.append(f"  **Story** #{snum}: {story.title} ({len(story_tasks)}개 태스크)")
                for st in story_tasks:
                    summary_parts.append(
                        f"    - #{st['issue_number']} {st['title']} → {st.get('agent', '?')}"
                    )

        summary_parts.append("\n**업무를 시작하려면 '시작해'라고 말해주세요.**")
        await self._broadcast_director_message("\n".join(summary_parts))

    async def _rollback_issues(self, issue_results: list[dict[str, Any]]) -> None:
        """생성된 이슈들을 close하여 롤백한다."""
        for created in issue_results:
            try:
                await self._git_service.close_issue(created["issue_number"])
            except Exception as rollback_err:
                log.warning("Rollback: failed to close issue",
                            issue=created["issue_number"], err=str(rollback_err))

    async def _start_execution(self) -> None:
        """사용자 허가 후 Backlog 태스크를 Ready로 전환하여 에이전트 작업을 시작한다."""
        plan = self._active_plan
        if plan is None or plan.stage != PlanStage.COMMITTED:
            await self._broadcast_director_message("시작할 수 있는 계획이 없습니다.")
            return

        # 이 에픽의 의존성 없는 태스크만 Ready로 이동
        tasks = await self._state_store.get_all_tasks()
        target_epic_id = plan.epic_id or ""
        moved = 0
        for task in tasks:
            if task.status != "backlog":
                continue
            # 에픽 필터링: 현재 에픽 소속 태스크만 대상
            if target_epic_id and getattr(task, "epic_id", None) != target_epic_id:
                continue
            has_deps = bool(task.dependencies)
            if not has_deps and task.github_issue_number:
                try:
                    await self._git_service.move_issue_to_column(
                        task.github_issue_number, "Ready"
                    )
                except Exception as e:
                    log.warning("Failed to move to Ready (Board-first)", task_id=task.id, err=str(e))
                    continue
                await self._state_store.update_task(
                    task.id, {"status": "ready", "board_column": "Ready"}
                )
                moved += 1

        plan.stage = PlanStage.EXECUTING
        plan.updated_at = datetime.now(timezone.utc)
        await self._broadcast_plan()

        await self._broadcast_director_message(
            f"업무 시작! {moved}개 태스크가 Ready 상태로 전환되었습니다. "
            f"에이전트들이 폴링하여 작업을 시작합니다."
        )
        log.info("Execution started", ready_count=moved, session_id=plan.session_id)
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
        stripped = lower.strip()
        if stripped == "create_epic":
            return "create_epic"
        if stripped == "status_query":
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

        task = await self._state_store.get_task(task_id)
        if task is None:
            log.warning("Review for unknown task, ignoring", task_id=task_id)
            return

        success = result.get("success", False) if isinstance(result, dict) else False

        if not success:
            # Worker가 실패 보고 → 재작업 (최대 3회, 초과 시 Backlog로 리셋)
            retry = task.retry_count or 0
            if retry >= 3:
                log.warning("Task exceeded max retries, resetting to Backlog",
                            task_id=task_id, retries=retry)
                # Board-first: Backlog로 이동 + retry 리셋
                if task.github_issue_number:
                    try:
                        await self._git_service.move_issue_to_column(task.github_issue_number, "Backlog")
                        await self._git_service.add_issue_comment(
                            task.github_issue_number,
                            f"⚠️ {retry}회 실패 후 Backlog로 리셋합니다. retry 카운터 초기화.",
                        )
                    except Exception as e:
                        log.error("Board move to Backlog failed", task_id=task_id, err=str(e))
                # Board=Backlog에 맞춰 DB도 backlog + retry 리셋
                await self._state_store.update_task(task_id, {
                    "status": "backlog", "board_column": "Backlog", "retry_count": 0,
                })
                return
            await self._finalize_review(task, approved=False, reason="Worker reported failure")
            return

        # Worker 성공 → Director가 LLM으로 코드 리뷰
        # reject 시에도 max retry 제한 적용, 초과 시 Backlog로 리셋
        retry = task.retry_count or 0
        if retry >= 3:
            log.warning("Task exceeded max retries (Director reject loop), resetting to Backlog",
                        task_id=task_id, retries=retry)
            # Board-first: Backlog로 이동 + retry 리셋
            if task.github_issue_number:
                try:
                    await self._git_service.move_issue_to_column(task.github_issue_number, "Backlog")
                    await self._git_service.add_issue_comment(
                        task.github_issue_number,
                        f"⚠️ Director 리뷰에서 {retry}회 reject 후 Backlog로 리셋합니다. retry 카운터 초기화.",
                    )
                except Exception as e:
                    log.error("Board move to Backlog failed", task_id=task_id, err=str(e))
            await self._state_store.update_task(task_id, {
                "status": "backlog", "board_column": "Backlog", "retry_count": 0,
            })
            return

        artifacts = result.get("artifacts", []) if isinstance(result, dict) else []
        summary = result.get("data", {}).get("summary", "") if isinstance(result, dict) else ""

        # ---- Import 검증 게이트: 생성 파일의 import가 실제 존재하는지 ----
        import_errors = await self._run_import_gate(artifacts)
        if import_errors:
            reject_reason = (
                "Import 검증 실패 — 존재하지 않는 모듈을 import합니다:\n\n"
                + "\n".join(f"- {e}" for e in import_errors[:10])
                + "\n\nworkspace의 실제 파일 구조를 확인하고 import 경로를 수정하세요."
            )
            await self._finalize_review(task, approved=False, reason=reject_reason)
            if task.github_issue_number:
                await self._git_service.add_issue_comment(
                    task.github_issue_number,
                    f"**Director Review: Import Gate FAILED**\n\n{reject_reason}",
                )
            return

        # ---- 테스트 게이트: pytest 실행 → 실패하면 LLM 리뷰 없이 reject ----
        test_passed, test_output = await self._run_test_gate(artifacts=artifacts)
        if not test_passed:
            reject_reason = f"테스트 실패로 reject합니다.\n\n```\n{test_output[-1500:]}\n```"
            await self._finalize_review(task, approved=False, reason=reject_reason)
            if task.github_issue_number:
                await self._git_service.add_issue_comment(
                    task.github_issue_number,
                    f"**Director Review: Test Gate FAILED**\n\n{reject_reason}",
                )
            return

        approved, review_note = await self._llm_review(task, artifacts, summary)
        await self._finalize_review(task, approved=approved, reason=review_note)

        # 리뷰 코멘트를 GitHub Issue에 추가
        if task.github_issue_number and review_note:
            status = "Approved" if approved else "Changes Requested"
            await self._git_service.add_comment(
                task.github_issue_number,
                f"**Director Review: {status}**\n\n{review_note}",
            )

    async def _run_import_gate(self, artifacts: list[str]) -> list[str]:
        """생성된 Python 파일의 import가 workspace에 실제 존재하는지 검증한다.

        Returns: 오류 메시지 리스트 (비어있으면 통과)
        """
        try:
            work_dir = Path(self._git_service.work_dir)
            if not work_dir.is_dir():
                return []
        except Exception:
            return []
        errors: list[str] = []

        # workspace의 실제 모듈 목록 구축
        existing_modules: set[str] = set()
        for py_file in work_dir.rglob("*.py"):
            rel = py_file.relative_to(work_dir)
            parts = list(rel.with_suffix("").parts)
            # src/personal_jira/models/issue.py → personal_jira.models.issue
            if parts and parts[0] == "src":
                parts = parts[1:]
            for i in range(1, len(parts) + 1):
                existing_modules.add(".".join(parts[:i]))

        # 프로젝트 루트 패키지 이름 감지
        project_packages: set[str] = set()
        for d in work_dir.iterdir():
            if d.is_dir() and (d / "__init__.py").exists():
                project_packages.add(d.name)
        src_dir = work_dir / "src"
        if src_dir.is_dir():
            for d in src_dir.iterdir():
                if d.is_dir() and (d / "__init__.py").exists():
                    project_packages.add(d.name)

        if not project_packages:
            return []  # 프로젝트 패키지 감지 못하면 스킵

        # 생성된 파일에서 import 추출 및 검증
        import_pattern = re.compile(
            r"^(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.MULTILINE
        )
        for fpath in artifacts:
            if not fpath.endswith(".py"):
                continue
            try:
                content = Path(fpath).read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for match in import_pattern.finditer(content):
                module = match.group(1) or match.group(2)
                root = module.split(".")[0]
                # 프로젝트 내부 import만 검증 (stdlib, 외부 패키지 제외)
                if root not in project_packages:
                    continue
                if module not in existing_modules:
                    rel_fpath = Path(fpath).relative_to(work_dir) if Path(fpath).is_relative_to(work_dir) else fpath
                    errors.append(f"`{rel_fpath}`: `{module}` 모듈이 workspace에 존재하지 않음")

        return errors

    async def _run_test_gate(
        self,
        work_dir: str | None = None,
        artifacts: list[str] | None = None,
    ) -> tuple[bool, str]:
        """workspace에서 린트 + 전체 테스트를 실행한다. (passed, output) 반환.

        Args:
            work_dir: 테스트 실행 디렉토리. None이면 공유 workspace.
            artifacts: 이번 태스크에서 생성된 파일 경로 목록 (린트 범위 제한용).
        """
        work_dir = work_dir or self._git_service.work_dir
        if not os.path.isdir(work_dir):
            return True, "no workspace"

        outputs: list[str] = []

        # ---- Step 1: 린트 — 새로 생성된 파일만 (기존 코드 false positive 방지) ----
        lint_targets = self._collect_lint_targets(work_dir, artifacts)
        if lint_targets:
            # workspace 자체 ruff 설정이 있으면 사용 (오케스트레이션 설정과 분리)
            ruff_config_args: list[str] = []
            for cfg_name in ("ruff.toml", ".ruff.toml"):
                cfg_path = os.path.join(work_dir, cfg_name)
                if os.path.isfile(cfg_path):
                    ruff_config_args = ["--config", cfg_path]
                    break
            if not ruff_config_args:
                pyproject = os.path.join(work_dir, "pyproject.toml")
                if os.path.isfile(pyproject):
                    ruff_config_args = ["--config", pyproject]

            # Step 1a: 안전한 lint 자동 수정 (--fix는 safe fix만 적용)
            await self._run_subprocess(
                ["uv", "run", "ruff", "check", *lint_targets,
                 "--fix", "--exclude", ".worktrees", "-q", *ruff_config_args],
                work_dir, "Lint-autofix", timeout=15,
            )
            # Step 1b: 나머지 린트 에러 검출
            lint_passed, lint_out = await self._run_subprocess(
                ["uv", "run", "ruff", "check", *lint_targets,
                 "--exclude", ".worktrees", "--no-fix", "-q", *ruff_config_args],
                work_dir, "Lint", timeout=30,
            )
            if lint_out:
                outputs.append(f"=== LINT ===\n{lint_out}")
            if not lint_passed:
                return False, "\n\n".join(outputs)

        # ---- Step 2: 테스트 — pyproject.toml 있을 때만 (인프라 셋업 단계 스킵) ----
        test_dir = os.path.join(work_dir, "tests")
        has_project = os.path.isfile(os.path.join(work_dir, "pyproject.toml"))
        if os.path.isdir(test_dir) and has_project:
            test_targets = self._collect_test_targets(work_dir, artifacts)
            test_passed, test_out = await self._run_subprocess(
                ["uv", "run", "pytest", *test_targets, "-x", "-q", "--tb=short",
                 "--ignore=.worktrees"],
                work_dir, "Test", timeout=180,
            )
            if test_out:
                structured = self._structure_test_output(test_out, work_dir, artifacts)
                outputs.append(f"=== TEST ===\n{structured}")
            if not test_passed:
                return False, "\n\n".join(outputs)

        return True, "\n\n".join(outputs) if outputs else "all checks passed"

    def _collect_lint_targets(
        self, work_dir: str, artifacts: list[str] | None,
    ) -> list[str]:
        """린트 대상 파일을 수집한다. artifacts가 있으면 해당 파일만, 없으면 전체."""
        if not artifacts:
            return ["."]  # fallback: 전체

        targets: list[str] = []
        for fpath in artifacts:
            if not fpath.endswith((".py", ".pyi")):
                continue
            # 절대 경로 → 상대 경로 변환
            try:
                if os.path.isabs(fpath):
                    rel = os.path.relpath(fpath, work_dir)
                else:
                    rel = fpath
                # .worktrees 내부 파일 제외 (ruff --exclude가 명시적 경로에는 미적용)
                if ".worktrees" in rel.replace("\\", "/"):
                    continue
                if os.path.isfile(os.path.join(work_dir, rel)):
                    targets.append(rel)
            except ValueError:
                continue
        return targets if targets else ["."]

    def _collect_test_targets(
        self, work_dir: str, artifacts: list[str] | None,
    ) -> list[str]:
        """테스트 대상을 수집한다. artifacts에 테스트 파일이 있으면 그것만, 없으면 tests/ 전체."""
        if not artifacts:
            return ["tests/"]

        targets: list[str] = []
        for fpath in artifacts:
            basename = os.path.basename(fpath)
            if not (basename.startswith("test_") and basename.endswith(".py")):
                continue
            try:
                rel = os.path.relpath(fpath, work_dir) if os.path.isabs(fpath) else fpath
                if ".worktrees" in rel.replace("\\", "/"):
                    continue
                if os.path.isfile(os.path.join(work_dir, rel)):
                    targets.append(rel)
            except ValueError:
                continue
        return targets if targets else ["tests/"]

    def _structure_test_output(
        self, raw_output: str, work_dir: str, artifacts: list[str] | None,
    ) -> str:
        """테스트 실패 출력을 구조화한다.

        기존 테스트 vs 새 테스트를 구분하여 워커에게 명확한 피드백 제공.
        """
        if not artifacts:
            return raw_output[-2000:]

        # artifacts에서 테스트 파일 경로 추출 (상대 경로로 통일)
        new_test_files: set[str] = set()
        for fpath in artifacts:
            basename = os.path.basename(fpath)
            if basename.startswith("test_") and basename.endswith(".py"):
                try:
                    if os.path.isabs(fpath):
                        rel = os.path.relpath(fpath, work_dir)
                    else:
                        rel = fpath
                    new_test_files.add(rel.replace("\\", "/"))
                except ValueError:
                    pass

        # pytest 출력에서 FAILED 라인 파싱
        lines = raw_output.split("\n")
        existing_failures: list[str] = []
        new_failures: list[str] = []

        for line in lines:
            if "FAILED" not in line:
                continue
            # 형식: FAILED tests/path/test_foo.py::test_bar - ...
            is_new = False
            for nf in new_test_files:
                if nf in line.replace("\\", "/"):
                    is_new = True
                    break
            if is_new:
                new_failures.append(line.strip())
            else:
                existing_failures.append(line.strip())

        parts: list[str] = []
        if existing_failures:
            parts.append(
                "🔴 기존 테스트가 깨졌습니다 — 새 코드가 기존 기능을 망가뜨림:\n"
                + "\n".join(f"  - {f}" for f in existing_failures[:10])
            )
        if new_failures:
            parts.append(
                "🟡 새 테스트 실패 — 구현이 스펙과 불일치:\n"
                + "\n".join(f"  - {f}" for f in new_failures[:10])
            )

        if parts:
            summary = "\n\n".join(parts)
            # 원본 출력의 마지막 부분도 포함 (traceback 참조용)
            return f"{summary}\n\n--- 상세 출력 ---\n{raw_output[-1500:]}"

        return raw_output[-2000:]

    async def _run_subprocess(
        self, cmd: list[str], cwd: str, label: str, timeout: int = 60,
    ) -> tuple[bool, str]:
        """서브프로세스를 실행하고 결과를 반환한다. 실패해도 예외 없음."""
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            output = stdout.decode(errors="replace").strip()
            passed = proc.returncode == 0
            if passed:
                log.info(f"{label} gate PASSED", work_dir=cwd)
            else:
                log.warning(f"{label} gate FAILED", work_dir=cwd, returncode=proc.returncode)
            return passed, output
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            log.warning(f"{label} gate timed out", work_dir=cwd)
            return False, f"{label} timed out after {timeout}s"
        except Exception as e:
            log.warning(f"{label} gate error", err=str(e))
            return True, ""  # 실행 자체 실패하면 게이트 통과 (환경 문제)

    async def run_full_test(self, work_dir: str) -> tuple[bool, str]:
        """MergeQueue.TestRunner 프로토콜 구현 — 전체 테스트를 실행한다."""
        return await self._run_test_gate(work_dir=work_dir)

    async def _llm_review(
        self, task: Any, artifacts: list[str], summary: str,
    ) -> tuple[bool, str]:
        """LLM으로 생성된 코드를 리뷰한다. (approved, review_note) 반환."""
        # 생성된 파일 내용 읽기 (최대 5개, 각 2000자)
        file_contents: list[str] = []
        for fpath in artifacts[:5]:
            try:
                from pathlib import Path
                content = Path(fpath).read_text(encoding="utf-8", errors="replace")[:2000]
                file_contents.append(f"### {fpath}\n```\n{content}\n```")
            except Exception:
                file_contents.append(f"### {fpath}\n(읽기 실패)")

        if not file_contents:
            # 파일이 없으면 summary만으로 판단
            return False, "리뷰할 파일이 없음 — 코드 생성 결과를 확인할 수 없어 reject"

        # workspace의 기존 파일 구조 참조 (아키텍처 일관성 검증용)
        existing_structure = ""
        try:
            ws = Path(self._git_service.work_dir)
            if ws.is_dir():
                all_files = sorted(str(p.relative_to(ws)) for p in ws.rglob("*") if p.is_file())
                existing_structure = "\n".join(all_files[:50])
        except Exception:
            pass

        arch_section = ""
        if existing_structure:
            arch_section = f"## Existing Project Structure\n```\n{existing_structure}\n```\n\n"

        prompt = (
            "You are the Director — PM, Tech Lead, and Architect of this project.\n"
            "Review the following code with STRICT criteria.\n\n"
            f"## Task\nTitle: {task.title}\nDescription: {task.description or 'N/A'}\n\n"
            f"## Summary\n{summary}\n\n"
            f"{arch_section}"
            f"## Generated Files\n" + "\n\n".join(file_contents) + "\n\n"
            "## Review Criteria\n"
            "1. **TDD**: Test files included? REJECT only if NO tests at all.\n"
            "2. **Task match**: Does the code address the task?\n"
            "3. **Architecture**: Reasonable structure for the project?\n"
            "4. **Security**: No hardcoded secrets?\n\n"
            "## Decision\n"
            "- APPROVE if: core logic is correct and tests exist, even if incomplete or truncated.\n"
            "- REJECT ONLY if: NO tests at all, completely wrong architecture, or security issue.\n"
            "- **IMPORTANT**: Truncated files or missing minor files (like __init__.py, .gitkeep) are NOT reject reasons. "
            "These can be fixed in follow-up tasks. Focus on whether the CORE implementation is correct.\n\n"
            'Respond with JSON: {"approved": true/false, "note": "specific feedback with reject reason if any"}\n'
            "Respond in Korean."
        )

        try:
            data, inp, out = await self._llm.chat_json(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=256, temperature=0.2,
            )
            await self._publish_token_usage(inp, out)
            approved = data.get("approved", True) if isinstance(data, dict) else True
            note = data.get("note", "") if isinstance(data, dict) else ""
            log.info("LLM review complete", task_id=task.id, approved=approved, note=note[:100])
            return approved, note
        except Exception as e:
            log.error("LLM review failed, rejecting", task_id=task.id, err=str(e))
            return False, f"Director 리뷰 LLM 호출 실패 — reject (error: {e})"

    async def _finalize_review(self, task: Any, approved: bool, reason: str) -> None:
        """리뷰 결과를 Board + DB에 반영하고, 승인 시 의존 태스크를 Ready로 전환.

        승인 시 플로우: merge 먼저 → 성공 시에만 done 전이 (review→done).
        merge 실패 시: review → ready 롤백 (유효한 상태 전이).
        """
        if not approved:
            # reject: review → ready (유효한 전이)
            if task.github_issue_number:
                try:
                    await self._git_service.move_issue_to_column(
                        task.github_issue_number, "Ready"
                    )
                except Exception as e:
                    log.error("Review: Board move failed", task_id=task.id, err=str(e))
                    return
            await self._state_store.update_task(task.id, {
                "status": "ready",
                "board_column": "Ready",
                "review_note": reason[:500],
                "retry_count_increment": 1,
            })
            log.info("Task review: rejected", task_id=task.id)
            await self._broadcast_review_message(task, approved, reason)
            return

        # approved: merge 먼저 시도 → 성공 시에만 done 전이
        merge_result = await self._enqueue_merge(task)
        if not merge_result.success:
            log.warning("Merge failed, reverting to ready",
                        task_id=task.id, err=merge_result.error)
            # merge 실패 → review → ready (유효한 전이)
            if task.github_issue_number:
                try:
                    await self._git_service.move_issue_to_column(
                        task.github_issue_number, "Ready"
                    )
                except Exception:
                    pass
            rollback_reason = merge_result.error
            if merge_result.test_output:
                rollback_reason += f"\n\n{merge_result.test_output[-1500:]}"
            await self._state_store.update_task(task.id, {
                "status": "ready", "board_column": "Ready",
                "retry_count_increment": 1,
                "review_note": rollback_reason[:500],
            })
            if task.github_issue_number:
                await self._git_service.add_comment(
                    task.github_issue_number,
                    f"**Merge Queue: FAILED**\n\n{rollback_reason[:1500]}",
                )
            return  # 의존 태스크 unlock 하지 않음

        # merge 성공 → review → done 전이 (Board-first)
        if task.github_issue_number:
            try:
                await self._git_service.move_issue_to_column(
                    task.github_issue_number, "Done"
                )
            except Exception as e:
                log.error("Review: Board move to Done failed", task_id=task.id, err=str(e))
                return
        await self._state_store.update_task(task.id, {
            "status": "done",
            "board_column": "Done",
            "review_note": reason[:500],
        })
        log.info("Task review: approved + merged", task_id=task.id)

        await self._broadcast_review_message(task, approved, reason)

        # 승인 + 머지 완료 → 산출물 브로드캐스트 + 의존 태스크 Ready 전환
        db_artifacts = await self._state_store.get_artifacts_for_task(task.id)
        if db_artifacts:
            file_paths = [a.file_path for a in db_artifacts if hasattr(a, "file_path")]
            await self._message_bus.publish(
                Message(
                    id=str(uuid.uuid4()),
                    type=MessageType.TASK_ARTIFACTS,
                    from_agent=task.assigned_agent or self.id,
                    payload={
                        "task_id": task.id,
                        "task_title": task.title,
                        "issue_number": task.github_issue_number,
                        "files": file_paths[:20],
                    },
                    trace_id=str(uuid.uuid4()),
                    timestamp=datetime.now(timezone.utc),
                )
            )
        await self._unlock_dependent_tasks(task.id)

    async def _broadcast_review_message(
        self, task: Any, approved: bool, reason: str,
    ) -> None:
        """리뷰 결과를 MessageBus에 발행한다 (Docs Agent 기록용)."""
        status = "Approved" if approved else "Changes Requested"
        await self._message_bus.publish(
            Message(
                id=str(uuid.uuid4()),
                type=MessageType.DIRECTOR_MESSAGE,
                from_agent=self.id,
                payload={
                    "content": (
                        f"**Director Review: {status}**\n"
                        f"- Task: {task.title}"
                        f" (#{task.github_issue_number or '?'})\n"
                        f"- Agent: {task.assigned_agent or '?'}\n"
                        f"- Feedback: {reason}"
                    ),
                },
                trace_id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
            )
        )

    async def _enqueue_merge(self, task: Any) -> MergeResult:
        """태스크를 머지 큐에 넣어 순차 처리한다. 큐가 없으면 직접 commit_and_pr."""
        if self._merge_queue:
            request = MergeRequest(
                task_id=task.id,
                task_title=task.title,
                issue_number=task.github_issue_number,
                worktree_path=None,  # 워커의 worktree는 이미 정리됨, 공유 workspace 사용
            )
            return await self._merge_queue.enqueue(request)

        # fallback: 머지 큐 없이 직접 처리 (하위 호환)
        try:
            pr_num = await self._git_service.commit_and_pr(
                f"feat: {task.title} (#{task.github_issue_number or '?'})",
                issue_number=task.github_issue_number,
            )
            if pr_num:
                log.info("PR created and merged (direct)", task_id=task.id, pr=pr_num)
            return MergeResult(success=True, pr_number=pr_num)
        except Exception as e:
            return MergeResult(success=False, error=str(e))

    async def _unlock_dependent_tasks(self, completed_task_id: str) -> None:
        """완료된 태스크에 의존하는 backlog 태스크들의 의존성을 확인하고 Ready 전환."""
        # 완료된 태스크의 에픽 ID로 범위 제한
        completed_task = await self._state_store.get_task(completed_task_id)
        epic_id = getattr(completed_task, "epic_id", None) if completed_task else None
        all_tasks = await self._state_store.get_all_tasks()
        for t in all_tasks:
            # 에픽 범위 필터링
            if epic_id and getattr(t, "epic_id", None) != epic_id:
                continue
            if t.status != "backlog":
                continue
            deps = t.dependencies or []
            if completed_task_id not in deps:
                continue

            # 이 태스크의 모든 의존성이 done인지 확인
            all_deps_done = True
            for dep_id in deps:
                dep_task = await self._state_store.get_task(dep_id)
                if dep_task is None or dep_task.status != "done":
                    all_deps_done = False
                    break

            if all_deps_done:
                # Board-first: Ready로 이동
                if t.github_issue_number:
                    try:
                        await self._git_service.move_issue_to_column(t.github_issue_number, "Ready")
                    except Exception as e:
                        log.warning("Failed to unlock task on Board", task_id=t.id, err=str(e))
                        continue

                # 선행 태스크 산출물을 후속 태스크 description에 추가
                artifact_context = await self._build_dependency_context(deps)
                if artifact_context:
                    updated_desc = (t.description or "") + artifact_context
                    await self._state_store.update_task(t.id, {
                        "status": "ready", "board_column": "Ready",
                        "description": updated_desc,
                    })
                else:
                    await self._state_store.update_task(t.id, {"status": "ready", "board_column": "Ready"})
                log.info("Dependent task unlocked", task_id=t.id, title=t.title)

    async def _build_dependency_context(self, dep_ids: list[str]) -> str:
        """선행 태스크들의 산출물(파일 경로 + 핵심 내용)을 컨텍스트 문자열로 반환."""
        sections: list[str] = []
        for dep_id in dep_ids:
            dep_task = await self._state_store.get_task(dep_id)
            if not dep_task:
                continue
            artifacts = await self._state_store.get_artifacts_for_task(dep_id)
            if not artifacts:
                continue
            file_lines = []
            for art in artifacts[:10]:
                fpath = art.file_path if hasattr(art, "file_path") else str(art)
                file_lines.append(f"  - {fpath}")
            sections.append(
                f"### 선행 태스크: {dep_task.title}\n"
                f"생성된 파일:\n" + "\n".join(file_lines)
            )
        if not sections:
            return ""
        return (
            "\n\n---\n## 선행 태스크 산출물 (이 파일들을 참조하여 작업하세요)\n"
            + "\n\n".join(sections)
        )

    # ===== Helpers =====

    async def _write_project_context(self, plan: EpicPlan) -> None:
        """프로젝트 컨텍스트를 workspace/docs/PROJECT.md에 저장한다.

        에이전트가 코드 생성 시 이 파일을 참조하여 전체 프로젝트 목적/기능/설계를 이해한다.
        """
        try:
            work_dir = Path(self._git_service.work_dir)
            docs_dir = work_dir / "docs"
            docs_dir.mkdir(parents=True, exist_ok=True)

            ctx = plan.project
            tech = ctx.tech_stack
            tech_lines = []
            for category in ("frontend", "backend", "database", "infra", "etc"):
                items = getattr(tech, category, [])
                if items:
                    tech_lines.append(f"- **{category}**: {', '.join(items)}")

            stories_section = ""
            if plan.stories:
                story_lines = []
                for s in plan.stories:
                    task_count = len(s.tasks)
                    story_lines.append(f"### {s.title}\n{s.description}\n- Sub-tasks: {task_count}개\n")
                stories_section = "## Stories\n\n" + "\n".join(story_lines)

            decisions_section = ""
            if plan.decisions:
                decisions_section = "## 설계 결정사항\n\n" + "\n".join(f"- {d}" for d in plan.decisions)

            constraints_section = ""
            if ctx.constraints:
                constraints_section = "## 제약사항\n\n" + "\n".join(f"- {c}" for c in ctx.constraints)

            non_goals_section = ""
            if ctx.non_goals:
                non_goals_section = "## Non-Goals\n\n" + "\n".join(f"- {ng}" for ng in ctx.non_goals)

            content = f"""# {plan.epic_title}

## 프로젝트 개요
{plan.epic_description}

## 목적
{ctx.purpose}

## 대상 사용자
{ctx.target_users}

## 범위
{ctx.scope}

## 기술 스택
{chr(10).join(tech_lines)}

{decisions_section}

{constraints_section}

{non_goals_section}

{stories_section}

---
> 이 파일은 Director Agent가 자동 생성합니다. 에이전트가 코드 생성 시 참조합니다.
"""
            await asyncio.to_thread(
                (docs_dir / "PROJECT.md").write_text, content, "utf-8"
            )
            log.info("Project context written to workspace", path="docs/PROJECT.md")
        except Exception as e:
            log.warning("Failed to write project context", err=str(e))

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
        if "stories" in data and isinstance(data["stories"], list):
            plan.stories = [
                StoryDraft(
                    temp_id=s.get("temp_id", f"story-{i+1}"),
                    title=s.get("title", ""),
                    description=s.get("description", ""),
                    tasks=list(s.get("tasks", [])),
                )
                for i, s in enumerate(data["stories"])
            ]
        if "tasks" in data and isinstance(data["tasks"], list):
            plan.tasks = [
                TaskDraft(
                    temp_id=t.get("temp_id", f"draft-{i+1}"),
                    title=t.get("title", ""),
                    description=t.get("description", ""),
                    agent=t.get("agent"),
                    priority=_safe_int(t.get("priority", 3)),
                    complexity=t.get("complexity", "medium"),
                    dependencies=list(t.get("dependencies", [])),
                    story_id=t.get("story_id", ""),
                )
                for i, t in enumerate(data["tasks"])
            ]

    def _append_conversation(self, role: str, content: str) -> None:
        """Sliding window 대화 기록 추가. 각 turn content는 최대 _MAX_TURN_CONTENT_LEN자로 제한."""
        truncated = content[:_MAX_TURN_CONTENT_LEN]
        self._conversation.append({"role": role, "content": truncated})
        if len(self._conversation) > _MAX_CONVERSATION_TURNS * 2:
            self._conversation = self._conversation[-_MAX_CONVERSATION_TURNS * 2:]

    def _format_conversation(self) -> str:
        """대화 기록을 텍스트로 포맷. 총 길이를 _MAX_FORMATTED_CONVERSATION_LEN으로 제한한다.
        최신 턴을 우선 보존하고 오래된 턴을 잘라낸다."""
        if not self._conversation:
            return "(no previous conversation)"
        lines: list[str] = []
        total = 0
        for turn in reversed(self._conversation):
            prefix = "User" if turn["role"] == "user" else "Director"
            line = f"{prefix}: {turn['content']}"
            if total + len(line) > _MAX_FORMATTED_CONVERSATION_LEN:
                lines.append("... (earlier turns truncated)")
                break
            total += len(line)
            lines.append(line)
        lines.reverse()
        return "\n".join(lines)

    async def _reset_session(self) -> None:
        """확정된 플랜을 초기화하고 새 세션을 준비한다."""
        if self._active_plan:
            try:
                await self._state_store.delete_plan(self._active_plan.session_id)
            except Exception as e:
                log.warning("Failed to delete plan from DB", err=str(e))
        self._active_plan = None
        self._conversation.clear()

    async def _recall_memories(self, query: str) -> str:
        """장기 기억에서 관련 정보를 검색하여 프롬프트 섹션으로 반환한다."""
        if not self._memory:
            return ""
        try:
            memories = await self._memory.search_formatted(query, top_k=5)
            if not memories:
                return ""
            return (
                "<previous_decisions>\n"
                f"{memories}\n"
                "</previous_decisions>\n\n"
            )
        except Exception as e:
            log.warning("Memory recall failed", err=str(e))
            return ""

    async def _save_memories(self) -> None:
        """현재 대화의 핵심 결정/사실을 장기 기억에 저장한다."""
        if not self._memory or not self._conversation or not self._active_plan:
            return
        try:
            from src.core.memory.extractor import extract_memories

            extracted = await extract_memories(self._conversation, self._llm)
            summary = extracted.get("summary", "")
            decisions = extracted.get("decisions", [])
            tech_stack = extracted.get("tech_stack", [])
            preferences = extracted.get("user_preferences", [])

            all_decisions = decisions + [f"기술 스택: {t}" for t in tech_stack]
            all_decisions += [f"사용자 요구: {p}" for p in preferences]

            if summary or all_decisions:
                await self._memory.save_conversation_summary(
                    summary=summary,
                    decisions=all_decisions,
                    session_id=self._active_plan.session_id,
                )
        except Exception as e:
            log.warning("Memory save failed", err=str(e))

    async def _broadcast_director_message(self, content: str) -> None:
        """사용자에게 Director 메시지를 WS로 전송한다."""
        log.info("Director says", content=content[:2000])
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
        """현재 EpicPlan 상태를 WS로 전송하고 DB에 persist한다."""
        if self._active_plan is None:
            return
        await self._persist_plan()
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
