"""V2: harness integrity verbose 출력 + --quiet 모드 테스트.

대상: check_integrity_verbose(), print_integrity_report()
"""

from __future__ import annotations

import io
from pathlib import Path
from textwrap import dedent
from unittest.mock import patch

# fixtures: harness_module (from conftest)

PLAN_MINIMAL = (
    dedent("""
    ---
    project: test
    profiles: []
    pipeline:
      steps: [init]
      current_step: built
      completed_steps: []
      skipped_steps: []
      gstack_mode: manual
    skeleton_sections: {included: [overview]}
    verify_history: []
    ---
""").strip()
    + "\n"
)


def _make_project(tmp_path: Path, *, skeleton: str | None = None) -> Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "harness-plan.md").write_text(PLAN_MINIMAL, encoding="utf-8")
    if skeleton is not None:
        (docs / "skeleton.md").write_text(skeleton, encoding="utf-8")
    return tmp_path


# ── check_integrity_verbose 반환값 검증 ──────────────────────────────────────


def test_verbose_result_skeleton_exists(harness_module, tmp_path: Path) -> None:
    """skeleton.md 있으면 skeleton_exists=True, plan_path/skeleton_path 채워짐."""
    (tmp_path / "pyproject.toml").touch()
    skeleton = "```filesystem\npyproject.toml\n```\n"
    project = _make_project(tmp_path, skeleton=skeleton)

    report = harness_module.Report()
    vr = harness_module.check_integrity_verbose(project, None, report)

    assert vr is not None
    assert vr.skeleton_exists is True
    assert vr.plan_path is not None
    assert vr.skeleton_path is not None


def test_verbose_result_skeleton_missing(harness_module, tmp_path: Path) -> None:
    """skeleton.md 없으면 skeleton_exists=False, filesystem 블록 카운트 0."""
    project = _make_project(tmp_path, skeleton=None)

    report = harness_module.Report()
    vr = harness_module.check_integrity_verbose(project, None, report)

    assert vr is not None
    assert vr.skeleton_exists is False
    assert vr.filesystem_blocks == 0
    assert vr.filesystem_paths_declared == 0


def test_verbose_result_filesystem_paths_counted(harness_module, tmp_path: Path) -> None:
    """filesystem 블록에 선언된 경로 수 + 실재 경로 수 정확히 카운트."""
    (tmp_path / "a.txt").touch()
    (tmp_path / "src").mkdir()
    # c.txt 는 선언만 하고 미생성 → paths_ok = 2/3
    skeleton = "```filesystem\na.txt\nsrc/\nc.txt\n```\n"
    project = _make_project(tmp_path, skeleton=skeleton)

    report = harness_module.Report()
    vr = harness_module.check_integrity_verbose(project, None, report)

    assert vr is not None
    assert vr.filesystem_blocks == 1
    assert vr.filesystem_paths_declared == 3
    assert vr.filesystem_paths_ok == 2


def test_verbose_result_placeholder_count(harness_module, tmp_path: Path) -> None:
    """미치환 placeholder → placeholder_count > 0."""
    (tmp_path / "pyproject.toml").touch()
    skeleton = "Description of <pkg> module.\n```filesystem\npyproject.toml\n```\n"
    project = _make_project(tmp_path, skeleton=skeleton)

    report = harness_module.Report()
    vr = harness_module.check_integrity_verbose(project, None, report)

    assert vr is not None
    assert vr.placeholder_count >= 1


def test_verbose_result_no_filesystem_block(harness_module, tmp_path: Path) -> None:
    """filesystem 블록 없으면 filesystem_blocks=0."""
    skeleton = "# 섹션\n\n내용.\n"
    project = _make_project(tmp_path, skeleton=skeleton)

    report = harness_module.Report()
    vr = harness_module.check_integrity_verbose(project, None, report)

    assert vr is not None
    assert vr.filesystem_blocks == 0
    assert vr.filesystem_paths_declared == 0


def test_verbose_result_plan_missing_returns_none(harness_module, tmp_path: Path) -> None:
    """plan 파일 없으면 None 반환."""
    report = harness_module.Report()
    vr = harness_module.check_integrity_verbose(tmp_path, None, report)
    assert vr is None
    assert report.error_count >= 1


# ── print_integrity_report verbose 출력 검증 ─────────────────────────────────


