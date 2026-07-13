"""ha-accept 시나리오 러너 회귀 테스트 — dotted path 게터/캡처·치환/http·cli 스텝/record.

외부 네트워크 없이 http.server(ThreadingHTTPServer, 127.0.0.1 임시 포트) 스텁으로
http kind 스텝을, sys.executable 페이크 명령으로 cli kind 스텝을 검증한다.
발명된 PASS 가 없는지 (미정의 변수 참조 → FAIL, 타임아웃 → FAIL) 를 특히 확인한다.
"""

from __future__ import annotations

import importlib.util
import json
import socket
import subprocess
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HA_ACCEPT_RUN = REPO_ROOT / "skills" / "ha-accept" / "run.py"


@pytest.fixture(scope="module")
def ha_accept() -> ModuleType:
    loader = SourceFileLoader("ha_accept_runner", str(HA_ACCEPT_RUN))
    spec = importlib.util.spec_from_loader("ha_accept_runner", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_accept_runner"] = mod
    loader.exec_module(mod)
    return mod


# ── _get_dotted ──────────────────────────────────────────────────────────


def test_get_dotted_simple_key(ha_accept) -> None:
    assert ha_accept._get_dotted({"id": 42}, "id") == 42


def test_get_dotted_nested_dict(ha_accept) -> None:
    assert ha_accept._get_dotted({"data": {"id": 7}}, "data.id") == 7


def test_get_dotted_list_index(ha_accept) -> None:
    assert ha_accept._get_dotted({"items": [{"name": "a"}, {"name": "b"}]}, "items.1.name") == "b"


def test_get_dotted_missing_key_raises(ha_accept) -> None:
    with pytest.raises((KeyError, IndexError, TypeError, ValueError)):
        ha_accept._get_dotted({"id": 1}, "missing")


def test_get_dotted_index_out_of_range_raises(ha_accept) -> None:
    with pytest.raises((KeyError, IndexError, TypeError, ValueError)):
        ha_accept._get_dotted({"items": [1]}, "items.5")


# ── _substitute — {var} 치환 ─────────────────────────────────────────────


def test_substitute_replaces_var_in_string(ha_accept) -> None:
    assert ha_accept._substitute("/api/todos/{todo_id}", {"todo_id": 42}) == "/api/todos/42"


def test_substitute_recurses_into_dict_and_list(ha_accept) -> None:
    value = {"title": "{name}", "tags": ["{name}", "static"]}
    result = ha_accept._substitute(value, {"name": "milk"})
    assert result == {"title": "milk", "tags": ["milk", "static"]}


def test_substitute_undefined_variable_raises(ha_accept) -> None:
    with pytest.raises(KeyError):
        ha_accept._substitute("/api/todos/{missing_var}", {})


# ── http kind — ThreadingHTTPServer 스텁 ────────────────────────────────


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _TodoHandler(BaseHTTPRequestHandler):
    """POST /api/todos 로 생성 → GET /api/todos/<id> 로 조회하는 최소 스텁."""

    _store: dict[int, dict] = {}
    _next_id = 1

    def _write_json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        payload = json.loads(raw)
        if self.path == "/api/todos":
            item = {"id": _TodoHandler._next_id, "title": payload.get("title"), "done": False}
            _TodoHandler._store[item["id"]] = item
            _TodoHandler._next_id += 1
            self._write_json(201, item)
            return
        self._write_json(404, {"error": "not found"})

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/api/todos/"):
            todo_id = int(self.path.rsplit("/", 1)[-1])
            item = _TodoHandler._store.get(todo_id)
            if item is None:
                self._write_json(404, {"error": "not found"})
                return
            self._write_json(200, item)
            return
        self._write_json(404, {"error": "not found"})

    def log_message(self, *a):
        pass


@pytest.fixture
def todo_server():
    _TodoHandler._store = {}
    _TodoHandler._next_id = 1
    port = _free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), _TodoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_run_http_scenario_captures_and_substitutes(ha_accept, todo_server) -> None:
    scenario = {
        "id": "A-001",
        "feature": "할일 추가",
        "kind": "http",
        "steps": [
            {
                "method": "POST",
                "path": "/api/todos",
                "json": {"title": "우유 사기"},
                "expect": {"status": 201},
                "capture": {"todo_id": "id"},
            },
            {
                "method": "GET",
                "path": "/api/todos/{todo_id}",
                "expect": {"status": 200, "json": {"done": False, "title": "우유 사기"}},
            },
        ],
    }
    result = ha_accept._run_http_scenario(scenario, todo_server)
    assert result["passed"] is True, result
    assert result["failed_step"] is None


