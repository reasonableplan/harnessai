"""BaseCodeGeneratorAgent._safe_resolve 보안 테스트."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.agent.base_code_generator import BaseCodeGeneratorAgent
from src.core.errors import SandboxEscapeError
from src.core.messaging.message_bus import MessageBus
from src.core.types import AgentConfig, AgentLevel, Task


class _ConcreteAgent(BaseCodeGeneratorAgent):
    def _build_prompt(self, task: Task) -> str:
        return "test"


def _make_agent(work_dir: str = "/tmp/workspace") -> _ConcreteAgent:
    config = AgentConfig(id="test-agent", domain="test", level=AgentLevel.WORKER)
    bus = MessageBus()
    store = MagicMock()
    store.get_agent_config = AsyncMock(return_value=None)
    store.save_message = AsyncMock()
    git = MagicMock()
    llm = MagicMock()
    return _ConcreteAgent(config, bus, store, git, llm, work_dir=work_dir)


class TestSafeResolve:
    def test_allows_relative_path_inside_workspace(self):
        agent = _make_agent()
        result = agent._safe_resolve("src/main.py")
        assert "src" in str(result)
        assert "main.py" in str(result)

    def test_allows_nested_path(self):
        agent = _make_agent()
        result = agent._safe_resolve("src/core/utils/helper.py")
        assert result.name == "helper.py"

    def test_blocks_parent_traversal(self):
        agent = _make_agent()
        with pytest.raises(SandboxEscapeError):
            agent._safe_resolve("../../etc/passwd")

    def test_blocks_absolute_path(self):
        agent = _make_agent()
        with pytest.raises(SandboxEscapeError):
            agent._safe_resolve("/etc/passwd")

    def test_blocks_prefix_attack(self):
        """work_dir=/tmp/workspace일 때 /tmp/workspace_evil/x 를 차단해야 한다."""
        agent = _make_agent(work_dir="/tmp/workspace")
        with pytest.raises(SandboxEscapeError):
            agent._safe_resolve("../workspace_evil/malicious.py")

    def test_allows_exact_work_dir_file(self):
        agent = _make_agent()
        result = agent._safe_resolve("file.txt")
        assert result.name == "file.txt"
