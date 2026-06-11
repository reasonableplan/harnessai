"""migrate-skeleton-hash 기능 단위 테스트 (V1/R4).

harness CLI 의 cmd_migrate_skeleton_hash() 로직을 검증.
conftest 의 harness_module fixture 를 사용 (importlib 로 CLI 스크립트 직접 로드).

모든 픽스처는 tmp_path 기반 — 사용자 환경 비의존.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from textwrap import dedent
from types import ModuleType

import pytest

# ── harness_module fixture (tests/skills/conftest.py 와 동일한 패턴) ─────────


def _load_harness_module() -> ModuleType:
    """harness CLI 스크립트를 모듈로 로드 (importlib — .py 확장자 없음)."""
    import importlib
    import importlib.util
    from importlib.machinery import SourceFileLoader

    repo_root = Path(__file__).resolve().parents[3]
    harness_bin = repo_root / "harness" / "bin" / "harness"
    loader = SourceFileLoader("_harness_bin_msh", str(harness_bin))
    spec = importlib.util.spec_from_loader("_harness_bin_msh", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_harness_bin_msh"] = mod
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def hmod() -> ModuleType:
    return _load_harness_module()


# ── 픽스처 헬퍼 ──────────────────────────────────────────────────────────

_MINIMAL_PLAN_NO_HASH = dedent("""\
    ---
    harness_version: 2
    schema_version: 1
    project_name: 테스트 프로젝트
    created_at: '2026-01-01T00:00:00+00:00'
    updated_at: '2026-01-01T00:00:00+00:00'
    project_type: mobile
    scale: small
    scale_axes:
      user_scale: small
      data_sensitivity: none
      team_size: solo
      availability: standard
      monetization: none
      lifecycle: mvp
    user_description_original: 테스트용
    profiles:
      - id: react-native-expo
        path: .
        status: confirmed
    skeleton_sections:
      required: [overview]
      optional: []
      included: [overview]
    pipeline:
      steps: [ha-init, ha-design, ha-plan]
      current_step: designed
      completed_steps: [ha-init, ha-design]
      skipped_steps: []
      gstack_mode: manual
    verify_history: []
    redesign_history: []
    backups: []
    last_activity: '2026-01-01T00:00:00+00:00'
    ---

    # 프로젝트 개요
    """)

_MINIMAL_PLAN_WITH_HASH = dedent("""\
    ---
    harness_version: 2
    schema_version: 1
    project_name: 테스트 프로젝트
    created_at: '2026-01-01T00:00:00+00:00'
    updated_at: '2026-01-01T00:00:00+00:00'
    project_type: mobile
    scale: small
    scale_axes:
      user_scale: small
      data_sensitivity: none
      team_size: solo
      availability: standard
      monetization: none
      lifecycle: mvp
    user_description_original: 테스트용
    profiles:
      - id: react-native-expo
        path: .
        status: confirmed
    skeleton_sections:
      required: [overview]
      optional: []
      included: [overview]
    pipeline:
      steps: [ha-init, ha-design, ha-plan]
      current_step: designed
      completed_steps: [ha-init, ha-design]
      skipped_steps: []
      gstack_mode: manual
    verify_history: []
    redesign_history: []
    backups: []
    last_activity: '2026-01-01T00:00:00+00:00'
    skeleton_hash: abc123deadbeef0000000000000000000000000000000000000000000000abcd
    ---

    # 프로젝트 개요
    """)

_SKELETON_CONTENT = "# 프로젝트 개요\n\n## 1. Overview\n\nContent here.\n"


def _write_plan(docs_dir: Path, content: str = _MINIMAL_PLAN_NO_HASH) -> Path:
    docs_dir.mkdir(parents=True, exist_ok=True)
    plan_path = docs_dir / "harness-plan.md"
    plan_path.write_text(content, encoding="utf-8")
    return plan_path


def _write_skeleton(docs_dir: Path, content: str = _SKELETON_CONTENT) -> Path:
    docs_dir.mkdir(parents=True, exist_ok=True)
    skel = docs_dir / "skeleton.md"
    skel.write_text(content, encoding="utf-8")
    return skel


def _expected_hash(content: str) -> str:
    import hashlib

    normalized = content.encode("utf-8").replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(normalized).hexdigest()


# ── 테스트 1: dry-run — 파일 미수정, hash 출력 ───────────────────────────


def test_dry_run_no_file_change(hmod: ModuleType, tmp_path: Path) -> None:
    """--apply 없으면 plan 파일이 변경되지 않아야 한다."""
    docs = tmp_path / "docs"
    plan_path = _write_plan(docs)
    _write_skeleton(docs)

    content_before = plan_path.read_text(encoding="utf-8")

    rc = hmod.cmd_migrate_skeleton_hash(plan_path, apply=False, no_backup=False)

    assert rc == 0
    assert plan_path.read_text(encoding="utf-8") == content_before


def test_dry_run_output_contains_hash(
    hmod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """dry-run stdout 에 new_hash 가 포함되어야 한다."""
    docs = tmp_path / "docs"
    plan_path = _write_plan(docs)
    _write_skeleton(docs)

    rc = hmod.cmd_migrate_skeleton_hash(plan_path, apply=False, no_backup=False)
    captured = capsys.readouterr()

    assert rc == 0
    result = json.loads(captured.out)
    expected = _expected_hash(_SKELETON_CONTENT)
    assert result["new_hash"] == expected
    assert result["old_hash"] == ""
    assert result["applied"] is False
    assert result["backup_path"] is None


# ── 테스트 2: --apply — hash 갱신 + backup 생성 ───────────────────────────


def test_apply_updates_hash_in_plan(
    hmod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """--apply 후 plan 파일에 skeleton_hash 가 기록되어야 한다."""
    docs = tmp_path / "docs"
    plan_path = _write_plan(docs)
    _write_skeleton(docs)

    rc = hmod.cmd_migrate_skeleton_hash(plan_path, apply=True, no_backup=False)
    captured = capsys.readouterr()

    assert rc == 0
    result = json.loads(captured.out)
    assert result["applied"] is True

    # plan 파일에 skeleton_hash 가 실제로 기록되었는지 확인
    plan_text = plan_path.read_text(encoding="utf-8")
    expected = _expected_hash(_SKELETON_CONTENT)
    assert f"skeleton_hash: {expected}" in plan_text
    assert result["new_hash"] == expected


def test_apply_creates_backup(
    hmod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """--apply 후 .harness-backup-*.md 백업 파일이 생성되어야 한다."""
    docs = tmp_path / "docs"
    plan_path = _write_plan(docs)
    _write_skeleton(docs)
    original_content = plan_path.read_text(encoding="utf-8")

    rc = hmod.cmd_migrate_skeleton_hash(plan_path, apply=True, no_backup=False)
    captured = capsys.readouterr()

    assert rc == 0
    result = json.loads(captured.out)
    assert result["backup_path"] is not None

    backup_file = Path(result["backup_path"])
    assert backup_file.exists(), f"백업 파일 없음: {backup_file}"
    assert backup_file.name.startswith(".harness-backup-")
    assert backup_file.name.endswith(".md")
    # 백업 내용 = 수정 전 plan
    assert backup_file.read_text(encoding="utf-8") == original_content


def test_apply_no_backup_flag(
    hmod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """--no-backup 시 백업 파일이 생성되지 않아야 한다."""
    docs = tmp_path / "docs"
    plan_path = _write_plan(docs)
    _write_skeleton(docs)

    rc = hmod.cmd_migrate_skeleton_hash(plan_path, apply=True, no_backup=True)
    captured = capsys.readouterr()

    assert rc == 0
    result = json.loads(captured.out)
    assert result["applied"] is True
    assert result["backup_path"] is None

    # docs 디렉토리에 backup 파일 없어야 함
    backup_files = list(docs.glob(".harness-backup-*.md"))
    assert backup_files == [], f"예상치 못한 백업 파일: {backup_files}"


# ── 테스트 3: 이미 hash 있는 plan → WARN + 종료, 미수정 ───────────────────


def test_existing_hash_warns_and_no_change(
    hmod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """skeleton_hash 가 이미 있는 plan 은 WARN 을 내고 파일을 수정하지 않는다."""
    docs = tmp_path / "docs"
    plan_path = _write_plan(docs, content=_MINIMAL_PLAN_WITH_HASH)
    _write_skeleton(docs)
    content_before = plan_path.read_text(encoding="utf-8")

    rc = hmod.cmd_migrate_skeleton_hash(plan_path, apply=True, no_backup=False)
    captured = capsys.readouterr()

    assert rc == 0  # WARN 은 exit 0 (not a hard failure)
    result = json.loads(captured.out)
    assert result["applied"] is False
    assert "warn" in result
    # 파일 미수정
    assert plan_path.read_text(encoding="utf-8") == content_before
    # 백업도 없어야 함
    backup_files = list(docs.glob(".harness-backup-*.md"))
    assert backup_files == []


# ── 테스트 4: skeleton.md 없으면 FAIL + exit 3 ────────────────────────────


def test_skeleton_missing_returns_error(hmod: ModuleType, tmp_path: Path) -> None:
    """skeleton.md 없으면 exit 3 으로 종료 (FAIL)."""
    docs = tmp_path / "docs"
    plan_path = _write_plan(docs)
    # skeleton.md 생성 안 함

    rc = hmod.cmd_migrate_skeleton_hash(plan_path, apply=False, no_backup=False)

    assert rc == 3


# ── 테스트 5: plan 없으면 exit 3 ──────────────────────────────────────────


def test_plan_missing_returns_error(hmod: ModuleType, tmp_path: Path) -> None:
    """plan 파일이 없으면 exit 3 으로 종료."""
    fake_plan = tmp_path / "docs" / "harness-plan.md"

    rc = hmod.cmd_migrate_skeleton_hash(fake_plan, apply=False, no_backup=False)

    assert rc == 3


# ── 테스트 6: hash 는 CRLF/LF 정규화 후 계산 ─────────────────────────────


def test_hash_normalizes_crlf(
    hmod: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """CRLF skeleton.md 와 LF skeleton.md 의 hash 가 동일해야 한다."""
    lf_content = "# Overview\n\nContent.\n"
    crlf_content = lf_content.replace("\n", "\r\n")

    # LF 버전
    docs_lf = tmp_path / "lf" / "docs"
    plan_lf = _write_plan(docs_lf)
    (docs_lf / "skeleton.md").write_text(lf_content, encoding="utf-8")

    rc_lf = hmod.cmd_migrate_skeleton_hash(plan_lf, apply=False, no_backup=False)
    out_lf = capsys.readouterr().out
    assert rc_lf == 0
    hash_lf = json.loads(out_lf)["new_hash"]

    # CRLF 버전
    docs_crlf = tmp_path / "crlf" / "docs"
    plan_crlf = _write_plan(docs_crlf)
    (docs_crlf / "skeleton.md").write_bytes(crlf_content.encode("utf-8"))

    rc_crlf = hmod.cmd_migrate_skeleton_hash(plan_crlf, apply=False, no_backup=False)
    out_crlf = capsys.readouterr().out
    assert rc_crlf == 0
    hash_crlf = json.loads(out_crlf)["new_hash"]

    assert hash_lf == hash_crlf, "CRLF/LF 정규화 후 hash 가 동일해야 함"
