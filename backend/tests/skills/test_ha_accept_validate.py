"""ha-accept validate 회귀 테스트 — acceptance.yaml 스키마/교차 검증/커버리지.

BLOCK 대상(스키마 위반, skeleton 미선언 엔드포인트 참조, 비활성 프로파일 참조)과
advisory 대상(커버리지 구멍)을 구분한다. 좋은 파일은 통과, path 파라미터는
세그먼트 수준으로 비교({todo_id} ↔ {id} 매칭)한다.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HA_ACCEPT_RUN = REPO_ROOT / "skills" / "ha-accept" / "run.py"


@pytest.fixture(scope="module")
def ha_accept() -> ModuleType:
    loader = SourceFileLoader("ha_accept_validate", str(HA_ACCEPT_RUN))
    spec = importlib.util.spec_from_loader("ha_accept_validate", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_accept_validate"] = mod
    loader.exec_module(mod)
    return mod


def _good_scenario(**overrides) -> dict:
    base = {
        "id": "A-001",
        "feature": "할일 추가",
        "gwt": "Given 빈 목록 / When 추가 / Then 1건 표시",
        "profile": "fastapi",
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
                "expect": {"status": 200, "json": {"done": False}},
            },
        ],
    }
    base.update(overrides)
    return base


def _good_data(**overrides) -> dict:
    base = {"version": 1, "scenarios": [_good_scenario()], "underivable": []}
    base.update(overrides)
    return base


_DECLARED = frozenset(
    {("POST", "/api/todos"), ("GET", "/api/todos/{id}"), ("DELETE", "/api/todos/{id}")}
)
_ACTIVE_PROFILES = frozenset({"fastapi", "python-cli"})


# ── _validate_schema — 단위 테스트 ──────────────────────────────────────


def test_schema_accepts_well_formed_data(ha_accept) -> None:
    assert ha_accept._validate_schema(_good_data()) == []


def test_schema_blocks_bad_version(ha_accept) -> None:
    violations = ha_accept._validate_schema(_good_data(version=2))
    assert any(v.kind == "bad_version" for v in violations)


def test_schema_blocks_duplicate_id(ha_accept) -> None:
    data = _good_data(scenarios=[_good_scenario(id="A-001"), _good_scenario(id="A-001")])
    violations = ha_accept._validate_schema(data)
    assert any(v.kind == "duplicate_id" for v in violations)


def test_schema_blocks_bad_id_format(ha_accept) -> None:
    data = _good_data(scenarios=[_good_scenario(id="A-1")])
    violations = ha_accept._validate_schema(data)
    assert any(v.kind == "bad_id" for v in violations)


@pytest.mark.parametrize("field", ["feature", "gwt", "profile"])
def test_schema_blocks_missing_required_field(ha_accept, field) -> None:
    data = _good_data(scenarios=[_good_scenario(**{field: ""})])
    violations = ha_accept._validate_schema(data)
    assert any(v.kind == "missing_field" for v in violations)


def test_schema_blocks_bad_kind(ha_accept) -> None:
    data = _good_data(scenarios=[_good_scenario(kind="browser")])
    violations = ha_accept._validate_schema(data)
    assert any(v.kind == "bad_kind" for v in violations)


def test_schema_blocks_http_step_missing_method(ha_accept) -> None:
    scenario = _good_scenario(steps=[{"path": "/api/todos", "expect": {"status": 201}}])
    violations = ha_accept._validate_schema(_good_data(scenarios=[scenario]))
    assert any(v.kind == "missing_field" and "method" in v.detail for v in violations)


def test_schema_blocks_http_step_missing_path(ha_accept) -> None:
    scenario = _good_scenario(steps=[{"method": "GET", "expect": {"status": 200}}])
    violations = ha_accept._validate_schema(_good_data(scenarios=[scenario]))
    assert any(v.kind == "missing_field" and "path" in v.detail for v in violations)


def test_schema_blocks_cli_step_missing_run(ha_accept) -> None:
    scenario = _good_scenario(kind="cli", profile="python-cli", steps=[{"expect": {"exit": 0}}])
    violations = ha_accept._validate_schema(_good_data(scenarios=[scenario]))
    assert any(v.kind == "missing_field" and "run" in v.detail for v in violations)


def test_schema_accepts_cli_scenario(ha_accept) -> None:
    scenario = _good_scenario(
        id="A-002",
        kind="cli",
        profile="python-cli",
        steps=[
            {"run": "python -m app add 우유", "expect": {"exit": 0, "stdout_contains": ["추가"]}}
        ],
    )
    assert ha_accept._validate_schema(_good_data(scenarios=[scenario])) == []


def test_schema_blocks_unknown_expect_key(ha_accept) -> None:
    scenario = _good_scenario(
        steps=[{"method": "GET", "path": "/api/todos", "expect": {"body": "x"}}]
    )
    violations = ha_accept._validate_schema(_good_data(scenarios=[scenario]))
    assert any(v.kind == "bad_expect_key" for v in violations)


def test_schema_blocks_cli_expect_key_on_http_step(ha_accept) -> None:
    """http 스텝의 exit/stdout_contains 는 러너가 조용히 무시 — 공허 단언 차단."""
    scenario = _good_scenario(
        steps=[{"method": "GET", "path": "/api/todos", "expect": {"exit": 0}}]
    )
    violations = ha_accept._validate_schema(_good_data(scenarios=[scenario]))
    assert any(v.kind == "bad_expect_key" for v in violations)


def test_schema_blocks_http_expect_key_on_cli_step(ha_accept) -> None:
    """cli 스텝의 status/json 도 동일 — kind 별 허용 expect 키만 통과."""
    scenario = _good_scenario(
        kind="cli", profile="python-cli", steps=[{"run": "echo hi", "expect": {"status": 200}}]
    )
    violations = ha_accept._validate_schema(_good_data(scenarios=[scenario]))
    assert any(v.kind == "bad_expect_key" for v in violations)


def test_schema_blocks_non_string_capture_value(ha_accept) -> None:
    scenario = _good_scenario(
        steps=[
            {
                "method": "POST",
                "path": "/api/todos",
                "expect": {"status": 201},
                "capture": {"todo_id": 123},
            }
        ]
    )
    violations = ha_accept._validate_schema(_good_data(scenarios=[scenario]))
    assert any(v.kind == "bad_capture_value" for v in violations)


def test_schema_blocks_empty_steps(ha_accept) -> None:
    scenario = _good_scenario(steps=[])
    violations = ha_accept._validate_schema(_good_data(scenarios=[scenario]))
    assert any(v.kind == "missing_steps" for v in violations)


# ── _validate_cross — 단위 테스트 ───────────────────────────────────────


def test_cross_passes_when_endpoint_declared(ha_accept) -> None:
    violations = ha_accept._validate_cross(_good_data(), _DECLARED, _ACTIVE_PROFILES)
    assert violations == []


def test_cross_blocks_undeclared_endpoint(ha_accept) -> None:
    scenario = _good_scenario(
        steps=[{"method": "GET", "path": "/api/ghost", "expect": {"status": 200}}]
    )
    violations = ha_accept._validate_cross(
        _good_data(scenarios=[scenario]), _DECLARED, _ACTIVE_PROFILES
    )
    assert any(v.kind == "endpoint_not_declared" for v in violations)


def test_cross_matches_path_param_by_segment(ha_accept) -> None:
    """시나리오의 {todo_id} 와 skeleton 선언의 {id} 는 세그먼트 위치가 같으면 매칭."""
    scenario = _good_scenario(
        steps=[{"method": "GET", "path": "/api/todos/{todo_id}", "expect": {"status": 200}}]
    )
    violations = ha_accept._validate_cross(
        _good_data(scenarios=[scenario]), _DECLARED, _ACTIVE_PROFILES
    )
    assert violations == []


def test_cross_blocks_unknown_profile(ha_accept) -> None:
    scenario = _good_scenario(profile="nextjs")
    violations = ha_accept._validate_cross(
        _good_data(scenarios=[scenario]), _DECLARED, _ACTIVE_PROFILES
    )
    assert any(v.kind == "unknown_profile" for v in violations)


def test_cross_skips_endpoint_check_for_cli_scenarios(ha_accept) -> None:
    scenario = _good_scenario(
        kind="cli", profile="python-cli", steps=[{"run": "echo hi", "expect": {"exit": 0}}]
    )
    violations = ha_accept._validate_cross(
        _good_data(scenarios=[scenario]), _DECLARED, _ACTIVE_PROFILES
    )
    assert violations == []


# ── _extract_declared_endpoints / _extract_features 재사용 (교차 검증 입력) ──


def test_extract_declared_endpoints_from_skeleton(ha_accept) -> None:
    skel = (
        "## 3. HTTP API\n\n"
        "| method | path |\n|---|---|\n"
        "| `GET /api/todos` | 목록 |\n"
        "| `POST /api/todos` | 추가 |\n"
    )
    endpoints = ha_accept._extract_declared_endpoints(skel)
    assert ("GET", "/api/todos") in endpoints
    assert ("POST", "/api/todos") in endpoints


# ── cmd_validate — 통합 테스트 ───────────────────────────────────────────

_SKEL_TEXT = (
    "## 2. 기능 요구사항\n\n"
    "### 확정 기능 (사용자 선택 결과 — MVP Phase 1)\n\n"
    "- [x] 할일 추가\n"
    "  - 수용 기준:\n"
    "    - Given 빈 목록 / When 추가 / Then 1건 표시\n"
    "- [x] 할일 삭제\n"
    "  - 수용 기준:\n"
    "    - Given 1건 있음 / When 삭제 / Then 제거됨\n\n"
    "## 3. HTTP API\n\n"
    "| method | path |\n|---|---|\n"
    "| `POST /api/todos` | 추가 |\n"
    "| `GET /api/todos/{id}` | 단건 |\n"
    "| `DELETE /api/todos/{id}` | 삭제 |\n"
)


def _setup_project(tmp_path: Path, acceptance_yaml_text: str) -> tuple[Path, Path]:
    docs = tmp_path / "docs"
    docs.mkdir()
    plan_path = docs / "harness-plan.md"
    plan_path.write_text("", encoding="utf-8")
    (docs / "skeleton.md").write_text(_SKEL_TEXT, encoding="utf-8")
    (docs / "acceptance.yaml").write_text(acceptance_yaml_text, encoding="utf-8")
    return plan_path, docs


def _patch_load_plan(ha_accept, monkeypatch, tmp_path: Path, plan_path: Path, profile_ids) -> None:
    plan = SimpleNamespace(profiles=[SimpleNamespace(id=pid, path=".") for pid in profile_ids])
    monkeypatch.setattr(ha_accept, "load_plan", lambda: (plan, plan_path, tmp_path))


_GOOD_YAML = """\
version: 1
scenarios:
  - id: A-001
    feature: "할일 추가"
    gwt: "Given 빈 목록 / When 추가 / Then 1건 표시"
    profile: fastapi
    kind: http
    steps:
      - method: POST
        path: /api/todos
        json: {title: "우유"}
        expect: {status: 201}
        capture: {todo_id: id}
      - method: GET
        path: /api/todos/{todo_id}
        expect: {status: 200}
