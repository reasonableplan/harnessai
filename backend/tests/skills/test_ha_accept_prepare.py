"""ha-accept prepare 회귀 테스트 — skeleton.md 에서 GWT/확정기능/엔드포인트 추출.

prepare 는 acceptance.yaml 파생(LLM 몫)의 입력 재료를 기계적으로 뽑아 JSON 으로
보고한다: ①확정 기능 목록 ②기능별 GWT 라인 ③interface.http 선언 엔드포인트
④활성 프로파일 {id, path, toolchain.smoke} ⑤docs/acceptance.yaml 존재 여부.
GWT 가 하나도 없으면 legacy_skeleton: true 로 명시 보고한다.
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
    loader = SourceFileLoader("ha_accept_prepare", str(HA_ACCEPT_RUN))
    spec = importlib.util.spec_from_loader("ha_accept_prepare", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_accept_prepare"] = mod
    loader.exec_module(mod)
    return mod


_SKELETON_WITH_GWT = """\
## 1. 프로젝트 개요

블라블라

## 2. 기능 요구사항

### AI 제안 후보 (사용자 선택 — /ha-design 단계에서 채워짐)

| # | 후보 기능 | 사용자 가치 | 근거 | 선택 |
|---|----------|-------------|------|:---:|
| 1 | 할일 추가 | 빠른 기록 | 페르소나 1 | O |

### 확정 기능 (사용자 선택 결과 — MVP Phase 1)

- [x] 할일 추가
  - 수용 기준:
    - Given 빈 목록 / When 제목 입력 후 추가 / Then 목록에 1건 표시
    - Given 목록에 1건 있음 / When 완료 체크 / Then 완료 표시로 전환
- [x] 할일 삭제
  - 수용 기준:
    - Given 목록에 1건 있음 / When 삭제 버튼 클릭 / Then 목록에서 제거됨

### 추가 기능 (Phase 2+)
- [ ] 반복 일정

### 비즈니스 규칙
- 완료 기록은 오늘 날짜만 가능

## 3. HTTP API

| method | path | 설명 |
|---|---|---|
| `GET /api/todos` | 목록 조회 |
| `POST /api/todos` | 추가 |
| `GET /api/todos/{id}` | 단건 조회 |
| `DELETE /api/todos/{id}` | 삭제 |
"""

_SKELETON_LEGACY_NO_GWT = """\
## 1. 프로젝트 개요

블라블라

## 2. 기능 요구사항

### 확정 기능 (사용자 선택 결과 — MVP Phase 1)

- [x] 할일 추가
- [x] 할일 삭제

## 3. HTTP API

| method | path | 설명 |
|---|---|---|
| `GET /api/todos` | 목록 조회 |
"""

_SKELETON_NO_REQUIREMENTS_SECTION = """\
## 1. 프로젝트 개요

블라블라

## 3. HTTP API

