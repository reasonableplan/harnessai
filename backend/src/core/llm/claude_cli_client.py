"""claude CLI subprocess 기반 LLM 클라이언트 (USE_CLAUDE_CLI=true 시 사용)."""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile

from src.core.llm.json_extract import parse_json_response
from src.core.logging.logger import get_logger

log = get_logger("ClaudeCliClient")

_CLI_TIMEOUT_S = 180.0  # 3분 — 복잡한 코드 생성 태스크 고려


def _resolve_cli_args() -> list[str]:
    """subprocess에 전달할 CLI 실행 인자 목록을 반환한다.

    Windows의 .cmd 래퍼는 cmd.exe를 경유하므로 <> 문자가 shell redirect로
    해석되는 문제가 있다. node + cli.js 를 직접 호출해 cmd.exe를 우회한다.
    """
    # 환경변수로 명시적 지정 가능
    explicit = os.environ.get("CLAUDE_CLI_PATH")
    if explicit:
        return [explicit]

    # npm 디렉토리 탐색
    npm_dir: str | None = None
    found = shutil.which("claude")
    if found:
        npm_dir = os.path.dirname(found)
    elif sys.platform == "win32":
        candidate = os.path.expandvars(r"%APPDATA%\npm")
        if os.path.isdir(candidate):
            npm_dir = candidate

    # node + cli.js 경로 확인
    if npm_dir:
        cli_js = os.path.join(npm_dir, "node_modules", "@anthropic-ai", "claude-code", "cli.js")
        if os.path.exists(cli_js):
            node = shutil.which("node") or "node"
            log.debug("Using node + cli.js directly", node=node, cli_js=cli_js)
            return [node, cli_js]

    # 폴백: .cmd/.sh 래퍼 직접 사용 (Unix)
    if found:
        return [found]

    raise RuntimeError(
        "claude CLI not found. Install Claude Code or set USE_CLAUDE_CLI=false."
    )


class ClaudeCliClient:
    """claude CLI를 asyncio subprocess로 실행하는 LLM 클라이언트.

    chat/chat_json 인터페이스를 ClaudeClient와 동일하게 맞춰 드롭인 교체 가능.
    토큰 카운트는 CLI가 제공하지 않으므로 0으로 반환한다.
    """

    def __init__(self) -> None:
        self._tokens_used = 0
        self._cli_args = _resolve_cli_args()
        log.info("ClaudeCliClient initialized", args=self._cli_args)

    async def chat(
        self,
        messages: list[dict],
        system: str | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        token_budget: int | None = None,
    ) -> tuple[str, int, int]:
        """
        claude CLI 호출.
        Returns: (response_text, input_tokens=0, output_tokens=0)
        """
        prompt = _build_prompt(messages, system)
        log.debug("ClaudeCliClient calling claude CLI", prompt_len=len(prompt))

        try:
            proc = await asyncio.create_subprocess_exec(
                *self._cli_args, "-p", prompt,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=tempfile.gettempdir(),  # 프로젝트 CLAUDE.md 컨텍스트 차단
            )
        except FileNotFoundError as e:
            raise RuntimeError(
                f"claude CLI not found ({self._cli_args[0]}). "
                "Install Claude Code or set USE_CLAUDE_CLI=false."
            ) from e

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=_CLI_TIMEOUT_S
            )
        except asyncio.TimeoutError as e:
            proc.kill()
            raise RuntimeError(f"claude CLI timed out after {_CLI_TIMEOUT_S}s") from e

        if proc.returncode != 0:
            err = stderr.decode(errors="replace").strip()
            raise RuntimeError(f"claude CLI exited with code {proc.returncode}: {err}")

        text = stdout.decode(errors="replace").strip()
        return text, 0, 0

    async def chat_json(
        self,
        messages: list[dict],
        system: str | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        token_budget: int | None = None,
    ) -> tuple[dict | list, int, int]:
        """JSON 응답을 파싱해서 반환."""
        text, input_tokens, output_tokens = await self.chat(
            messages=messages,
            system=system,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            token_budget=token_budget,
        )
        return parse_json_response(text), input_tokens, output_tokens

    @property
    def tokens_used(self) -> int:
        return self._tokens_used


def _build_prompt(messages: list[dict], system: str | None) -> str:
    """messages 배열을 단일 프롬프트 문자열로 변환한다."""
    parts: list[str] = []
    if system:
        parts.append(f"{system}\n")
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            parts.append(content)
        elif role == "assistant":
            parts.append(f"Assistant: {content}")
    return "\n\n".join(parts)
