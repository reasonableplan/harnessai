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
        cmd = self._build_command(config, prompt, system_prompt)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(working_dir) if working_dir else None,
            # Unix에서 새 프로세스 그룹 생성 — SIGTERM을 트리 전체에 전달하기 위해
            **({"start_new_session": True} if sys.platform != "win32" else {}),
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=config.timeout_seconds,
            )
        except asyncio.TimeoutError:
            await self._kill_process_tree(proc)
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
    ) -> list[str]:
        """Claude CLI 명령어 구성.

        asyncio.create_subprocess_exec은 OS exec()를 직접 호출하므로
        Windows CMD의 32KB 제한과 무관하다 (exec 인자 한도: Linux ~2MB, Windows ~32KB).
        system_prompt는 항상 --system-prompt 인라인으로 전달한다.
        """
        cmd = [
            "claude",
            "-p", prompt,
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
