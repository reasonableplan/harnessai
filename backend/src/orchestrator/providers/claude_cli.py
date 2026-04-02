"""Claude CLI provider — subprocess로 Claude CLI 실행."""

from __future__ import annotations

import asyncio
from pathlib import Path

from src.orchestrator.config import AgentConfig
from src.orchestrator.providers.base import BaseProvider

# Windows CMD 인자 길이 제한 (~32KB). 이보다 긴 system prompt은 stdin으로 전달.
_MAX_ARG_LENGTH = 30_000


class ClaudeCliProvider(BaseProvider):
    """Claude CLI를 subprocess로 실행하는 provider."""

    async def execute(
        self,
        agent_name: str,
        config: AgentConfig,
        prompt: str,
        *,
        system_prompt: str | None = None,
        working_dir: Path | None = None,
    ) -> str:
        cmd, stdin_data = self._build_command(config, prompt, system_prompt)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE if stdin_data else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(working_dir) if working_dir else None,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=stdin_data),
                timeout=config.timeout_seconds,
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()
            raise TimeoutError(f"{agent_name} 타임아웃: {config.timeout_seconds}초 초과")

        if proc.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"{agent_name} CLI 실행 실패 (exit {proc.returncode}): {error_msg}"
            )

        return stdout.decode("utf-8", errors="replace").strip()

    def _build_command(
        self,
        config: AgentConfig,
        prompt: str,
        system_prompt: str | None,
    ) -> tuple[list[str], bytes | None]:
        """Claude CLI 명령어 구성.

        Returns:
            (명령어 리스트, stdin 데이터 or None)
        """
        cmd = [
            "claude",
            "-p", prompt,
            "--model", config.model,
            "--max-tokens", str(config.max_tokens),
        ]

        stdin_data: bytes | None = None
        if system_prompt:
            if len(system_prompt) <= _MAX_ARG_LENGTH:
                cmd.extend(["--system-prompt", system_prompt])
            else:
                # 긴 프롬프트는 프롬프트에 포함시켜 stdin으로 전달
                combined = f"<system>\n{system_prompt}\n</system>\n\n{prompt}"
                cmd[2] = combined  # -p 인자 교체
                stdin_data = None

        return cmd, stdin_data