def test_run_http_scenario_fails_on_status_mismatch(ha_accept, todo_server) -> None:
    scenario = {
        "id": "A-002",
        "feature": "x",
        "kind": "http",
        "steps": [
            {"method": "GET", "path": "/api/todos/999", "expect": {"status": 200}},
        ],
    }
    result = ha_accept._run_http_scenario(scenario, todo_server)
    assert result["passed"] is False
    assert result["failed_step"] == 1


def test_run_http_scenario_fails_on_json_mismatch(ha_accept, todo_server) -> None:
    scenario = {
        "id": "A-003",
        "feature": "x",
        "kind": "http",
        "steps": [
            {
                "method": "POST",
                "path": "/api/todos",
                "json": {"title": "우유"},
                "expect": {"status": 201, "json": {"done": True}},
            },
        ],
    }
    result = ha_accept._run_http_scenario(scenario, todo_server)
    assert result["passed"] is False
    assert result["failed_step"] == 1


def test_run_http_scenario_fails_on_undefined_variable(ha_accept, todo_server) -> None:
    scenario = {
        "id": "A-004",
        "feature": "x",
        "kind": "http",
        "steps": [
            {"method": "GET", "path": "/api/todos/{never_captured}", "expect": {"status": 200}},
        ],
    }
    result = ha_accept._run_http_scenario(scenario, todo_server)
    assert result["passed"] is False
    assert result["failed_step"] == 1
    assert "변수" in result["detail"]


# ── cli kind — sys.executable 페이크 ─────────────────────────────────────


def _py(code: str) -> str:
    return f'"{sys.executable}" -c "{code}"'


def test_run_cli_scenario_passes(ha_accept, tmp_path) -> None:
    scenario = {
        "id": "A-010",
        "feature": "x",
        "kind": "cli",
        "steps": [
            {
                # ASCII 전용 — Windows 콘솔 codepage 로 spawn 된 자식 프로세스의
                # 비-ASCII stdout 은 cp949 등으로 인코딩돼 부모의 utf-8 디코딩과
                # 어긋난다 (기존 ha-smoke 픽스처들도 동일 이유로 ASCII 만 사용).
                "run": _py("print('added')"),
                "expect": {"exit": 0, "stdout_contains": ["added"]},
            }
        ],
    }
    result = ha_accept._run_cli_scenario(scenario, tmp_path)
    assert result["passed"] is True, result


def test_run_cli_scenario_fails_on_exit_mismatch(ha_accept, tmp_path) -> None:
    scenario = {
        "id": "A-011",
        "feature": "x",
        "kind": "cli",
        "steps": [{"run": _py("import sys; sys.exit(1)"), "expect": {"exit": 0}}],
    }
    result = ha_accept._run_cli_scenario(scenario, tmp_path)
    assert result["passed"] is False
    assert result["failed_step"] == 1


def test_run_cli_scenario_fails_on_stdout_missing(ha_accept, tmp_path) -> None:
    scenario = {
        "id": "A-012",
        "feature": "x",
        "kind": "cli",
        "steps": [
            {"run": _py("print('ok')"), "expect": {"exit": 0, "stdout_contains": ["누락된문자열"]}}
        ],
    }
    result = ha_accept._run_cli_scenario(scenario, tmp_path)
    assert result["passed"] is False


def test_run_cli_scenario_handles_timeout(ha_accept, tmp_path, monkeypatch) -> None:
    scenario = {
        "id": "A-013",
        "feature": "x",
        "kind": "cli",
        "steps": [{"run": "slow-cmd", "expect": {"exit": 0}}],
    }

    def _raise_timeout(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 0))

    monkeypatch.setattr(ha_accept.subprocess, "run", _raise_timeout)

    result = ha_accept._run_cli_scenario(scenario, tmp_path)
    assert result["passed"] is False
    assert "타임아웃" in result["detail"]


# ── cmd_run — 프로파일 필터/부팅 실패/공허 통과 방지 ─────────────────────


def _cli_only_yaml(fake_cmd: str) -> str:
    # yaml.safe_dump — Windows 경로 백슬래시/따옴표가 섞인 fake_cmd 의 이스케이프를
    # 수동 템플릿 없이 안전하게 처리한다.
    import yaml

    return yaml.safe_dump(
        {
            "version": 1,
            "scenarios": [
                {
                    "id": "A-001",
                    "feature": "cli 출력",
                    "gwt": "Given 설치됨 / When 실행 / Then ok 출력",
                    "profile": "python-cli",
                    "kind": "cli",
                    "steps": [{"run": fake_cmd, "expect": {"exit": 0, "stdout_contains": ["ok"]}}],
                }
            ],
            "underivable": [],
        },
        allow_unicode=True,
    )


