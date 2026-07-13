"""_ha_shared/runtime.py 회귀 테스트 — booted_server 정상/실패 경로.

ha-smoke 의 `_kill_tree` + readiness 폴링을 추출한 공용 모듈
(acceptance-layer-design.md §4). ha-accept 의 http kind 시나리오 러너가
이 contextmanager 로 프로파일을 기동한다 — "부팅 실패 = 시나리오 실행
불가"를 BootFailure 예외로 명확히 구분해야 한다.
"""

from __future__ import annotations

import importlib.util
import socket
import subprocess
import sys
import time
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def runtime() -> ModuleType:
    loader = SourceFileLoader(
        "ha_shared_runtime", str(REPO_ROOT / "skills" / "_ha_shared" / "runtime.py")
    )
    spec = importlib.util.spec_from_loader("ha_shared_runtime", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_shared_runtime"] = mod
    loader.exec_module(mod)
    return mod


def _py(code: str) -> str:
    """현재 인터프리터로 한 줄 파이썬을 실행하는 셸 명령."""
    return f'"{sys.executable}" -c "{code}"'


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ── wait_ready ────────────────────────────────────────────────────────────


def test_wait_ready_success(runtime, tmp_path) -> None:
    port = _free_port()
    cmd = f'"{sys.executable}" -m http.server {port} --bind 127.0.0.1'
    proc = subprocess.Popen(cmd, shell=True, cwd=str(tmp_path))
    try:
        result = runtime.wait_ready(f"http://127.0.0.1:{port}/", 30, proc=proc)
        assert result.ready is True
        assert result.status == 200
    finally:
        runtime.kill_tree(proc)


def test_wait_ready_detects_process_exit(runtime, tmp_path) -> None:
    port = _free_port()
    proc = subprocess.Popen(_py("import sys; sys.exit(7)"), shell=True, cwd=str(tmp_path))
    try:
        result = runtime.wait_ready(f"http://127.0.0.1:{port}/", 10, proc=proc)
        assert result.ready is False
        assert result.exited is True
        assert result.exit_code == 7
    finally:
        runtime.kill_tree(proc)


def test_wait_ready_timeout(runtime, tmp_path) -> None:
    port = _free_port()
    proc = subprocess.Popen(_py("import time; time.sleep(30)"), shell=True, cwd=str(tmp_path))
    try:
        start = time.monotonic()
        result = runtime.wait_ready(f"http://127.0.0.1:{port}/", 2, proc=proc)
        elapsed = time.monotonic() - start
        assert result.ready is False
        assert result.exited is False
        assert result.status is None
        assert elapsed < 10
    finally:
        runtime.kill_tree(proc)


# ── booted_server — 정상 경로 ────────────────────────────────────────────


def test_booted_server_yields_origin_and_tears_down(runtime, tmp_path) -> None:
    port = _free_port()
    cmd = f'"{sys.executable}" -m http.server {port} --bind 127.0.0.1'

    with runtime.booted_server(cmd, tmp_path, f"http://127.0.0.1:{port}/", 30) as origin:
        assert origin == f"http://127.0.0.1:{port}"

    # 트리 정리 확인 — 같은 포트를 즉시 재바인딩 가능해야 함 (이전 프로세스가 살아있으면 실패)
    with socket.socket() as s:
        s.bind(("127.0.0.1", port))


# ── booted_server — 실패 경로 (BootFailure) ──────────────────────────────


def test_booted_server_raises_on_process_exit(runtime, tmp_path) -> None:
    port = _free_port()
    cmd = _py("import sys; sys.exit(3)")

    with (
        pytest.raises(runtime.BootFailure) as exc_info,
        runtime.booted_server(cmd, tmp_path, f"http://127.0.0.1:{port}/", 10),
    ):
        pytest.fail("부팅 실패 시 with 블록 본문에 진입하면 안 됨")

    assert exc_info.value.result.exited is True
    assert exc_info.value.result.exit_code == 3


def test_booted_server_raises_on_ready_timeout(runtime, tmp_path) -> None:
    port = _free_port()
    cmd = _py("import time; time.sleep(30)")

    start = time.monotonic()
    with (
        pytest.raises(runtime.BootFailure) as exc_info,
        runtime.booted_server(cmd, tmp_path, f"http://127.0.0.1:{port}/", 2),
    ):
        pytest.fail("ready 타임아웃 시 with 블록 본문에 진입하면 안 됨")
    elapsed = time.monotonic() - start

    assert exc_info.value.result.ready is False
    assert exc_info.value.result.exited is False
    assert elapsed < 10  # sleep(30) 종료를 기다리지 않고 트리 킬
