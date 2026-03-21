"""memory extractor 테스트 — 대화에서 핵심 정보 추출."""
from __future__ import annotations

from unittest.mock import AsyncMock

from src.core.memory.extractor import extract_memories


async def test_empty_conversation_returns_defaults():
    """빈 대화는 기본값 반환."""
    llm = AsyncMock()
    result = await extract_memories([], llm)

    assert result["summary"] == ""
    assert result["decisions"] == []
    assert result["tech_stack"] == []
    assert result["user_preferences"] == []
    llm.chat_json.assert_not_called()


async def test_extracts_from_conversation():
    """LLM 응답이 정상이면 그대로 반환."""
    llm = AsyncMock()
    llm.chat_json = AsyncMock(return_value=(
        {
            "summary": "React 프로젝트 논의",
            "decisions": ["TypeScript 사용"],
            "tech_stack": ["React", "Vite"],
            "user_preferences": ["한국어로 소통"],
        },
        100, 50,
    ))

    conversation = [
        {"role": "user", "content": "React로 만들어줘"},
        {"role": "assistant", "content": "TypeScript + Vite로 구성하겠습니다"},
    ]
    result = await extract_memories(conversation, llm)

    assert result["summary"] == "React 프로젝트 논의"
    assert "TypeScript 사용" in result["decisions"]
    llm.chat_json.assert_called_once()


async def test_llm_returns_non_dict():
    """LLM이 dict가 아닌 값 반환 시 기본값."""
    llm = AsyncMock()
    llm.chat_json = AsyncMock(return_value=("not a dict", 0, 0))

    conversation = [{"role": "user", "content": "test"}]
    result = await extract_memories(conversation, llm)

    assert result["summary"] == ""
    assert result["decisions"] == []


async def test_llm_error_returns_defaults():
    """LLM 에러 시 기본값 반환 (크래시 없음)."""
    llm = AsyncMock()
    llm.chat_json = AsyncMock(side_effect=RuntimeError("API error"))

    conversation = [{"role": "user", "content": "test"}]
    result = await extract_memories(conversation, llm)

    assert result["summary"] == ""
    assert result["decisions"] == []


async def test_xml_escape_applied():
    """대화 내용이 XML escape된다."""
    llm = AsyncMock()
    llm.chat_json = AsyncMock(return_value=({"summary": "ok", "decisions": [], "tech_stack": [], "user_preferences": []}, 0, 0))

    conversation = [{"role": "user", "content": '<script>alert("xss")</script>'}]
    await extract_memories(conversation, llm)

    call_args = llm.chat_json.call_args
    prompt = call_args[1]["messages"][0]["content"] if "messages" in call_args[1] else call_args[0][0][0]["content"]
    assert "<script>" not in prompt
    assert "&lt;script&gt;" in prompt