underivable: []
"""


def test_cmd_validate_passes_well_formed_file(ha_accept, tmp_path, monkeypatch, capsys) -> None:
    plan_path, _docs = _setup_project(tmp_path, _GOOD_YAML)
    _patch_load_plan(ha_accept, monkeypatch, tmp_path, plan_path, ["fastapi"])

    rc = ha_accept.cmd_validate(SimpleNamespace())
    out = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert out["passed"] is True
    assert out["schema_violations"] == []
    assert out["cross_violations"] == []


def test_cmd_validate_blocks_missing_acceptance_yaml(
    ha_accept, tmp_path, monkeypatch, capsys
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    plan_path = docs / "harness-plan.md"
    plan_path.write_text("", encoding="utf-8")
    (docs / "skeleton.md").write_text(_SKEL_TEXT, encoding="utf-8")
    _patch_load_plan(ha_accept, monkeypatch, tmp_path, plan_path, ["fastapi"])

    rc = ha_accept.cmd_validate(SimpleNamespace())

    assert rc == 1


def test_cmd_validate_fails_explicitly_when_skeleton_missing(
    ha_accept, tmp_path, monkeypatch, capsys
) -> None:
    """skeleton.md 부재는 '엔드포인트 미선언' 오진 대신 명시적 FAIL 로 보고."""
    docs = tmp_path / "docs"
    docs.mkdir()
    plan_path = docs / "harness-plan.md"
    plan_path.write_text("", encoding="utf-8")
    (docs / "acceptance.yaml").write_text(_GOOD_YAML, encoding="utf-8")
    _patch_load_plan(ha_accept, monkeypatch, tmp_path, plan_path, ["fastapi"])

    rc = ha_accept.cmd_validate(SimpleNamespace())
    captured = capsys.readouterr()

    assert rc == 1
    assert "skeleton.md" in (captured.out + captured.err)


def test_cmd_validate_blocks_malformed_yaml(ha_accept, tmp_path, monkeypatch, capsys) -> None:
    plan_path, _docs = _setup_project(tmp_path, "not: valid: yaml: [")
    _patch_load_plan(ha_accept, monkeypatch, tmp_path, plan_path, ["fastapi"])

    rc = ha_accept.cmd_validate(SimpleNamespace())

    assert rc == 1


def test_cmd_validate_reports_coverage_advisory_without_blocking(
    ha_accept, tmp_path, monkeypatch, capsys
) -> None:
    """'할일 삭제' 기능은 확정됐지만 시나리오가 없음 — advisory 로만 보고, exit 은 0."""
    plan_path, _docs = _setup_project(tmp_path, _GOOD_YAML)
    _patch_load_plan(ha_accept, monkeypatch, tmp_path, plan_path, ["fastapi"])

    rc = ha_accept.cmd_validate(SimpleNamespace())
    out = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert "할일 삭제" in out["coverage"]["features_without_scenarios"]


def test_cmd_validate_blocks_undeclared_endpoint_reference(
    ha_accept, tmp_path, monkeypatch, capsys
) -> None:
    bad_yaml = _GOOD_YAML.replace("/api/todos/{todo_id}", "/api/ghost")
    plan_path, _docs = _setup_project(tmp_path, bad_yaml)
    _patch_load_plan(ha_accept, monkeypatch, tmp_path, plan_path, ["fastapi"])

    rc = ha_accept.cmd_validate(SimpleNamespace())
    out = json.loads(capsys.readouterr().out)

    assert rc == 1
    assert out["passed"] is False
    assert any(v["kind"] == "endpoint_not_declared" for v in out["cross_violations"])