| method | path | 설명 |
|---|---|---|
| `GET /api/todos` | 목록 조회 |
"""


def _plan(profiles):
    return SimpleNamespace(
        pipeline=SimpleNamespace(current_step="verified"),
        profiles=profiles,
    )


def _run_prepare(ha_accept, monkeypatch, tmp_path: Path, skel_text: str, profiles):
    docs = tmp_path / "docs"
    docs.mkdir()
    plan_path = docs / "harness-plan.md"
    plan_path.write_text("", encoding="utf-8")
    (docs / "skeleton.md").write_text(skel_text, encoding="utf-8")

    plan = _plan([SimpleNamespace(id=p.id, path=".") for p in profiles])
    monkeypatch.setattr(ha_accept, "load_plan", lambda: (plan, plan_path, tmp_path))
    monkeypatch.setattr(ha_accept, "assert_state", lambda *a, **k: None)
    monkeypatch.setattr(ha_accept, "get_active_profiles", lambda p, pr: profiles)
    return plan_path


def test_prepare_extracts_features_with_gwt(ha_accept, tmp_path, monkeypatch, capsys) -> None:
    profile = SimpleNamespace(
        id="fastapi", toolchain=SimpleNamespace(smoke="uv run uvicorn app:app")
    )
    _run_prepare(ha_accept, monkeypatch, tmp_path, _SKELETON_WITH_GWT, [profile])

    rc = ha_accept.cmd_prepare(SimpleNamespace())
    out = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert out["legacy_skeleton"] is False
    names = [f["name"] for f in out["features"]]
    assert names == ["할일 추가", "할일 삭제"]
    add_feature = out["features"][0]
    assert len(add_feature["gwt"]) == 2
    assert "Given" in add_feature["gwt"][0]
    assert "When" in add_feature["gwt"][0]
    assert "Then" in add_feature["gwt"][0]
    # "추가 기능 (Phase 2+)" 의 항목은 확정 기능이 아니므로 제외
    assert "반복 일정" not in names


def test_prepare_extracts_declared_endpoints(ha_accept, tmp_path, monkeypatch, capsys) -> None:
    profile = SimpleNamespace(id="fastapi", toolchain=SimpleNamespace(smoke=None))
    _run_prepare(ha_accept, monkeypatch, tmp_path, _SKELETON_WITH_GWT, [profile])

    ha_accept.cmd_prepare(SimpleNamespace())
    out = json.loads(capsys.readouterr().out)

    endpoints = {(e["method"], e["path"]) for e in out["declared_endpoints"]}
    assert ("GET", "/api/todos") in endpoints
    assert ("POST", "/api/todos") in endpoints
    assert ("GET", "/api/todos/{id}") in endpoints
    assert ("DELETE", "/api/todos/{id}") in endpoints


def test_prepare_reports_active_profiles(ha_accept, tmp_path, monkeypatch, capsys) -> None:
    profile = SimpleNamespace(
        id="fastapi", toolchain=SimpleNamespace(smoke="uv run uvicorn app:app --port 8000")
    )
    _run_prepare(ha_accept, monkeypatch, tmp_path, _SKELETON_WITH_GWT, [profile])

    ha_accept.cmd_prepare(SimpleNamespace())
    out = json.loads(capsys.readouterr().out)

    assert out["profiles"] == [
        {"id": "fastapi", "path": ".", "toolchain": {"smoke": "uv run uvicorn app:app --port 8000"}}
    ]


def test_prepare_reports_acceptance_yaml_existence(
    ha_accept, tmp_path, monkeypatch, capsys
) -> None:
    profile = SimpleNamespace(id="fastapi", toolchain=SimpleNamespace(smoke=None))
    plan_path = _run_prepare(ha_accept, monkeypatch, tmp_path, _SKELETON_WITH_GWT, [profile])

    ha_accept.cmd_prepare(SimpleNamespace())
    out = json.loads(capsys.readouterr().out)
    assert out["acceptance_yaml_exists"] is False

    (plan_path.parent / "acceptance.yaml").write_text("version: 1\n", encoding="utf-8")
    ha_accept.cmd_prepare(SimpleNamespace())
    out2 = json.loads(capsys.readouterr().out)
    assert out2["acceptance_yaml_exists"] is True


def test_prepare_legacy_skeleton_when_no_gwt_lines(
    ha_accept, tmp_path, monkeypatch, capsys
) -> None:
    profile = SimpleNamespace(id="fastapi", toolchain=SimpleNamespace(smoke=None))
    _run_prepare(ha_accept, monkeypatch, tmp_path, _SKELETON_LEGACY_NO_GWT, [profile])

    ha_accept.cmd_prepare(SimpleNamespace())
    out = json.loads(capsys.readouterr().out)

    assert out["legacy_skeleton"] is True
    # 확정 기능 목록 자체는 그대로 보고 (체크박스는 있으니까)
    assert [f["name"] for f in out["features"]] == ["할일 추가", "할일 삭제"]


def test_prepare_fails_explicitly_when_skeleton_missing(
    ha_accept, tmp_path, monkeypatch, capsys
) -> None:
    """verified 상태에서 skeleton.md 부재는 비정상 — silent legacy 폴백 대신 명시 FAIL."""
    docs = tmp_path / "docs"
    docs.mkdir()
    plan_path = docs / "harness-plan.md"
    plan_path.write_text("", encoding="utf-8")
    plan = _plan([SimpleNamespace(id="fastapi", path=".")])
    monkeypatch.setattr(ha_accept, "load_plan", lambda: (plan, plan_path, tmp_path))
    monkeypatch.setattr(ha_accept, "assert_state", lambda *a, **k: None)

    rc = ha_accept.cmd_prepare(SimpleNamespace())
    captured = capsys.readouterr()

    assert rc == 1
    assert "skeleton.md" in (captured.out + captured.err)


def test_prepare_legacy_skeleton_when_requirements_section_absent(
    ha_accept, tmp_path, monkeypatch, capsys
) -> None:
    profile = SimpleNamespace(id="fastapi", toolchain=SimpleNamespace(smoke=None))
    _run_prepare(ha_accept, monkeypatch, tmp_path, _SKELETON_NO_REQUIREMENTS_SECTION, [profile])

    ha_accept.cmd_prepare(SimpleNamespace())
    out = json.loads(capsys.readouterr().out)

    assert out["legacy_skeleton"] is True
    assert out["features"] == []
