#!/usr/bin/env python3
"""HarnessAI v2 — `/ha-smoke` 백엔드 (런타임 기동 검증, advisory 게이트).

검증 사다리의 최상단: test/lint/type 이 전부 통과해도 앱이 안 뜨는 산출물을
잡는다. 두 가지 probe 모드:
  - exit 모드: 명령이 exit 0 으로 끝나면 PASS (CLI/스크립트/`--help` 류)
  - url 모드:  명령을 백그라운드로 띄우고 URL readiness 폴링 (dev server 류),
               판정 후 프로세스 트리 정리
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "_ha_shared"))
from utils import (  # noqa: E402, I001
    assert_state,
    get_active_profiles,
    load_plan,
    record_verify,
    save_plan,
)

_OUTPUT_TAIL_CHARS = 4000


def _kill_tree(proc: subprocess.Popen) -> None:
    """프로세스와 자식 전부 종료 (dev server 가 자식 프로세스를 띄우는 케이스)."""
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


def _tail(text: str) -> str:
    return text[-_OUTPUT_TAIL_CHARS:]


def _probe_exit(cmd: str, cwd: Path, timeout: int) -> dict:
    try:
        r = subprocess.run(
            cmd,
            shell=True,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        out = e.stdout if isinstance(e.stdout, str) else ""
        return {
            "passed": False,
            "mode": "exit",
            "detail": f"타임아웃 {timeout}s 초과",
            "output_tail": _tail(out),
        }
    output = (r.stdout or "") + (r.stderr or "")
    if r.returncode == 0:
        return {"passed": True, "mode": "exit", "detail": "exit code 0", "output_tail": _tail(output)}
    return {
        "passed": False,
        "mode": "exit",
        "detail": f"exit code {r.returncode}",
        "output_tail": _tail(output),
    }


def _probe_url(cmd: str, cwd: Path, url: str, ready_timeout: int) -> dict:
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
            deadline = time.monotonic() + ready_timeout
            while time.monotonic() < deadline:
                rc = proc.poll()
                if rc is not None:
                    return {
                        "passed": False,
                        "mode": "url",
                        "detail": f"프로세스가 ready 전에 종료 (exit code {rc})",
                        "output_tail": _read_log_tail(log),
                    }
                try:
                    with urllib.request.urlopen(url, timeout=2) as resp:
                        status = resp.status
                    if 200 <= status < 400:
                        return {
                            "passed": True,
                            "mode": "url",
                            "detail": f"HTTP {status} @ {url}",
                            "output_tail": _read_log_tail(log),
                        }
                    return {
                        "passed": False,
                        "mode": "url",
                        "detail": f"HTTP {status} @ {url}",
                        "output_tail": _read_log_tail(log),
                    }
                except urllib.error.HTTPError as e:
                    return {
                        "passed": False,
                        "mode": "url",
                        "detail": f"HTTP {e.code} @ {url}",
                        "output_tail": _read_log_tail(log),
                    }
                except (urllib.error.URLError, OSError):
                    time.sleep(0.5)  # 아직 안 떴음 — 재시도
            return {
                "passed": False,
                "mode": "url",
                "detail": f"{ready_timeout}s 내 {url} 미응답 (ready 타임아웃 초과)",
                "output_tail": _read_log_tail(log),
            }
        finally:
            _kill_tree(proc)


def _read_log_tail(log) -> str:
    try:
        log.flush()
        log.seek(0)
        return _tail(log.read())
    except OSError:
        return ""


def run_probe(
    cmd: str,
    *,
    cwd: Path,
    url: str | None = None,
    timeout: int = 120,
    ready_timeout: int = 60,
) -> dict:
    """smoke 명령 실행 → {"passed", "mode", "detail", "output_tail"}.

    url 이 주어지면 url 모드 (백그라운드 기동 + readiness 폴링 + 트리 킬),
    아니면 exit 모드 (exit 0 = PASS).
    """
    if url:
        return _probe_url(cmd, Path(cwd), url, ready_timeout)
    return _probe_exit(cmd, Path(cwd), timeout)


def cmd_prepare(args: argparse.Namespace) -> int:
    plan, plan_path, project = load_plan()
    assert_state(plan, ["verified", "reviewed"], "/ha-smoke")

    profiles = get_active_profiles(plan, project)
    output = {
        "project": str(project),
        "state": plan.pipeline.current_step,
        "platform": platform.system().lower(),
        "profiles": [
            {
                "id": p.id,
                "path": plan.profiles[i].path if i < len(plan.profiles) else ".",
                "cwd": str(project / plan.profiles[i].path)
                if i < len(plan.profiles) and plan.profiles[i].path != "."
                else str(project),
                "smoke": p.toolchain.smoke,
            }
            for i, p in enumerate(profiles)
        ],
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    result = run_probe(
        args.command,
        cwd=Path(args.cwd),
        url=args.url or None,
        timeout=args.timeout,
        ready_timeout=args.ready_timeout,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


def cmd_record(args: argparse.Namespace) -> int:
    plan, plan_path, project = load_plan()
    assert_state(plan, ["verified", "reviewed"], "/ha-smoke record")

    passed = args.passed.lower() in ("true", "1", "yes", "y")
    record_verify(plan, step="smoke", passed=passed, summary=args.summary)
    # advisory 게이트 — 상태 전이 없음 (FAIL 이어도 verified/reviewed 유지,
    # 후속 판단은 SKILL.md 가이드의 LLM/사용자 몫)
    save_plan(plan, plan_path)

    output = {
        "passed": passed,
        "summary": args.summary,
        "current_step": plan.pipeline.current_step,
        "verify_history_count": len(plan.verify_history),
        "next": "/ha-ship" if passed else "/ha-build <T-ID> (기동 실패 원인 수정 후 재검증)",
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="ha-smoke")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prepare")
    p = sub.add_parser("probe")
    p.add_argument("--command", required=True, help="smoke 명령 (shell)")
    p.add_argument("--cwd", required=True)
    p.add_argument("--url", default="", help="지정 시 url 모드 (dev server readiness 폴링)")
    p.add_argument("--timeout", type=int, default=120, help="exit 모드 타임아웃 (초)")
    p.add_argument("--ready-timeout", type=int, default=60, help="url 모드 readiness 타임아웃 (초)")
    r = sub.add_parser("record")
    r.add_argument("--passed", required=True)
    r.add_argument("--summary", required=True)
    args = parser.parse_args()
    if args.cmd == "prepare":
        return cmd_prepare(args)
    if args.cmd == "probe":
        return cmd_probe(args)
    return cmd_record(args)


if __name__ == "__main__":
    sys.exit(main())