def _setup_run_project(ha_accept, monkeypatch, tmp_path: Path, yaml_text: str, profile_ids):
    docs = tmp_path / "docs"
    docs.mkdir()
    plan_path = docs / "harness-plan.md"
    plan_path.write_text("", encoding="utf-8")
    (docs / "acceptance.yaml").write_text(yaml_text, encoding="utf-8")
    plan = SimpleNamespace(profiles=[SimpleNamespace(id=pid, path=".") for pid in profile_ids])
    monkeypatch.setattr(ha_accept, "load_plan", lambda: (plan, plan_path, tmp_path))


def test_cmd_run_cli_only_passes(ha_accept, tmp_path, monkeypatch, capsys) -> None:
    yaml_text = _cli_only_yaml(_py("print('ok')"))
    _setup_run_project(ha_accept, monkeypatch, tmp_path, yaml_text, ["python-cli"])

    rc = ha_accept.cmd_run(
        SimpleNamespace(profile="python-cli", command="", url="", ready_timeout=1)
    )
    out = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert [r["passed"] for r in out["scenarios"]] == [True]


def test_cmd_run_fails_when_no_scenarios_match_profile(
    ha_accept, tmp_path, monkeypatch, capsys
) -> None:
    """--profile 오타 → 시나리오 0개 매칭이 공허 통과(exit 0)가 되면 안 된다."""
    yaml_text = _cli_only_yaml("echo ok")
    _setup_run_project(ha_accept, monkeypatch, tmp_path, yaml_text, ["python-cli"])

    rc = ha_accept.cmd_run(SimpleNamespace(profile="tpyo-cli", command="", url="", ready_timeout=1))

    assert rc == 2


def test_cmd_run_boot_failure_marks_all_scenarios_failed(
    ha_accept, tmp_path, monkeypatch, capsys
) -> None:
    """부팅 실패는 발명된 PASS 없이 전 시나리오 실행-불가 FAIL — 원인(HTTP status) 노출."""
    yaml_text = (
        "version: 1\n"
        "scenarios:\n"
        "  - id: A-001\n"
        '    feature: "할일 추가"\n'
        '    gwt: "Given / When / Then"\n'
        "    profile: fastapi\n"
        "    kind: http\n"
        "    steps:\n"
        "      - method: GET\n"
        "        path: /api/todos\n"
        "        expect: {status: 200}\n"
    )
    _setup_run_project(ha_accept, monkeypatch, tmp_path, yaml_text, ["fastapi"])

    @contextmanager
    def _boom(cmd, cwd, url, ready_timeout):
        raise ha_accept.BootFailure(
            SimpleNamespace(ready=False, exited=False, status=500, exit_code=None), "tail"
        )
        yield  # pragma: no cover

    monkeypatch.setattr(ha_accept, "booted_server", _boom)

    rc = ha_accept.cmd_run(
        SimpleNamespace(
            profile="fastapi", command="uvicorn app", url="http://127.0.0.1:9/", ready_timeout=1
        )
    )
    out = json.loads(capsys.readouterr().out)

    assert rc == 1
    assert [r["passed"] for r in out["scenarios"]] == [False]
    assert "부팅 실패" in out["scenarios"][0]["detail"]
    assert "500" in out["scenarios"][0]["detail"]


# ── record — plan monkeypatch ────────────────────────────────────────────


def test_cmd_record_appends_verify_history(ha_accept, tmp_path, monkeypatch, capsys) -> None:
    plan = SimpleNamespace(
        pipeline=SimpleNamespace(current_step="verified"),
        verify_history=[],
    )
    plan_path = tmp_path / "harness-plan.md"

    recorded: dict = {}

    def _fake_record_verify(p, *, step, passed, summary):
        recorded["step"] = step
        recorded["passed"] = passed
        recorded["summary"] = summary
        p.verify_history.append(SimpleNamespace(step=step, passed=passed, summary=summary))
        return p

    saved: list = []
    monkeypatch.setattr(ha_accept, "load_plan", lambda: (plan, plan_path, tmp_path))
    monkeypatch.setattr(ha_accept, "assert_state", lambda *a, **k: None)
    monkeypatch.setattr(ha_accept, "record_verify", _fake_record_verify)
    monkeypatch.setattr(ha_accept, "save_plan", lambda p, pp: saved.append((p, pp)))

    rc = ha_accept.cmd_record(SimpleNamespace(passed="true", summary="A-001 PASS"))
    out = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert recorded == {"step": "accept", "passed": True, "summary": "A-001 PASS"}
    assert saved == [(plan, plan_path)]
    assert out["passed"] is True
    assert out["current_step"] == "verified"
