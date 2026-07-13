"""declared_files 스텁 스탬퍼 + 스텁 미구현 게이트 회귀 테스트 (scaffolding-design.md §5~§6).

대상:
  - skills/ha-build/run.py :: _stub_content / _stamp_declared_files /
    _declared_stub_files (순수 헬퍼)
  - skills/ha-build/run.py :: cmd_prepare (스탬프 통합 — reentry/scaffold/--no-stamp 분기)
  - skills/ha-build/run.py :: cmd_complete (스텁 미구현 게이트 — LESSON-021 앞)

로딩 패턴: test_ha_scaffold_bootstrap.py 의 SourceFileLoader + SimpleNamespace duck-typed
plan/profile patch 패턴을 재사용한다. 모듈 이름은 다른 테스트 파일과 겹치지 않게 고유하게.
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
HA_BUILD_RUN = REPO_ROOT / "skills" / "ha-build" / "run.py"

_STUB_LINE = "# HARNESS-STUB T-001: ha-build prepare 선생성 스텁 — 구현 시 이 줄 제거\n"


def _load_module(name: str, path: Path) -> ModuleType:
    loader = SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec is not None, f"spec load failed: {path}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ha_build() -> ModuleType:
    return _load_module("ha_build_stub_stamper", HA_BUILD_RUN)


# ── _stub_content — 확장자별 주석 문법 (순수 함수) ──────────────────────────


def test_stub_content_python_uses_hash_comment(ha_build) -> None:
    assert ha_build._stub_content("src/foo.py", "T-001") == _STUB_LINE


def test_stub_content_typescript_uses_slash_comment(ha_build) -> None:
    assert ha_build._stub_content("src/bar.ts", "T-001") == (
        "// HARNESS-STUB T-001: ha-build prepare 선생성 스텁 — 구현 시 이 줄 제거\n"
    )


def test_stub_content_css_uses_block_comment(ha_build) -> None:
    assert ha_build._stub_content("src/style.css", "T-001") == (
        "/* HARNESS-STUB T-001: ha-build prepare 선생성 스텁 — 구현 시 이 줄 제거 */\n"
    )


def test_stub_content_markdown_uses_html_comment(ha_build) -> None:
    assert ha_build._stub_content("docs/readme.md", "T-001") == (
        "<!-- HARNESS-STUB T-001: ha-build prepare 선생성 스텁 — 구현 시 이 줄 제거 -->\n"
    )


def test_stub_content_sql_uses_dash_comment(ha_build) -> None:
    assert ha_build._stub_content("db/schema.sql", "T-001") == (
        "-- HARNESS-STUB T-001: ha-build prepare 선생성 스텁 — 구현 시 이 줄 제거\n"
    )


def test_stub_content_excludes_directory_token(ha_build) -> None:
    assert ha_build._stub_content("src/components/", "T-001") is None


def test_stub_content_excludes_glob_token(ha_build) -> None:
    assert ha_build._stub_content("src/glob/*.py", "T-001") is None
    assert ha_build._stub_content("src/glob/file?.py", "T-001") is None


def test_stub_content_excludes_unsupported_extension(ha_build) -> None:
    assert ha_build._stub_content("src/config.json", "T-001") is None


# ── _stamp_declared_files ───────────────────────────────────────────────────


def test_stamp_declared_files_creates_parent_dirs(ha_build, tmp_path: Path) -> None:
    declared = ["src/nested/deep/foo.py"]

    stamped, unstamped = ha_build._stamp_declared_files(tmp_path, declared, "T-001")

    assert stamped == ["src/nested/deep/foo.py"]
    assert unstamped == []
    created = tmp_path / "src" / "nested" / "deep" / "foo.py"
    assert created.read_text(encoding="utf-8") == _STUB_LINE


def test_stamp_declared_files_skips_existing_file(ha_build, tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    existing = tmp_path / "src" / "foo.py"
    existing.write_text("print('real code')\n", encoding="utf-8")

    stamped, unstamped = ha_build._stamp_declared_files(tmp_path, ["src/foo.py"], "T-001")

    assert stamped == []
    assert unstamped == []
    assert existing.read_text(encoding="utf-8") == "print('real code')\n"


def test_stamp_declared_files_reports_exclusions_without_creating(ha_build, tmp_path: Path) -> None:
    declared = ["src/components/", "src/glob/*.py", "src/config.json"]

    stamped, unstamped = ha_build._stamp_declared_files(tmp_path, declared, "T-001")

    assert stamped == []
    assert unstamped == declared
    for rel in declared:
        assert not (tmp_path / rel).exists()


# ── _declared_stub_files ─────────────────────────────────────────────────────


def test_declared_stub_files_detects_marker(ha_build, tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text(_STUB_LINE, encoding="utf-8")

    assert ha_build._declared_stub_files(tmp_path, ["src/foo.py"]) == ["src/foo.py"]


def test_declared_stub_files_ignores_implemented_file(ha_build, tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text("def foo():\n    return 1\n", encoding="utf-8")

    assert ha_build._declared_stub_files(tmp_path, ["src/foo.py"]) == []


def test_declared_stub_files_skips_missing_files(ha_build, tmp_path: Path) -> None:
    assert ha_build._declared_stub_files(tmp_path, ["src/missing.py"]) == []


# ── cmd_prepare 통합 — 스탬프/reentry/scaffold/--no-stamp ───────────────────


def _make_plan() -> SimpleNamespace:
    return SimpleNamespace(
        pipeline=SimpleNamespace(
            current_step="planned",
            completed_steps=(),
            skipped_steps=(),
            steps=("planned", "building", "built"),
            gstack_mode="manual",
        ),
        profiles=[SimpleNamespace(id="fastapi", path=".")],
        skeleton_hash=None,
        frozen_status="frozen",
    )


def _patch_prepare(ha_build, monkeypatch, plan, tmp_path: Path, tasks_text: str) -> Path:
    tasks_path = tmp_path / "tasks.md"
    tasks_path.write_text(tasks_text, encoding="utf-8")
    plan_path = tmp_path / "harness-plan.md"
    plan_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(ha_build, "load_plan", lambda: (plan, plan_path, tmp_path))
    monkeypatch.setattr(ha_build, "save_plan", lambda p, pp: None)
    monkeypatch.setattr(ha_build, "get_active_profiles", lambda plan, project: [])
    return tasks_path


_TASKS_TABLE_T001_PENDING = (
    "| ID    | Agent         | Depends On | Description | Status |\n"
    "|-------|---------------|------------|-------------|--------|\n"
    "| T-001 | backend_coder | -          | 태스크       | 대기    |\n"
)

_TASKS_TABLE_T001_INPROGRESS = (
    "| ID    | Agent         | Depends On | Description | Status      |\n"
    "|-------|---------------|------------|-------------|-------------|\n"
    "| T-001 | backend_coder | -          | 태스크       | in-progress |\n"
)

_SPEC_T001 = "\n### T-001\n생성 파일: `src/foo.py`, `src/bar.ts`, `src/config.json`\n"

_TASKS_TABLE_T002_PENDING = (
    "| ID    | Agent         | Depends On | Description | Status |\n"
    "|-------|---------------|------------|-------------|--------|\n"
    "| T-002 | backend_coder | -          | 태스크       | 대기    |\n"
)

_SPEC_T002_EXCLUSIONS = (
    "\n### T-002\n생성 파일: `src/valid.py`, `src/dirtoken/`, `src/glob/*.ts`, `src/data.json`\n"
)

_TASKS_TABLE_T000_SCAFFOLD = (
    "| ID    | Agent    | Depends On | Description | Status |\n"
    "|-------|----------|------------|-------------|--------|\n"
    "| T-000 | scaffold | -          | 부트스트랩    | 대기    |\n"
)

_SPEC_T000 = "\n### T-000\n생성 파일: `package.json`\n"


def test_prepare_stamps_missing_declared_files_for_pending_task(
    ha_build, tmp_path, monkeypatch, capsys
) -> None:
    plan = _make_plan()
    _patch_prepare(ha_build, monkeypatch, plan, tmp_path, _TASKS_TABLE_T001_PENDING + _SPEC_T001)

    rc = ha_build.cmd_prepare(SimpleNamespace(task="T-001", skip_frozen_gate=False))

    assert rc == 0
    task = json.loads(capsys.readouterr().out)["tasks"][0]
    assert task["stamped_files"] == ["src/foo.py", "src/bar.ts"]
    assert task["unstamped"] == ["src/config.json"]
    assert (tmp_path / "src" / "foo.py").exists()
    assert (tmp_path / "src" / "bar.ts").exists()
    assert not (tmp_path / "src" / "config.json").exists()


def test_prepare_reports_unstamped_for_dir_glob_and_unsupported_ext(
    ha_build, tmp_path, monkeypatch, capsys
) -> None:
    plan = _make_plan()
    _patch_prepare(
        ha_build, monkeypatch, plan, tmp_path, _TASKS_TABLE_T002_PENDING + _SPEC_T002_EXCLUSIONS
    )

    rc = ha_build.cmd_prepare(SimpleNamespace(task="T-002", skip_frozen_gate=False))

    assert rc == 0
    task = json.loads(capsys.readouterr().out)["tasks"][0]
    assert task["stamped_files"] == ["src/valid.py"]
    assert set(task["unstamped"]) == {"src/dirtoken/", "src/glob/*.ts", "src/data.json"}
    assert not (tmp_path / "src" / "dirtoken").exists()
    assert not (tmp_path / "src" / "glob").exists()
    assert not (tmp_path / "src" / "data.json").exists()


def test_prepare_does_not_stamp_already_existing_file(
    ha_build, tmp_path, monkeypatch, capsys
) -> None:
    plan = _make_plan()
    _patch_prepare(ha_build, monkeypatch, plan, tmp_path, _TASKS_TABLE_T001_PENDING + _SPEC_T001)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text("print('real')\n", encoding="utf-8")

    rc = ha_build.cmd_prepare(SimpleNamespace(task="T-001", skip_frozen_gate=False))

    assert rc == 0
    task = json.loads(capsys.readouterr().out)["tasks"][0]
    assert "src/foo.py" not in task["stamped_files"]
    assert (tmp_path / "src" / "foo.py").read_text(encoding="utf-8") == "print('real')\n"


def test_prepare_reentry_task_does_not_stamp_and_reports_stub_files(
    ha_build, tmp_path, monkeypatch, capsys
) -> None:
    plan = _make_plan()
    _patch_prepare(ha_build, monkeypatch, plan, tmp_path, _TASKS_TABLE_T001_INPROGRESS + _SPEC_T001)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text(_STUB_LINE, encoding="utf-8")
    (tmp_path / "src" / "bar.ts").write_text("export const bar = 1;\n", encoding="utf-8")

    rc = ha_build.cmd_prepare(SimpleNamespace(task="T-001", skip_frozen_gate=False))

    assert rc == 0
    captured = capsys.readouterr()
    task = json.loads(captured.out)["tasks"][0]
    assert task["reentry"] is True
    assert task["stamped_files"] == []
    assert task["unstamped"] == []
    assert task["stub_files"] == ["src/foo.py"]
    assert not (tmp_path / "src" / "config.json").exists()
    assert "스텁 미구현 1개" in captured.err


def test_prepare_does_not_stamp_scaffold_task(ha_build, tmp_path, monkeypatch, capsys) -> None:
    plan = _make_plan()
    _patch_prepare(ha_build, monkeypatch, plan, tmp_path, _TASKS_TABLE_T000_SCAFFOLD + _SPEC_T000)

    rc = ha_build.cmd_prepare(SimpleNamespace(task="T-000", skip_frozen_gate=False))

    assert rc == 0
    task = json.loads(capsys.readouterr().out)["tasks"][0]
    assert task["stamped_files"] == []
    assert task["unstamped"] == []
    assert not (tmp_path / "package.json").exists()


def test_prepare_no_stamp_flag_creates_nothing(ha_build, tmp_path, monkeypatch, capsys) -> None:
    plan = _make_plan()
    _patch_prepare(ha_build, monkeypatch, plan, tmp_path, _TASKS_TABLE_T001_PENDING + _SPEC_T001)

    rc = ha_build.cmd_prepare(SimpleNamespace(task="T-001", skip_frozen_gate=False, no_stamp=True))

    assert rc == 0
    task = json.loads(capsys.readouterr().out)["tasks"][0]
    assert task["stamped_files"] == []
    assert not (tmp_path / "src" / "foo.py").exists()
    assert not (tmp_path / "src" / "bar.ts").exists()


# ── cmd_complete 통합 — 스텁 미구현 게이트 ──────────────────────────────────


def _make_complete_plan() -> SimpleNamespace:
    return SimpleNamespace(
        pipeline=SimpleNamespace(
            current_step="building",
            completed_steps=(),
            skipped_steps=(),
            steps=("planned", "building", "built"),
            gstack_mode="manual",
        ),
        profiles=[SimpleNamespace(id="fastapi", path=".")],
        skeleton_hash=None,
        frozen_status="frozen",
    )


def _patch_complete(ha_build, monkeypatch, plan, tmp_path: Path, tasks_text: str) -> Path:
    tasks_path = tmp_path / "tasks.md"
    tasks_path.write_text(tasks_text, encoding="utf-8")
    plan_path = tmp_path / "harness-plan.md"
    plan_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(ha_build, "load_plan", lambda: (plan, plan_path, tmp_path))
    monkeypatch.setattr(ha_build, "save_plan", lambda p, pp: None)
    monkeypatch.setattr(ha_build, "transition", lambda *a, **kw: None)
    return tasks_path


def _complete_args(task: str, status: str = "done", reason: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        task=task,
        status=status,
        reason=reason,
        skip_toolchain=True,
        skip_security=True,
        skip_frozen_gate=False,
    )


def test_complete_blocks_when_stub_marker_remains(ha_build, tmp_path, monkeypatch, capsys) -> None:
    plan = _make_complete_plan()
    _patch_complete(
        ha_build, monkeypatch, plan, tmp_path, _TASKS_TABLE_T001_INPROGRESS + _SPEC_T001
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text(_STUB_LINE, encoding="utf-8")
    (tmp_path / "src" / "bar.ts").write_text("export const bar = 1;\n", encoding="utf-8")

    rc = ha_build.cmd_complete(_complete_args("T-001"))

    assert rc == 1
    err = capsys.readouterr().err
    assert "[BLOCK]" in err
    assert "스텁 미구현" in err
    assert "src/foo.py" in err


def test_complete_passes_when_stub_marker_removed(ha_build, tmp_path, monkeypatch, capsys) -> None:
    plan = _make_complete_plan()
    _patch_complete(
        ha_build, monkeypatch, plan, tmp_path, _TASKS_TABLE_T001_INPROGRESS + _SPEC_T001
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text("def foo():\n    return 1\n", encoding="utf-8")
    (tmp_path / "src" / "bar.ts").write_text("export const bar = 1;\n", encoding="utf-8")

    rc = ha_build.cmd_complete(_complete_args("T-001"))

    assert rc == 0
    assert "스텁 미구현 게이트 통과" in capsys.readouterr().err


def test_complete_ignores_stub_marker_in_undeclared_file(
    ha_build, tmp_path, monkeypatch, capsys
) -> None:
    plan = _make_complete_plan()
    _patch_complete(
        ha_build, monkeypatch, plan, tmp_path, _TASKS_TABLE_T001_INPROGRESS + _SPEC_T001
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text("def foo():\n    return 1\n", encoding="utf-8")
    (tmp_path / "src" / "bar.ts").write_text("export const bar = 1;\n", encoding="utf-8")
    (tmp_path / "src" / "unrelated.py").write_text(
        "# HARNESS-STUB T-999: ha-build prepare 선생성 스텁 — 구현 시 이 줄 제거\n",
        encoding="utf-8",
    )

    rc = ha_build.cmd_complete(_complete_args("T-001"))

    assert rc == 0


def test_complete_status_blocked_skips_stub_gate(ha_build, tmp_path, monkeypatch, capsys) -> None:
    plan = _make_complete_plan()
    _patch_complete(
        ha_build, monkeypatch, plan, tmp_path, _TASKS_TABLE_T001_INPROGRESS + _SPEC_T001
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text(_STUB_LINE, encoding="utf-8")

    rc = ha_build.cmd_complete(_complete_args("T-001", status="blocked", reason="테스트"))

    assert rc == 0
    assert "스텁 미구현" not in capsys.readouterr().err


def test_complete_status_skipped_skips_stub_gate(ha_build, tmp_path, monkeypatch, capsys) -> None:
    plan = _make_complete_plan()
    _patch_complete(
        ha_build, monkeypatch, plan, tmp_path, _TASKS_TABLE_T001_INPROGRESS + _SPEC_T001
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text(_STUB_LINE, encoding="utf-8")

    rc = ha_build.cmd_complete(_complete_args("T-001", status="skipped"))

    assert rc == 0
    assert "스텁 미구현" not in capsys.readouterr().err


def test_complete_injected_t000_without_spec_block_is_noop(
    ha_build, tmp_path, monkeypatch, capsys
) -> None:
    plan = _make_complete_plan()
    _patch_complete(ha_build, monkeypatch, plan, tmp_path, _TASKS_TABLE_T000_SCAFFOLD)

    rc = ha_build.cmd_complete(_complete_args("T-000"))

    assert rc == 0
    assert "스텁 미구현 게이트 통과" in capsys.readouterr().err
