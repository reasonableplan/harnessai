"""claude CLI subprocess 기반 LLM 클라이언트 (USE_CLAUDE_CLI=true 시 사용)."""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile

from src.core.llm.json_extract import parse_json_response
from src.core.logging.logger import get_logger
from src.core.resilience.api_retry import with_retry

log = get_logger("ClaudeCliClient")

_CLI_TIMEOUT_S = 600.0  # 10분 — 복잡한 코드 생성 + Director 리뷰(대용량 diff) 고려

# 프로세스 그룹 격리 — 타임아웃 시 트리 종료를 위해 필요
_PGROUP_KWARGS: dict = (
    {"creationflags": 0x00000200}  # CREATE_NEW_PROCESS_GROUP
    if sys.platform == "win32"
    else {"start_new_session": True}
)


async def _kill_process_tree(proc: asyncio.subprocess.Process) -> None:
    """프로세스와 자식 프로세스 트리 전체를 종료한다.

    Windows: taskkill /T /F (트리 종료)
    Unix: process group 단위 SIGTERM → SIGKILL fallback
    """
    if proc.returncode is not None:
        return  # 이미 종료됨

    if sys.platform == "win32":
        try:
            kill_proc = await asyncio.create_subprocess_exec(
                "taskkill", "/T", "/F", "/PID", str(proc.pid),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(kill_proc.wait(), timeout=10.0)
        except (asyncio.TimeoutError, OSError) as e:
            log.warning("taskkill failed, falling back to proc.kill()", err=str(e))
            proc.kill()
    else:
        import signal

        try:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGTERM)
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            proc.kill()

    try:
        await asyncio.wait_for(proc.wait(), timeout=5.0)
    except asyncio.TimeoutError:
        pass


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

    def __init__(self, default_model: str | None = None) -> None:
        self._tokens_used = 0
        self._cli_args = _resolve_cli_args()
        self._default_model = default_model
        log.info("ClaudeCliClient initialized", args=self._cli_args, model=default_model)

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
        # CLI가 대화형 응답 대신 JSON만 반환하도록 접미사 추가
        if "JSON" in prompt or "json" in prompt:
            prompt += "\n\nIMPORTANT: Respond ONLY with the requested JSON. No questions, no conversation. Just JSON."
        log.debug("ClaudeCliClient calling claude CLI", prompt_len=len(prompt))

        async def _call() -> str:
            # stdin으로 프롬프트 전달 — Windows에서 긴 유니코드
            # command-line 인자가 프로세스를 멈추는 문제 방지
            use_model = model or self._default_model
            model_args = ["--model", use_model] if use_model else []
            try:
                proc = await asyncio.create_subprocess_exec(
                    *self._cli_args, "-p", *model_args,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=tempfile.gettempdir(),  # 프로젝트 CLAUDE.md 컨텍스트 차단
                    **_PGROUP_KWARGS,
                )
            except FileNotFoundError as e:
                raise RuntimeError(
                    f"claude CLI not found ({self._cli_args[0]}). "
                    "Install Claude Code or set USE_CLAUDE_CLI=false."
                ) from e

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(input=prompt.encode("utf-8")),
                    timeout=_CLI_TIMEOUT_S,
                )
            except asyncio.TimeoutError as e:
                await _kill_process_tree(proc)
                raise RuntimeError(f"claude CLI timed out after {_CLI_TIMEOUT_S}s") from e

            if proc.returncode != 0:
                err = stderr.decode(errors="replace").strip()
                raise RuntimeError(f"claude CLI exited with code {proc.returncode}: {err}")

            return stdout.decode(errors="replace").strip()

        text = await with_retry(_call, max_retries=2, label="ClaudeCLI")
        # CLI는 토큰 카운트를 제공하지 않으므로 문자 수 기반 추정
        estimated_input = len(prompt) // 4
        estimated_output = len(text) // 4
        self._tokens_used += estimated_input + estimated_output
        return text, estimated_input, estimated_output

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

    async def execute_in_workspace(
        self,
        work_dir: str,
        instructions: str,
        timeout: float = _CLI_TIMEOUT_S,
    ) -> tuple[bool, str]:
        """workspace에서 Claude Code를 자율 실행한다.

        Agent가 파일을 읽고, 코드를 쓰고, 테스트를 돌리고, 에러를 고치는
        실제 개발자처럼 동작한다.

        Returns: (success, summary)
        """
        log.info("Executing in workspace", work_dir=work_dir, instructions_len=len(instructions))

        # --allowedTools가 CLI 버전에 따라 미지원일 수 있으므로 fallback
        cli_extra_args = ["--allowedTools", "Read,Write,Edit,Bash,Glob,Grep"]
        model_args = ["--model", self._default_model] if self._default_model else []
        try:
            proc = await asyncio.create_subprocess_exec(
                *self._cli_args, "-p", *model_args, *cli_extra_args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
                **_PGROUP_KWARGS,
            )
        except FileNotFoundError as e:
            raise RuntimeError(f"claude CLI not found ({self._cli_args[0]})") from e

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=instructions.encode("utf-8")),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            await _kill_process_tree(proc)
            return False, f"CLI timed out after {timeout}s"

        output = stdout.decode(errors="replace").strip()
        if proc.returncode != 0:
            err = stderr.decode(errors="replace").strip()
            log.warning("CLI execution failed", returncode=proc.returncode, err=err[:500])
            return False, f"CLI exited {proc.returncode}: {err[:500]}"

        estimated_tokens = (len(instructions) + len(output)) // 4
        self._tokens_used += estimated_tokens
        return True, output

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
