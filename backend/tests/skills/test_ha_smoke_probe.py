"""ha-smoke run_probe 단위 테스트 — 런타임 기동 검증 게이트의 결정론 코어.

exit 모드 (명령이 exit 0 으로 끝나야 PASS) / url 모드 (dev server 를 띄우고
readiness 폴링 후 프로세스 트리 정리). 검증 사다리의 최상단 — test/lint/type
이 전부 통과해도 앱이 안 뜨는 산출물을 잡는다 (feedback_runtime_breakage).
"""

from __future__ import annotations

import importlib.util
import socket
import sys
import time
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def ha_smoke() -> ModuleType:
    loader = SourceFileLoader("ha_smoke_run", str(REPO_ROOT / "skills" / "ha-smoke" / "run.py"))
    spec = importlib.util.spec_from_loader("ha_smoke_run", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_smoke_run"] = mod
    loader.exec_module(mod)
    return mod


def _py(code: str) -> str:
    """현재 인터프리터로 한 줄 파이썬을 실행하는 셸 명령."""
    return f'"{sys.executable}" -c "{code}"'


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ── exit 모드 ──────────────────────────────────────────────────────────────


def test_exit_mode_pass(ha_smoke, tmp_path) -> None:
    r = ha_smoke.run_probe(_py("print(42)"), cwd=tmp_path)
    assert r["passed"] is True
    assert r["mode"] == "exit"


def test_exit_mode_fail(ha_smoke, tmp_path) -> None:
    r = ha_smoke.run_probe(_py("import sys; sys.exit(3)"), cwd=tmp_path)
    assert r["passed"] is False
    assert "3" in r["detail"]


def test_exit_mode_timeout(ha_smoke, tmp_path) -> None:
    r = ha_smoke.run_probe(_py("import time; time.sleep(30)"), cwd=tmp_path, timeout=2)
    assert r["passed"] is False
    assert "초과" in r["detail"]


# ── url 모드 ───────────────────────────────────────────────────────────────


def test_url_mode_ready(ha_smoke, tmp_path) -> None:
    """dev server 가 뜨면 PASS — 이후 프로세스 정리."""
    port = _free_port()
    cmd = f'"{sys.executable}" -m http.server {port} --bind 127.0.0.1'
    r = ha_smoke.run_probe(cmd, cwd=tmp_path, url=f"http://127.0.0.1:{port}/", ready_timeout=30)
    assert r["passed"] is True
    assert r["mode"] == "url"
    assert "200" in r["detail"]


def test_url_mode_process_died_early(ha_smoke, tmp_path) -> None:
    """서버가 ready 전에 죽으면 FAIL + exit code 보고 (크래시 감지)."""
    port = _free_port()
    r = ha_smoke.run_probe(
        _py("import sys; sys.exit(5)"),
        cwd=tmp_path,
        url=f"http://127.0.0.1:{port}/",
        ready_timeout=10,
    )
    assert r["passed"] is False
    assert "종료" in r["detail"]


def test_url_mode_never_ready_kills_process(ha_smoke, tmp_path) -> None:
    """ready-timeout 내 미응답 → FAIL, 자식 프로세스를 기다리지 않고 트리 킬."""
    port = _free_port()
    start = time.monotonic()
    r = ha_smoke.run_probe(
        _py("import time; time.sleep(60)"),
        cwd=tmp_path,
        url=f"http://127.0.0.1:{port}/",
        ready_timeout=2,
    )
    elapsed = time.monotonic() - start
    assert r["passed"] is False
    assert elapsed < 30  # sleep(60) 종료를 기다리지 않음
