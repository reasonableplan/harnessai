"""ha-converge 스킬 run.py 테스트 (Track A4).

converge.py 의 순수 로직은 test_converge.py 가 커버. 여기선 스킬 배선:
_iter_source_texts + cmd_commit 의 end-to-end(skeleton+tasks+source → tasks append).
"""

from __future__ import annotations

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HA_CONVERGE_RUN = REPO_ROOT / "skills" / "ha-converge" / "run.py"

_SKELETON = """\
## 8. HTTP API

- **`GET /api/users`** — list
- **`GET /api/orders/{id}`** — get order
"""

_TASKS = """\
## 12. 태스크 분해

### 태스크 목록 (Phase 테이블 — 파서 고정 5컬럼, 순서 변경 금지)
| ID | 에이전트 | 의존성 | 설명 | 상태 |
|---|---|---|---|---|
| T-001 | backend_coder | - | users API | done |

### 진행 상태
- `대기` — 아직 시작 안 함
"""


@pytest.fixture(scope="module")
def ha_converge() -> ModuleType:
    loader = SourceFileLoader("ha_converge_run", str(HA_CONVERGE_RUN))
    spec = importlib.util.spec_from_loader("ha_converge_run", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_converge_run"] = mod
    loader.exec_module(mod)
    return mod


def test_iter_source_texts_respects_skip_dirs_and_exts(ha_converge, tmp_path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("code here", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lib.js").write_text("vendor", encoding="utf-8")
    (tmp_path / "README.md").write_text("docs", encoding="utf-8")

    texts = ha_converge._iter_source_texts(tmp_path)

    assert "code here" in texts
    assert "vendor" not in texts  # node_modules skipped
    assert "docs" not in texts  # .md not a source ext


def _setup_project(tmp_path: Path) -> Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "skeleton.md").write_text(_SKELETON, encoding="utf-8")
    (docs / "tasks.md").write_text(_TASKS, encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    # implements only /api/users → /api/orders is missing
    (src / "app.py").write_text('@router.get("/api/users")\n', encoding="utf-8")
    return docs / "harness-plan.md"


def _patch_plan(ha_converge, monkeypatch, tmp_path: Path, plan_path: Path) -> None:
    fake_plan = SimpleNamespace(pipeline=SimpleNamespace(current_step="reviewed"))
    monkeypatch.setattr(ha_converge, "load_plan", lambda: (fake_plan, plan_path, tmp_path))
    monkeypatch.setattr(ha_converge, "assert_state", lambda *a, **kw: None)


def test_commit_appends_missing_endpoint_task(ha_converge, tmp_path, monkeypatch) -> None:
    plan_path = _setup_project(tmp_path)
    _patch_plan(ha_converge, monkeypatch, tmp_path, plan_path)

    rc = ha_converge.cmd_commit(SimpleNamespace())

    assert rc == 0
    tasks_text = (plan_path.parent / "tasks.md").read_text(encoding="utf-8")
    assert "T-002" in tasks_text
    assert "GET /api/orders/{id}" in tasks_text
    # 기존 태스크 보존
    assert "users API" in tasks_text


def test_commit_is_idempotent(ha_converge, tmp_path, monkeypatch) -> None:
    plan_path = _setup_project(tmp_path)
    _patch_plan(ha_converge, monkeypatch, tmp_path, plan_path)

    assert ha_converge.cmd_commit(SimpleNamespace()) == 0
    first = (plan_path.parent / "tasks.md").read_text(encoding="utf-8")
    assert ha_converge.cmd_commit(SimpleNamespace()) == 0
    second = (plan_path.parent / "tasks.md").read_text(encoding="utf-8")

    assert first == second  # no duplicate rows on re-run


def test_prepare_is_read_only(ha_converge, tmp_path, monkeypatch, capsys) -> None:
    plan_path = _setup_project(tmp_path)
    _patch_plan(ha_converge, monkeypatch, tmp_path, plan_path)
    before = (plan_path.parent / "tasks.md").read_text(encoding="utf-8")

    rc = ha_converge.cmd_prepare(SimpleNamespace())

    assert rc == 0
    after = (plan_path.parent / "tasks.md").read_text(encoding="utf-8")
    assert before == after  # prepare must not mutate
    out = capsys.readouterr().out
    assert "GET /api/orders/{id}" in out
    assert '"uncovered"' in out
