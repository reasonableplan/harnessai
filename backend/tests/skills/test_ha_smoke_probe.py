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


def _routed_server(tmp_path: Path, routes: dict[str, int]) -> Path:
    """경로별 HTTP 상태를 돌려주는 결정론 서버 스크립트를 작성 (미정의 경로는 404)."""
    script = tmp_path / "srv.py"
    script.write_text(
        "import sys\n"
        "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
        f"ROUTES = {routes!r}\n"
        "class H(BaseHTTPRequestHandler):\n"
        "    def do_GET(self):\n"
        "        code = ROUTES.get(self.path, 404)\n"
        "        self.send_response(code)\n"
        "        self.end_headers()\n"
        "        self.wfile.write(b'x')\n"
        "    def log_message(self, *a):\n"
        "        pass\n"
        "HTTPServer(('127.0.0.1', int(sys.argv[1])), H).serve_forever()\n",
        encoding="utf-8",
    )
    return script


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


# ── 선언 엔드포인트 타격 (계층2 — 떠도 라우트 깨짐) ──────────────────────────


def test_declared_endpoints_all_ok(ha_smoke, tmp_path) -> None:
    """기동 PASS 후 선언 GET 엔드포인트가 전부 살아있으면 PASS (401 = 인증게이트, OK)."""
    port = _free_port()
    script = _routed_server(tmp_path, {"/": 200, "/api/items": 200, "/api/users": 401})
    cmd = f'"{sys.executable}" "{script}" {port}'
    r = ha_smoke.run_probe(
        cmd,
        cwd=tmp_path,
        url=f"http://127.0.0.1:{port}/",
        endpoints=["/api/items", "/api/users"],
        ready_timeout=30,
    )
    assert r["passed"] is True
    assert r["mode"] == "url"


def test_declared_endpoint_missing_fails(ha_smoke, tmp_path) -> None:
    """선언했지만 미등록(404) 엔드포인트 → FAIL + 경로/상태 보고."""
    port = _free_port()
    script = _routed_server(tmp_path, {"/": 200})
    cmd = f'"{sys.executable}" "{script}" {port}'
    r = ha_smoke.run_probe(
        cmd,
        cwd=tmp_path,
        url=f"http://127.0.0.1:{port}/",
        endpoints=["/api/items"],
        ready_timeout=30,
    )
    assert r["passed"] is False
    assert "/api/items" in r["detail"]
    assert "404" in r["detail"]


def test_declared_endpoint_5xx_fails(ha_smoke, tmp_path) -> None:
    """핸들러 크래시(5xx) → FAIL (root 는 200 이라 기존 게이트는 못 잡던 케이스)."""
    port = _free_port()
    script = _routed_server(tmp_path, {"/": 200, "/api/boom": 500})
    cmd = f'"{sys.executable}" "{script}" {port}'
    r = ha_smoke.run_probe(
        cmd,
        cwd=tmp_path,
        url=f"http://127.0.0.1:{port}/",
        endpoints=["/api/boom"],
        ready_timeout=30,
    )
    assert r["passed"] is False
    assert "/api/boom" in r["detail"]
    assert "500" in r["detail"]


def test_declared_path_param_endpoint_skipped(ha_smoke, tmp_path) -> None:
    """path 파라미터 엔드포인트는 실제 ID 없이 못 때리므로 v1 에서 skip → PASS."""
    port = _free_port()
    script = _routed_server(tmp_path, {"/": 200})  # /items/{id} 는 404 가 되겠지만
    cmd = f'"{sys.executable}" "{script}" {port}'
    r = ha_smoke.run_probe(
        cmd,
        cwd=tmp_path,
        url=f"http://127.0.0.1:{port}/",
        endpoints=["/items/{id}", "/users/:uid"],
        ready_timeout=30,
    )
    assert r["passed"] is True


def test_declared_endpoints_report_all_broken(ha_smoke, tmp_path) -> None:
    """여러 엔드포인트 중 깨진 것을 모두 detail 에 나열."""
    port = _free_port()
    script = _routed_server(tmp_path, {"/": 200, "/ok": 200, "/boom": 500})
    cmd = f'"{sys.executable}" "{script}" {port}'
    r = ha_smoke.run_probe(
        cmd,
        cwd=tmp_path,
        url=f"http://127.0.0.1:{port}/",
        endpoints=["/ok", "/missing", "/boom"],
        ready_timeout=30,
    )
    assert r["passed"] is False
    assert "/missing" in r["detail"]
    assert "/boom" in r["detail"]
    assert "/ok" not in r["detail"]  # 살아있는 건 보고 안 함


# ── suggest_smoke_command (dogfood #8: toolchain.smoke 미설정 시 자동 제안) ──


def test_suggest_smoke_finds_main_under_src(ha_smoke, tmp_path: Path) -> None:
    pkg = tmp_path / "src" / "mypkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").touch()
    (pkg / "__main__.py").touch()
    assert ha_smoke.suggest_smoke_command(tmp_path) == "python -m mypkg --help"


def test_suggest_smoke_finds_main_flat_layout(ha_smoke, tmp_path: Path) -> None:
    pkg = tmp_path / "tool"
    pkg.mkdir()
    (pkg / "__init__.py").touch()
    (pkg / "__main__.py").touch()
    assert ha_smoke.suggest_smoke_command(tmp_path) == "python -m tool --help"


def test_suggest_smoke_none_when_no_runnable_package(ha_smoke, tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "lib").mkdir()
    (tmp_path / "src" / "lib" / "__init__.py").touch()  # __main__.py 없음 → 제안 없음
    assert ha_smoke.suggest_smoke_command(tmp_path) is None
