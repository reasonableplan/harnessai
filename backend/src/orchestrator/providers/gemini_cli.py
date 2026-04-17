"""Gemini CLI provider — subprocess로 Gemini CLI 실행."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path

from src.orchestrator.config import AgentConfig
from src.orchestrator.providers.base import BaseProvider


class GeminiCliProvider(BaseProvider):
    """Gemini CLI를 subprocess로 실행하는 provider.

    환경변수 GEMINI_API_KEY가 필요하다.
    gemini -p <prompt> -m <model> -o text -y
    """

    async def execute(
        self,
        agent_name: str,
        config: AgentConfig,
        prompt: str,
        *,
        system_prompt: str | None = None,
        working_dir: Path | None = None,
    ) -> str:
        cmd = self._build_command(config)

        # Gemini CLI는 --system-prompt 플래그가 없음 — 프롬프트 앞에 붙임
        full_prompt = (
            f"{system_prompt}\n\n---\n\n{prompt}" if system_prompt else prompt
        )

        env = {**os.environ}
        # GEMINI_API_KEY가 환경에 없으면 명시적 경고
        if "GEMINI_API_KEY" not in env:
            raise RuntimeError(
                "GEMINI_API_KEY 환경변수가 설정되어 있지 않습니다."
            )

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(working_dir) if working_dir else None,
            env=env,
            **({"start_new_session": True} if sys.platform != "win32" else {}),
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=full_prompt.encode("utf-8")),
                timeout=config.timeout_seconds,
            )
        except TimeoutError:
            await self._kill_process_tree(proc)
            await proc.wait()
            raise TimeoutError(
                f"{agent_name} 타임아웃: {config.timeout_seconds}초 초과"
            ) from None

        if proc.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"{agent_name} Gemini CLI 실행 실패 (exit {proc.returncode}): {error_msg}"
            )

        return stdout.decode("utf-8", errors="replace").strip()

    def _build_command(self, config: AgentConfig) -> list[str]:
        """Gemini CLI 명령어 구성.

        프롬프트는 stdin으로 전달 (-p 플래그 없이 stdin만 사용).
        -y: 모든 tool 승인 자동화 (비대화형 실행에 필수)
        -o text: ANSI 이스케이프 없는 순수 텍스트 출력
        """
        cli = "gemini.cmd" if sys.platform == "win32" else "gemini"
        return [
            cli,
            "-p", "",       # 비대화형 모드 활성화 (실제 프롬프트는 stdin)
            "-m", config.model,
            "-o", "text",   # 순수 텍스트 출력
            "-y",           # 모든 tool 자동 승인
        ]

    async def _kill_process_tree(self, proc: asyncio.subprocess.Process) -> None:
        """프로세스와 자식 프로세스 트리를 종료."""
        pid = proc.pid
        if pid is None:
            return
        try:
            if sys.platform == "win32":
                kill_proc = await asyncio.create_subprocess_exec(
                    "taskkill", "/T", "/F", "/PID", str(pid),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await kill_proc.wait()
            else:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass
