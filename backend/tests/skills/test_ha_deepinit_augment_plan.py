"""G1 회귀 테스트: ha-deepinit augment-plan 서브커맨드.

결함: SKILL.md §5 가 `run.py augment-plan` 호출을 명시하지만 subcommand 미구현.
Fix: cmd_augment_plan — scan 결과 요약을 user_description_original 에 append.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HA_DEEPINIT_RUN = REPO_ROOT / "skills" / "ha-deepinit" / "run.py"


def _load_ha_deepinit() -> ModuleType:
    loader = SourceFileLoader("ha_deepinit_augment", str(HA_DEEPINIT_RUN))
    spec = importlib.util.spec_from_loader("ha_deepinit_augment", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_deepinit_augment"] = mod
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ha_deepinit() -> ModuleType:
    return _load_ha_deepinit()


def _make_mock_plan(description: str = "초기 설명") -> MagicMock:
    mock_plan = MagicMock()
    mock_plan.user_description_original = description
    return mock_plan


# ── cmd_augment_plan 기능 테스트 ──────────────────────────────────────────


def test_augment_plan_appends_summary_to_description(ha_deepinit, tmp_path, monkeypatch) -> None:
    """augment-plan → user_description_original 끝에 분석 요약 추가."""
    mock_plan = _make_mock_plan("초기 설명")
    plan_path = tmp_path / "docs" / "harness-plan.md"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("dummy", encoding="utf-8")

    saved: list[MagicMock] = []

    monkeypatch.setattr(ha_deepinit, "load_plan", lambda: (mock_plan, plan_path, tmp_path))
    monkeypatch.setattr(ha_deepinit, "save_plan", lambda p, pp: saved.append(p))

    # 프로젝트에 파일 몇 개 생성
    (tmp_path / "main.py").write_text("print('hello')", encoding="utf-8")
    (tmp_path / "utils.py").write_text("pass", encoding="utf-8")

    args = SimpleNamespace(project="", no_backup=True)
    rc = ha_deepinit.cmd_augment_plan(args)

    assert rc == 0
    assert len(saved) == 1
    updated = saved[0].user_description_original
    assert updated.startswith("초기 설명")
    assert "## 자동 분석 (ha-deepinit augment" in updated


def test_augment_plan_preserves_original_description(ha_deepinit, tmp_path, monkeypatch) -> None:
    """기존 user_description_original 내용이 보존되어야 함 (덮어쓰기 아님)."""
    original = "프로젝트: 금칙어 게임\n목표: 키워드 기반 게임"
    mock_plan = _make_mock_plan(original)
    plan_path = tmp_path / "docs" / "harness-plan.md"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("dummy", encoding="utf-8")

    saved: list[MagicMock] = []
    monkeypatch.setattr(ha_deepinit, "load_plan", lambda: (mock_plan, plan_path, tmp_path))
    monkeypatch.setattr(ha_deepinit, "save_plan", lambda p, pp: saved.append(p))

    args = SimpleNamespace(project="", no_backup=True)
    ha_deepinit.cmd_augment_plan(args)

    updated = saved[0].user_description_original
    assert updated.startswith(original), f"원본 보존 실패: {updated[:80]!r}"


def test_augment_plan_output_json_keys(ha_deepinit, tmp_path, monkeypatch, capsys) -> None:
    """출력 JSON 에 필수 키 포함: augmented, total_files, primary_language."""
    mock_plan = _make_mock_plan("desc")
    plan_path = tmp_path / "docs" / "harness-plan.md"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("dummy", encoding="utf-8")

    monkeypatch.setattr(ha_deepinit, "load_plan", lambda: (mock_plan, plan_path, tmp_path))
    monkeypatch.setattr(ha_deepinit, "save_plan", lambda p, pp: None)

    args = SimpleNamespace(project="", no_backup=True)
    rc = ha_deepinit.cmd_augment_plan(args)

    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["augmented"] is True
    assert "total_files" in data
    assert "primary_language" in data


def test_augment_plan_creates_backup_by_default(ha_deepinit, tmp_path, monkeypatch) -> None:
    """--no-backup 없으면 .harness-plan.md.bak-<ts> 파일 생성."""
    mock_plan = _make_mock_plan("desc")
    plan_path = tmp_path / "docs" / "harness-plan.md"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("original content", encoding="utf-8")

    monkeypatch.setattr(ha_deepinit, "load_plan", lambda: (mock_plan, plan_path, tmp_path))
    monkeypatch.setattr(ha_deepinit, "save_plan", lambda p, pp: None)

    args = SimpleNamespace(project="", no_backup=False)
    ha_deepinit.cmd_augment_plan(args)

    backup_files = list(plan_path.parent.glob(".harness-plan.md.bak-*"))
    assert len(backup_files) == 1, f"backup 파일 생성 안 됨: {list(plan_path.parent.iterdir())}"
    assert backup_files[0].read_text(encoding="utf-8") == "original content"


def test_augment_plan_no_backup_flag_skips_backup(ha_deepinit, tmp_path, monkeypatch) -> None:
    """--no-backup 옵션 → backup 파일 생성 안 됨."""
    mock_plan = _make_mock_plan("desc")
    plan_path = tmp_path / "docs" / "harness-plan.md"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("original content", encoding="utf-8")

    monkeypatch.setattr(ha_deepinit, "load_plan", lambda: (mock_plan, plan_path, tmp_path))
    monkeypatch.setattr(ha_deepinit, "save_plan", lambda p, pp: None)

    args = SimpleNamespace(project="", no_backup=True)
    ha_deepinit.cmd_augment_plan(args)

    backup_files = list(plan_path.parent.glob(".harness-plan.md.bak-*"))
    assert len(backup_files) == 0, "no_backup=True 인데 backup 생성됨"


def test_augment_plan_summary_contains_language_info(ha_deepinit, tmp_path, monkeypatch) -> None:
    """분석 요약에 언어 정보 포함."""
    mock_plan = _make_mock_plan("desc")
    plan_path = tmp_path / "docs" / "harness-plan.md"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("dummy", encoding="utf-8")

    # .py 파일 여러 개 생성
    for i in range(4):
        (tmp_path / f"module_{i}.py").write_text("pass", encoding="utf-8")

    saved: list[MagicMock] = []
    monkeypatch.setattr(ha_deepinit, "load_plan", lambda: (mock_plan, plan_path, tmp_path))
    monkeypatch.setattr(ha_deepinit, "save_plan", lambda p, pp: saved.append(p))

    args = SimpleNamespace(project="", no_backup=True)
    ha_deepinit.cmd_augment_plan(args)

    updated = saved[0].user_description_original
    assert "python" in updated.lower(), f"언어 정보 없음: {updated}"


def test_augment_plan_save_oserror_returns_exit1(ha_deepinit, tmp_path, monkeypatch) -> None:
    """save_plan OSError → exit 1."""
    mock_plan = _make_mock_plan("desc")
    plan_path = tmp_path / "docs" / "harness-plan.md"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("dummy", encoding="utf-8")

    monkeypatch.setattr(ha_deepinit, "load_plan", lambda: (mock_plan, plan_path, tmp_path))

    def _fail_save(p, pp):
        raise OSError("disk full")
    monkeypatch.setattr(ha_deepinit, "save_plan", _fail_save)

    args = SimpleNamespace(project="", no_backup=True)
    rc = ha_deepinit.cmd_augment_plan(args)

    assert rc == 1


def test_augment_plan_uses_custom_project_path(ha_deepinit, tmp_path, monkeypatch) -> None:
    """--project 인자로 스캔 경로 지정 가능."""
    mock_plan = _make_mock_plan("desc")
    plan_path = tmp_path / "docs" / "harness-plan.md"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("dummy", encoding="utf-8")

    # 별도 스캔 디렉토리
    scan_dir = tmp_path / "custom_project"
    scan_dir.mkdir()
    for i in range(4):
        (scan_dir / f"file_{i}.ts").write_text("export {};", encoding="utf-8")

    saved: list[MagicMock] = []
    monkeypatch.setattr(ha_deepinit, "load_plan", lambda: (mock_plan, plan_path, tmp_path))
    monkeypatch.setattr(ha_deepinit, "save_plan", lambda p, pp: saved.append(p))

    args = SimpleNamespace(project=str(scan_dir), no_backup=True)
    rc = ha_deepinit.cmd_augment_plan(args)

    assert rc == 0
    updated = saved[0].user_description_original
    assert "typescript" in updated.lower(), f"custom project 언어 반영 안 됨: {updated}"


# ── argparse subparser 등록 확인 ──────────────────────────────────────────


def test_main_augment_plan_subparser_registered(ha_deepinit, tmp_path, monkeypatch) -> None:
    """argparse 에 augment-plan 서브커맨드 등록 확인 — 호출 시 exit 2 아님."""
    mock_plan = _make_mock_plan("desc")
    plan_path = tmp_path / "docs" / "harness-plan.md"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text("dummy", encoding="utf-8")

    monkeypatch.setattr(ha_deepinit, "load_plan", lambda: (mock_plan, plan_path, tmp_path))
    monkeypatch.setattr(ha_deepinit, "save_plan", lambda p, pp: None)

    # sys.argv 패치해서 augment-plan 호출
    monkeypatch.setattr(sys, "argv", ["ha-deepinit", "augment-plan", "--no-backup"])

    rc = ha_deepinit.main()

    assert rc == 0, f"augment-plan 서브커맨드 실행 실패 (rc={rc})"
