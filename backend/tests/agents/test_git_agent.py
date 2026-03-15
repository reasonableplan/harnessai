"""GitAgent 테스트 — commit 메시지 처리, work_dir 접근."""
from __future__ import annotations

import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.git.git_agent import GitAgent
from src.core.messaging.message_bus import MessageBus
from src.core.types import AgentConfig, AgentLevel, Task, TaskStatus


def make_config():
    return AgentConfig(id="agent-git", domain="git", level=AgentLevel.WORKER)


def make_task(title: str = "feat: test commit", task_id: str = "t1") -> Task:
    return Task(
        id=task_id,
        title=title,
        description="",
        status=TaskStatus.IN_PROGRESS,
        board_column="In Progress",
        labels=["commit"],
    )


@pytest.fixture
def git_service():
    svc = MagicMock()
    svc.work_dir = "/tmp/workspace"
    svc.move_issue_to_column = AsyncMock()
    svc.create_branch = AsyncMock()
    svc.create_pr = AsyncMock(return_value=1)
    return svc


@pytest.fixture
def agent(git_service):
    bus = MessageBus()
    state_store = MagicMock()
    state_store.update_task = AsyncMock()
    state_store.get_agent_config = AsyncMock(return_value=None)
    state_store.save_message = AsyncMock()
    return GitAgent(
        config=make_config(),
        message_bus=bus,
        state_store=state_store,
        git_service=git_service,
    )


class TestHandleCommit:
    async def test_uses_public_work_dir_property(self, agent, git_service):
        """_work_dir private 접근 대신 work_dir property를 사용한다."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            await agent._handle_commit(make_task())

        calls = mock_run.call_args_list
        for call in calls:
            assert "/tmp/workspace" in call[0][0]

    async def test_uses_git_add_u_not_A(self, agent, git_service):
        """`git add -u` 를 사용한다 (미추적 파일 포함 -A 금지)."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            await agent._handle_commit(make_task())

        add_call = mock_run.call_args_list[0][0][0]
        assert "-u" in add_call
        assert "-A" not in add_call

    async def test_commit_message_truncated_at_250(self, agent, git_service):
        """커밋 메시지가 250자를 초과하면 잘린다."""
        long_title = "x" * 300
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            await agent._handle_commit(make_task(title=long_title))

        commit_call = mock_run.call_args_list[1][0][0]
        msg_index = commit_call.index("-m") + 1
        assert len(commit_call[msg_index]) <= 250

    async def test_empty_title_uses_fallback(self, agent, git_service):
        """빈 제목은 fallback 커밋 메시지를 사용한다."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            task = make_task(title="   ")
            await agent._handle_commit(task)

        commit_call = mock_run.call_args_list[1][0][0]
        msg_index = commit_call.index("-m") + 1
        assert commit_call[msg_index].startswith("chore: task")

    async def test_subprocess_error_raises_runtime_error(self, agent, git_service):
        """subprocess 실패 시 RuntimeError를 발생시킨다."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "git", stderr="error")
            with pytest.raises(RuntimeError):
                await agent._handle_commit(make_task())

    async def test_returns_success_result(self, agent, git_service):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = await agent._handle_commit(make_task())

        assert result.success is True
        assert result.data == {"committed": True}