def _capture_integrity_print(harness_module, report, vr, *, quiet: bool = False) -> str:
    """print_integrity_report 출력을 문자열로 캡처."""
    buf = io.StringIO()
    with patch(
        "builtins.print", side_effect=lambda *a, **kw: buf.write(" ".join(str(x) for x in a) + "\n")
    ):
        harness_module.print_integrity_report(report, vr, quiet=quiet)
    return buf.getvalue()


def test_verbose_output_contains_project_path(harness_module, tmp_path: Path) -> None:
    """verbose 출력에 [integrity] project: <path> 포함."""
    skeleton = "```filesystem\n```\n"
    project = _make_project(tmp_path, skeleton=skeleton)

    report = harness_module.Report()
    vr = harness_module.check_integrity_verbose(project, None, report)
    out = _capture_integrity_print(harness_module, report, vr)

    assert "[integrity] project:" in out
    assert str(project) in out


def test_verbose_output_shows_skeleton_check_items(harness_module, tmp_path: Path) -> None:
    """verbose 출력에 skeleton.md 검사 대상 + filesystem/placeholder 항목 포함."""
    (tmp_path / "pyproject.toml").touch()
    skeleton = "```filesystem\npyproject.toml\n```\n"
    project = _make_project(tmp_path, skeleton=skeleton)

    report = harness_module.Report()
    vr = harness_module.check_integrity_verbose(project, None, report)
    out = _capture_integrity_print(harness_module, report, vr)

    assert "skeleton.md" in out
    # 검사 통과 항목 표시
    assert "✓" in out


def test_verbose_output_shows_warn_on_drift(harness_module, tmp_path: Path) -> None:
    """drift WARN 있으면 verbose 출력에 extras + [WARN] 포함."""
    import yaml

    skeleton = "```filesystem\npyproject.toml\n```\n"
    (tmp_path / "pyproject.toml").touch()
    project = _make_project(tmp_path, skeleton=skeleton)

    # profiles 디렉토리 생성 (HARNESS_ROOT 대신 직접 경로 주입)
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    profile_data = {
        "id": "test-verbose",
        "file_structure": "src/\n",
    }
    profile_md = "---\n" + yaml.safe_dump(profile_data, allow_unicode=True) + "---\n"
    (profiles_dir / "test-verbose.md").write_text(profile_md, encoding="utf-8")

    # extra dir 생성
    (tmp_path / "extra_dir").mkdir()

    # _check_file_structure_drift 를 직접 호출해 report 에 WARN 기록
    report = harness_module.Report()
    harness_module._check_file_structure_drift(tmp_path, profiles_dir, report)

    # IntegrityVerboseResult 에 drift_checks 주입
    vr = harness_module.IntegrityVerboseResult(
        project=project,
        plan_path=project / "docs" / "harness-plan.md",
        skeleton_path=project / "docs" / "skeleton.md",
        skeleton_exists=True,
        filesystem_blocks=1,
        filesystem_paths_declared=1,
        filesystem_paths_ok=1,
        placeholder_count=0,
        drift_checks=[("test-verbose", ["extra_dir/"], [])],
    )
    out = _capture_integrity_print(harness_module, report, vr)

    assert "[WARN]" in out or "extras" in out
    assert "extra_dir" in out


def test_quiet_output_no_verbose_details(harness_module, tmp_path: Path) -> None:
    """--quiet 모드: [integrity] project: / ✓ 항목 없고 요약만."""
    (tmp_path / "pyproject.toml").touch()
    skeleton = "```filesystem\npyproject.toml\n```\n"
    project = _make_project(tmp_path, skeleton=skeleton)

    report = harness_module.Report()
    vr = harness_module.check_integrity_verbose(project, None, report)
    out = _capture_integrity_print(harness_module, report, vr, quiet=True)

    # verbose 전용 라인 없어야 함
    assert "[integrity] project:" not in out
    assert "[integrity] skeleton.md:" not in out
    # 요약 라인은 있어야 함
    assert "Files checked:" in out


def test_quiet_output_contains_summary(harness_module, tmp_path: Path) -> None:
    """--quiet 모드 출력에 Files checked / Errors / Warnings 요약 포함."""
    skeleton = "# 내용\n"
    project = _make_project(tmp_path, skeleton=skeleton)

    report = harness_module.Report()
    vr = harness_module.check_integrity_verbose(project, None, report)
    out = _capture_integrity_print(harness_module, report, vr, quiet=True)

    assert "Files checked:" in out
    assert "Errors:" in out
    assert "Warnings:" in out
