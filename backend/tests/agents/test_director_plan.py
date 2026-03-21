"""DirectorAgent 대화형 워크플로우 테스트 — Stage 상태 머신."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.director.director_agent import DirectorAgent, _resolve_agent_id
from src.core.messaging.message_bus import MessageBus
from src.core.types import (
    AgentConfig,
    AgentLevel,
    EpicPlan,
    PlanStage,
    TaskDraft,
    UserInput,
)


def _make_llm(**overrides):
    """LLM mock 생성. chat_json의 반환값을 overrides로 제어한다."""
    llm = MagicMock()
    llm.chat = AsyncMock(return_value=("create_epic", 5, 5))
    llm.chat_json = AsyncMock(return_value=({}, 10, 10))
    for k, v in overrides.items():
        setattr(llm, k, v)
    return llm


def _make_director(state_store=None, git_service=None, llm_client=None):
    if state_store is None:
        state_store = MagicMock()
        state_store.save_message = AsyncMock()
        state_store.get_agent_config = AsyncMock(return_value=None)
    if git_service is None:
        git_service = MagicMock()
        git_service.ensure_label = AsyncMock()
        git_service.add_issue_to_project = AsyncMock(return_value="item-id")
        git_service.link_sub_issue = AsyncMock()
        git_service.close_issue = AsyncMock()
    if llm_client is None:
        llm_client = _make_llm()

    config = AgentConfig(id="director", domain="director", level=AgentLevel.DIRECTOR)
    bus = MessageBus()
    return DirectorAgent(
        config=config,
        message_bus=bus,
        state_store=state_store,
        git_service=git_service,
        llm_client=llm_client,
    )


@pytest.fixture
def state_store():
    store = MagicMock()
    store.save_message = AsyncMock()
    store.get_agent_config = AsyncMock(return_value=None)
    store.create_epic = AsyncMock()
    store.create_task = AsyncMock()
    store.get_all_agents = AsyncMock(return_value=[])
    store.get_all_tasks = AsyncMock(return_value=[])
    return store


@pytest.fixture
def git_service():
    svc = MagicMock()
    svc.create_issue = AsyncMock(return_value=1)
    svc.move_issue_to_column = AsyncMock()
    svc.ensure_label = AsyncMock()
    svc.add_issue_to_project = AsyncMock(return_value="item-id")
    svc.link_sub_issue = AsyncMock()
    svc.close_issue = AsyncMock()
    return svc


class TestResolveAgentId:
    def test_exact_match(self):
        assert _resolve_agent_id("agent-backend") == "agent-backend"

    def test_keyword_match(self):
        assert _resolve_agent_id("backend") == "agent-backend"
        assert _resolve_agent_id("ui") == "agent-frontend"

    def test_empty_returns_none(self):
        assert _resolve_agent_id("") is None

    def test_unknown_returns_none(self):
        assert _resolve_agent_id("unknown-agent") is None


class TestGatheringStage:
    async def test_new_input_creates_plan(self, state_store, git_service):
        """새 요청이 들어오면 GATHERING Stage의 EpicPlan이 생성된다."""
        llm = _make_llm(
            chat=AsyncMock(return_value=("create_epic", 5, 5)),
            chat_json=AsyncMock(return_value=(
                {
                    "response": "어떤 인증 방식을 원하세요?",
                    "action": "continue",
                    "project_update": {"topic": "인증 시스템"},
                    "decisions_append": [],
                },
                10, 10,
            )),
        )
        director = _make_director(state_store, git_service, llm)

        await director.handle_user_input(
            UserInput(source="dashboard", content="인증 시스템 만들어줘")
        )

        assert director.active_plan is not None
        assert director.active_plan.stage == PlanStage.GATHERING
        assert director.active_plan.project.topic == "인증 시스템"

    async def test_gathering_updates_project_context(self, state_store, git_service):
        """GATHERING 대화 중 ProjectContext가 누적 업데이트된다."""
        call_count = 0

        async def fake_chat_json(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (
                    {
                        "response": "기술 스택은?",
                        "action": "continue",
                        "project_update": {"topic": "채팅 앱", "purpose": "사내 소통"},
                        "decisions_append": [],
                    },
                    10, 10,
                )
            return (
                {
                    "response": "요구사항 정리됐습니다.",
                    "action": "continue",
                    "project_update": {
                        "tech_stack": {"frontend": ["React"], "backend": ["FastAPI"]},
                        "scope": "MVP",
                    },
                    "decisions_append": ["MVP 우선"],
                },
                10, 10,
            )

        llm = _make_llm(
            chat=AsyncMock(return_value=("create_epic", 5, 5)),
            chat_json=AsyncMock(side_effect=fake_chat_json),
        )
        director = _make_director(state_store, git_service, llm)

        # 첫 메시지 → plan 생성 + gathering
        await director.handle_user_input(
            UserInput(source="dashboard", content="채팅 앱 만들자")
        )
        assert director.active_plan.project.topic == "채팅 앱"

        # 두 번째 메시지 → 추가 정보
        await director.handle_user_input(
            UserInput(source="dashboard", content="React+FastAPI, MVP로")
        )
        plan = director.active_plan
        assert plan.project.tech_stack.frontend == ["React"]
        assert plan.project.tech_stack.backend == ["FastAPI"]
        assert plan.project.scope == "MVP"
        assert "MVP 우선" in plan.decisions

    async def test_lock_transitions_to_structuring(self, state_store, git_service):
        """LLM이 lock을 반환하면 STRUCTURING Stage로 전환된다."""
        call_count = 0

        async def fake_chat_json(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # gathering 응답 — lock
                return (
                    {
                        "response": "요구사항 확정합니다.",
                        "action": "lock",
                        "project_update": {"topic": "인증"},
                        "decisions_append": ["JWT 기반"],
                    },
                    10, 10,
                )
            # structuring 응답 (자동 호출됨)
            return (
                {
                    "response": "태스크를 나눴습니다.",
                    "epic_title": "JWT 인증",
                    "epic_description": "JWT 기반 인증 시스템",
                    "tasks": [
                        {
                            "temp_id": "draft-1",
                            "title": "JWT 미들웨어",
                            "agent": "agent-backend",
                            "priority": 1,
                        },
                    ],
                },
                20, 20,
            )

        llm = _make_llm(
            chat=AsyncMock(return_value=("create_epic", 5, 5)),
            chat_json=AsyncMock(side_effect=fake_chat_json),
        )
        director = _make_director(state_store, git_service, llm)

        await director.handle_user_input(
            UserInput(source="dashboard", content="JWT 인증 만들어")
        )

        plan = director.active_plan
        assert plan.stage == PlanStage.STRUCTURING
        assert plan.epic_title == "JWT 인증"
        assert len(plan.tasks) == 1
        assert plan.tasks[0].title == "JWT 미들웨어"


class TestStructuringStage:
    async def test_revise_updates_tasks(self, state_store, git_service):
        """STRUCTURING에서 수정 요청 시 태스크가 업데이트된다."""
        llm = _make_llm(
            chat_json=AsyncMock(return_value=(
                {
                    "response": "프론트 태스크도 추가했어요.",
                    "epic_title": "인증 시스템",
                    "epic_description": "JWT 인증",
                    "tasks": [
                        {"temp_id": "draft-1", "title": "JWT 미들웨어", "agent": "agent-backend", "priority": 1},
                        {"temp_id": "draft-2", "title": "로그인 UI", "agent": "agent-frontend", "priority": 2},
                    ],
                },
                20, 20,
            )),
        )
        director = _make_director(state_store, git_service, llm)

        # 직접 plan 설정 (gathering 건너뛰기)
        director._active_plan = EpicPlan(
            session_id="test",
            stage=PlanStage.STRUCTURING,
            epic_title="인증",
            tasks=[TaskDraft(temp_id="draft-1", title="JWT 미들웨어", agent="agent-backend", priority=1)],
        )

        await director.handle_user_input(
            UserInput(source="dashboard", content="프론트 로그인 UI도 추가해")
        )

        assert len(director.active_plan.tasks) == 2
        assert director.active_plan.tasks[1].title == "로그인 UI"


class TestPlanAction:
    async def test_approve_transitions_to_confirming(self, state_store, git_service):
        """plan.approve → STRUCTURING에서 CONFIRMING으로 전환."""
        llm = _make_llm()
        director = _make_director(state_store, git_service, llm)

        director._active_plan = EpicPlan(
            session_id="test",
            stage=PlanStage.STRUCTURING,
            epic_title="인증",
            tasks=[TaskDraft(temp_id="draft-1", title="JWT", agent="agent-backend", priority=1)],
        )

        await director.handle_plan_action("approve")

        assert director.active_plan.stage == PlanStage.CONFIRMING

    async def test_commit_creates_issues(self, state_store, git_service):
        """plan.commit → CONFIRMING에서 GitHub Issues 생성 후 COMMITTED."""
        issue_counter = 0

        async def fake_create_issue(spec):
            nonlocal issue_counter
            issue_counter += 1
            return issue_counter

        git_service.create_issue = AsyncMock(side_effect=fake_create_issue)
        llm = _make_llm()
        director = _make_director(state_store, git_service, llm)

        director._active_plan = EpicPlan(
            session_id="test",
            stage=PlanStage.CONFIRMING,
            epic_title="인증 시스템",
            epic_description="JWT 기반",
            tasks=[
                TaskDraft(temp_id="draft-1", title="JWT 미들웨어", agent="agent-backend", priority=1),
                TaskDraft(temp_id="draft-2", title="로그인 API", agent="agent-backend", priority=1),
                TaskDraft(temp_id="draft-3", title="로그인 UI", agent="agent-frontend", priority=2, dependencies=["draft-2"]),
            ],
        )

        await director.handle_plan_action("commit")

        assert director.active_plan.stage == PlanStage.COMMITTED
        assert state_store.create_epic.call_count == 1
        assert state_store.create_task.call_count == 3
        # 3개 서브이슈 + 1개 Epic 이슈 = 4번 호출
        assert git_service.create_issue.call_count == 4

        # 의존성이 temp_id에서 실제 task_id로 변환되었는지 확인
        third_call = state_store.create_task.call_args_list[2][0][0]
        assert len(third_call["dependencies"]) == 1
        assert third_call["dependencies"][0] != "draft-2"  # 실제 UUID여야 함

    async def test_commit_without_confirming_stage_rejected(self, state_store, git_service):
        """CONFIRMING이 아닌 Stage에서 commit 시도하면 거부된다."""
        llm = _make_llm()
        director = _make_director(state_store, git_service, llm)

        director._active_plan = EpicPlan(
            session_id="test",
            stage=PlanStage.STRUCTURING,
            tasks=[TaskDraft(temp_id="draft-1", title="t1")],
        )

        await director.handle_plan_action("commit")

        assert director.active_plan.stage == PlanStage.STRUCTURING  # 변경 없음
        state_store.create_epic.assert_not_called()

    async def test_revise_from_confirming_goes_back_to_structuring(self, state_store, git_service):
        """CONFIRMING에서 revise → STRUCTURING으로 역행."""
        llm = _make_llm(
            chat_json=AsyncMock(return_value=(
                {
                    "response": "수정했습니다.",
                    "epic_title": "인증 v2",
                    "tasks": [{"temp_id": "draft-1", "title": "수정된 태스크"}],
                },
                10, 10,
            )),
        )
        director = _make_director(state_store, git_service, llm)

        director._active_plan = EpicPlan(
            session_id="test",
            stage=PlanStage.CONFIRMING,
            epic_title="인증",
            tasks=[TaskDraft(temp_id="draft-1", title="원래 태스크")],
        )

        await director.handle_plan_action("revise", "이름 바꿔줘")

        assert director.active_plan.stage == PlanStage.STRUCTURING

    async def test_no_active_plan_action_noop(self, state_store, git_service):
        """활성 플랜 없이 plan action 시도 — 에러 없이 메시지만 전송."""
        llm = _make_llm()
        director = _make_director(state_store, git_service, llm)

        # 예외 없이 실행되어야 함
        await director.handle_plan_action("commit")


class TestStatusQuery:
    async def test_status_query_broadcasts_summary(self, state_store, git_service):
        """status_query 분류 시 에이전트/태스크 요약을 브로드캐스트한다."""
        agent_mock = MagicMock()
        agent_mock.status = "busy"
        state_store.get_all_agents = AsyncMock(return_value=[agent_mock])

        task_mock = MagicMock()
        task_mock.status = "in-progress"
        state_store.get_all_tasks = AsyncMock(return_value=[task_mock])

        llm = _make_llm(
            chat=AsyncMock(return_value=("status_query", 5, 5)),
        )
        director = _make_director(state_store, git_service, llm)

        # 메시지 발행 추적
        published: list = []
        director._message_bus.subscribe_all(lambda msg: published.append(msg))

        await director.handle_user_input(
            UserInput(source="dashboard", content="현재 상태 알려줘")
        )

        # director.message 이벤트가 발행되었는지 확인
        director_msgs = [m for m in published if m.type == "director.message"]
        assert len(director_msgs) == 1
        assert "에이전트 1명" in director_msgs[0].payload["content"]


class TestConversationWindow:
    async def test_sliding_window_limit(self, state_store, git_service):
        """대화 기록이 MAX_CONVERSATION_TURNS * 2를 초과하면 잘린다."""
        llm = _make_llm()
        director = _make_director(state_store, git_service, llm)

        # 대화 12개 추가 (limit = 5 * 2 = 10)
        for i in range(12):
            director._append_conversation("user", f"msg-{i}")

        assert len(director._conversation) == 10
        assert director._conversation[0]["content"] == "msg-2"  # 오래된 것 삭제됨
