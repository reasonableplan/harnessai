"""Claude CLI provider — subprocess로 Claude CLI 실행."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path

from src.orchestrator.config import AgentConfig
from src.orchestrator.providers.base import BaseProvider


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
        cmd = self._build_command(config, system_prompt)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,   # 프롬프트를 stdin으로 전달 — Windows cmd.exe 8191자 제한 우회
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(working_dir) if working_dir else None,
            # Unix에서 새 프로세스 그룹 생성 — SIGTERM을 트리 전체에 전달하기 위해
            **({"start_new_session": True} if sys.platform != "win32" else {}),
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=prompt.encode("utf-8")),
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
                f"{agent_name} CLI 실행 실패 (exit {proc.returncode}): {error_msg}"
            )

        return stdout.decode("utf-8", errors="replace").strip()

    def _build_command(
        self,
        config: AgentConfig,
        system_prompt: str | None,
    ) -> list[str]:
        """Claude CLI 명령어 구성.

        프롬프트는 stdin으로 전달 — Windows .cmd 래퍼가 cmd.exe를 거칠 때 발생하는
        8191자 커맨드라인 제한을 우회한다. -p (print mode) + stdin 조합.
        """
        # Windows에서 npm CLI는 .cmd 래퍼로 설치됨 — create_subprocess_exec은 .cmd 직접 실행 불가
        cli = "claude.cmd" if sys.platform == "win32" else "claude"
        cmd = [
            cli,
            "-p",                           # non-interactive print 모드, stdin에서 prompt 읽음
            "--model", config.model,
        ]

        if system_prompt:
            cmd.extend(["--system-prompt", system_prompt])

        return cmd

    async def _kill_process_tree(self, proc: asyncio.subprocess.Process) -> None:
        """프로세스와 자식 프로세스 트리를 종료."""
        pid = proc.pid
        if pid is None:
            return
        try:
            if sys.platform == "win32":
                # Windows: taskkill로 프로세스 트리 전체 강제 종료
                kill_proc = await asyncio.create_subprocess_exec(
                    "taskkill", "/T", "/F", "/PID", str(pid),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await kill_proc.wait()
            else:
                # Unix: 새 세션 그룹 전체에 SIGTERM 전달
                os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass
