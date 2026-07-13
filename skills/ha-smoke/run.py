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
import platform
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).parent.parent / "_ha_shared"))
from runtime import kill_tree, wait_ready  # noqa: E402
from utils import (  # noqa: E402, I001
    assert_state,
    get_active_profiles,
    load_plan,
    record_verify,
    save_plan,
)

_OUTPUT_TAIL_CHARS = 4000


def suggest_smoke_command(cwd: Path) -> str | None:
    """Suggest a runtime-launch command when toolchain.smoke is unset (dogfood #8).

    Scans cwd and cwd/src for a runnable Python package (a dir with both
    __init__.py and __main__.py) and returns ``python -m <pkg> --help`` — the
    natural "does the app start" probe for a CLI. Returns None when no runnable
    package is found (non-Python or library-only), so callers fall back to
    asking the user rather than guessing wrong.
    """
    for base in (cwd, cwd / "src"):
        if not base.is_dir():
            continue
        try:
            children = sorted(p for p in base.iterdir() if p.is_dir())
        except OSError:
            continue
        for pkg in children:
            if (pkg / "__init__.py").is_file() and (pkg / "__main__.py").is_file():
                return f"python -m {pkg.name} --help"
    return None


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


def _invalid_endpoints(endpoints: list[str]) -> list[str]:
    """경로가 아닌 --endpoint 값 (절대 경로가 아님) 을 골라낸다.

    Git Bash(MSYS) 는 `--endpoint /api/items` 를 `C:/Program Files/Git/api/items` 로
    변환한다. 이 값은 ':' 를 포함해 아래 path 파라미터 skip 에 걸리므로, 검사 0건인
    채 PASS 가 나 계층2 가 무음으로 무력화된다 (dogfood D-6). 경로가 아니면 기동
    전에 하드 FAIL 시킨다.
    """
    return [e for e in endpoints if not e.startswith("/")]


def _check_endpoints(origin: str, endpoints: list[str]) -> tuple[list[str], int, int]:
    """기동한 서버의 선언 GET 엔드포인트를 타격 → (깨진 것, 타격 개수, skip 개수).

    404(미등록) / 5xx(핸들러 크래시) 만 깨짐으로 본다. 2xx/3xx/401/403/422 등은
    "라우트가 존재하고 핸들러가 도달함" 이므로 OK. path 파라미터({id}, :id) 는
    실제 값 없이 못 때리므로 skip — skip 개수는 호출측이 detail 에 노출한다.
    """
    broken: list[str] = []
    probed = 0
    skipped = 0
    for path in endpoints:
        if "{" in path or ":" in path:
            skipped += 1  # path 파라미터 — 실제 값 필요, v1 skip
            continue
        probed += 1
        try:
            with urllib.request.urlopen(origin + path, timeout=3) as resp:
                code = resp.status
        except urllib.error.HTTPError as e:
            code = e.code
        except (urllib.error.URLError, OSError) as e:
            broken.append(f"GET {path} (연결 실패: {e})")
            continue
        if code == 404 or code >= 500:
            broken.append(f"GET {path} ({code})")
    return broken, probed, skipped


def _probe_url(
    cmd: str, cwd: Path, url: str, ready_timeout: int, endpoints: list[str] | None = None
) -> dict:
    if endpoints:
        invalid = _invalid_endpoints(endpoints)
        if invalid:
            return {
                "passed": False,
                "mode": "url",
                "detail": (
                    "부적격 --endpoint (경로는 '/' 로 시작해야 함): "
                    + ", ".join(invalid)
                    + " — Git Bash 는 /api/x 를 Windows 경로로 변환한다. "
                    "MSYS_NO_PATHCONV=1 을 앞에 붙여 재실행."
                ),
                "output_tail": "",
            }

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
                if result.exited:
                    detail = f"프로세스가 ready 전에 종료 (exit code {result.exit_code})"
                elif result.status is not None:
                    detail = f"HTTP {result.status} @ {url}"
                else:
                    detail = f"{ready_timeout}s 내 {url} 미응답 (ready 타임아웃 초과)"
                return {
                    "passed": False,
                    "mode": "url",
                    "detail": detail,
                    "output_tail": _read_log_tail(log),
                }
            status = result.status
            if endpoints:
                origin = "{0.scheme}://{0.netloc}".format(urlsplit(url))
                broken, probed, skipped = _check_endpoints(origin, endpoints)
                if broken:
                    return {
                        "passed": False,
                        "mode": "url",
                        "detail": (
                            f"기동 OK (HTTP {status} @ {url}) 이나 선언 "
                            f"엔드포인트 깨짐: " + ", ".join(broken)
                        ),
                        "output_tail": _read_log_tail(log),
                    }
                # 타격/skip 개수를 항상 노출 — "0개 OK" 가 성공처럼 읽히면 안 된다.
                return {
                    "passed": True,
                    "mode": "url",
                    "detail": (
                        f"HTTP {status} @ {url}; 선언 GET 엔드포인트 {probed}개 OK "
                        f"(파라미터 경로 skip {skipped}개)"
                    ),
                    "output_tail": _read_log_tail(log),
                }
            return {
                "passed": True,
                "mode": "url",
                "detail": f"HTTP {status} @ {url}",
                "output_tail": _read_log_tail(log),
            }
        finally:
            kill_tree(proc)


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
    endpoints: list[str] | None = None,
    timeout: int = 120,
    ready_timeout: int = 60,
) -> dict:
    """smoke 명령 실행 → {"passed", "mode", "detail", "output_tail"}.

    url 이 주어지면 url 모드 (백그라운드 기동 + readiness 폴링 + 트리 킬),
    아니면 exit 모드 (exit 0 = PASS). url 모드에서 endpoints 가 주어지면 기동 후
    선언 GET 엔드포인트를 타격해 404/5xx (떠도 라우트 깨짐) 를 잡는다.
    """
    if url:
        return _probe_url(cmd, Path(cwd), url, ready_timeout, endpoints)
    return _probe_exit(cmd, Path(cwd), timeout)


def _profile_smoke_entry(profile: object, rel_path: str, project: Path) -> dict:
    """Build the per-profile prepare entry, suggesting a smoke command when unset."""
    cwd = project / rel_path if rel_path != "." else project
    smoke = getattr(getattr(profile, "toolchain", None), "smoke", None)
    entry = {
        "id": getattr(profile, "id", ""),
        "path": rel_path,
        "cwd": str(cwd),
        "smoke": smoke,
    }
    if not smoke:
        # toolchain.smoke 미설정 — 실행 가능 패키지에서 기동 명령 제안 (#8)
        entry["smoke_suggested"] = suggest_smoke_command(cwd)
    return entry


def cmd_prepare(args: argparse.Namespace) -> int:
    plan, plan_path, project = load_plan()
    assert_state(plan, ["verified", "reviewed"], "/ha-smoke")

    profiles = get_active_profiles(plan, project)
    output = {
        "project": str(project),
        "state": plan.pipeline.current_step,
        "platform": platform.system().lower(),
        "profiles": [
            _profile_smoke_entry(
                p,
                plan.profiles[i].path if i < len(plan.profiles) else ".",
                project,
            )
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
        endpoints=args.endpoint or None,
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
        "next": "/ha-accept" if passed else "/ha-build <T-ID> (기동 실패 원인 수정 후 재검증)",
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
    p.add_argument(
        "--endpoint",
        action="append",
        default=[],
        help="url 모드: 기동 후 타격할 선언 GET 경로 (반복 가능, 예: --endpoint /api/users)",
    )
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
