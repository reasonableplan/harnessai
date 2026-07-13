"""HarnessAI v2 — shared process-lifecycle helpers for runtime boot probes.

Used by `ha-smoke` (dev-server readiness probe) and `ha-accept` (http-kind
scenario runner). Owns exactly the process lifecycle: launch, poll a URL
until ready (or the process exits/times out), and tear the process tree
down. It does NOT decide what "pass"/"fail" means to a caller — e.g.
ha-smoke's declared-endpoint probing (`_check_endpoints`) and its
`{"passed", "mode", "detail", "output_tail"}` result shape stay in
skills/ha-smoke/run.py (acceptance-layer-design.md §4).
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

_OUTPUT_TAIL_CHARS = 4000


def kill_tree(proc: subprocess.Popen) -> None:
    """Terminate proc and its children (dev servers that spawn child processes)."""
    if proc.poll() is not None:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
            )
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (OSError, subprocess.TimeoutExpired):
        pass  # 이미 죽었거나 권한 문제 — 아래 wait/kill 폴백이 처리
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


@dataclass(frozen=True)
class ReadyResult:
    """Outcome of polling a URL for readiness.

    - ready=True: `url` answered with an HTTP status in [200, 400) before the
      deadline (`status` carries that code).
    - ready=False, exited=True: the process exited before becoming ready
      (`exit_code` carries its return code) — only possible when `proc` was
      given to wait_ready().
    - ready=False, exited=False, status is not None: `url` answered with an
      error status (>=400 — HTTPError case).
    - ready=False, exited=False, status is None: the deadline passed with no
      response at all (connection refused/reset the whole time).
    """

    ready: bool
    status: int | None = None
    exited: bool = False
    exit_code: int | None = None


def wait_ready(
    url: str,
    timeout: float,
    *,
    proc: subprocess.Popen | None = None,
    poll_interval: float = 0.5,
) -> ReadyResult:
    """Poll `url` until it answers with an HTTP status < 400, or give up.

    If `proc` is given, also detects the process exiting before becoming
    ready (checked once per iteration, before the URL probe) — a crash-on-boot
    case URL polling alone cannot distinguish from "still starting up".
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc is not None:
            rc = proc.poll()
            if rc is not None:
                return ReadyResult(ready=False, exited=True, exit_code=rc)
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                status = resp.status
            if 200 <= status < 400:
                return ReadyResult(ready=True, status=status)
            return ReadyResult(ready=False, status=status)
        except urllib.error.HTTPError as e:
            return ReadyResult(ready=False, status=e.code)
        except (urllib.error.URLError, OSError):
            time.sleep(poll_interval)  # 아직 안 떴음 — 재시도
    return ReadyResult(ready=False)


class BootFailure(Exception):
    """Raised by booted_server() when the launched process never became ready.

    `result` explains why (exited early / bad status / timeout — see
    ReadyResult). `output_tail` is the last captured stdout+stderr text, for
    callers that want to surface a diagnostic.
    """

    def __init__(self, result: ReadyResult, output_tail: str) -> None:
        super().__init__(f"boot failed: {result}")
        self.result = result
        self.output_tail = output_tail


def _read_log_tail(log) -> str:
    try:
        log.flush()
        log.seek(0)
        return log.read()[-_OUTPUT_TAIL_CHARS:]
    except OSError:
        return ""


@contextmanager
def booted_server(cmd: str, cwd: Path, url: str, ready_timeout: int) -> Iterator[str]:
    """Launch `cmd`, wait for `url` to become ready, yield its origin, then tear down.

    On success: yields ``"{scheme}://{netloc}"`` derived from `url`.
    On failure (process exits early / times out / bad status): raises
    BootFailure with the ReadyResult + captured output tail, so callers can
    report "boot failed — scenarios not runnable" distinctly from a scenario
    assertion failure. The process tree is always killed on exit, whether the
    boot succeeded or failed.
    """
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as log:
        kwargs: dict = {}
        if sys.platform != "win32":
            kwargs["start_new_session"] = True  # killpg 로 트리 정리 가능하게
        proc = subprocess.Popen(
            cmd,
            shell=True,
            cwd=str(cwd),
            stdout=log,
            stderr=subprocess.STDOUT,
            **kwargs,
        )
        try:
            result = wait_ready(url, ready_timeout, proc=proc)
            if not result.ready:
                raise BootFailure(result, _read_log_tail(log))
            origin = "{0.scheme}://{0.netloc}".format(urlsplit(url))
            yield origin
        finally:
            kill_tree(proc)
