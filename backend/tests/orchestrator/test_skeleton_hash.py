"""Regression tests for skeleton_hash utilities (Group 2 Step 3)."""

from __future__ import annotations

from pathlib import Path

from src.orchestrator.skeleton_hash import (
    SkeletonHashCheckResult,
    check_skeleton_hash,
    compute_section_hashes,
    compute_skeleton_hash,
)

# ── compute_section_hashes (per-section, ID-keyed) ──────────────────


def test_section_hashes_change_only_for_edited_section(tmp_path: Path) -> None:
    """한 섹션만 수정하면 그 섹션의 hash 만 바뀐다 (결정론적 rebuild 의 기반)."""
    p = tmp_path / "skeleton.md"
    p.write_text(
        "# T\n\n## 1. 프로젝트 개요\nbefore\n\n## 2. 기술 스택\nstack\n",
        encoding="utf-8",
    )
    before = compute_section_hashes(p)
    p.write_text(
        "# T\n\n## 1. 프로젝트 개요\nAFTER\n\n## 2. 기술 스택\nstack\n",
        encoding="utf-8",
    )
    after = compute_section_hashes(p)
    assert set(before) == {"overview", "stack"}
    assert before["stack"] == after["stack"]
    assert before["overview"] != after["overview"]


def test_section_hashes_crlf_lf_normalized(tmp_path: Path) -> None:
    lf = tmp_path / "lf.md"
    crlf = tmp_path / "crlf.md"
    lf.write_bytes("# T\n\n## 1. 프로젝트 개요\nbody\n".encode())
    crlf.write_bytes("# T\r\n\r\n## 1. 프로젝트 개요\r\nbody\r\n".encode())
    assert compute_section_hashes(lf) == compute_section_hashes(crlf)


def test_section_hashes_missing_file_returns_empty(tmp_path: Path) -> None:
    assert compute_section_hashes(tmp_path / "nope.md") == {}


def test_section_hashes_unknown_heading_skipped(tmp_path: Path) -> None:
    """SECTION_TITLES 에 없는 제목의 헤딩은 ID 로 해석 불가 — 결과에서 제외."""
    p = tmp_path / "skeleton.md"
    p.write_text("## 1. 프로젝트 개요\nbody\n\n## 2. 정체불명 섹션\nx\n", encoding="utf-8")
    assert set(compute_section_hashes(p)) == {"overview"}


def test_compute_hash_deterministic(tmp_path: Path) -> None:
    """Same content produces same hash across calls."""
    p = tmp_path / "skeleton.md"
    p.write_text("# Project\n\n## 1. Overview\nBody\n", encoding="utf-8")
    h1 = compute_skeleton_hash(p)
    h2 = compute_skeleton_hash(p)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_compute_hash_crlf_lf_normalized(tmp_path: Path) -> None:
    """CRLF and LF line endings hash identically (cross-platform safety)."""
    lf = tmp_path / "lf.md"
    crlf = tmp_path / "crlf.md"
    lf.write_bytes(b"# A\n\n## 1. B\nbody\n")
    crlf.write_bytes(b"# A\r\n\r\n## 1. B\r\nbody\r\n")
    assert compute_skeleton_hash(lf) == compute_skeleton_hash(crlf)


def test_compute_hash_missing_file_returns_empty(tmp_path: Path) -> None:
    """Non-existent path returns empty string, not an exception."""
    missing = tmp_path / "does-not-exist.md"
    assert compute_skeleton_hash(missing) == ""


def test_check_match_when_hash_unchanged(tmp_path: Path) -> None:
    """plan_hash == current_hash → is_match=True, not legacy."""
    p = tmp_path / "skeleton.md"
    p.write_text("body\n", encoding="utf-8")
    plan_hash = compute_skeleton_hash(p)

    result = check_skeleton_hash(plan_hash, p)

    assert isinstance(result, SkeletonHashCheckResult)
    assert result.is_match is True
    assert result.is_legacy is False
    assert result.skeleton_missing is False
    assert result.plan_hash == plan_hash
    assert result.current_hash == plan_hash


def test_check_mismatch_after_external_edit(tmp_path: Path) -> None:
    """Different hashes → is_match=False, not legacy (genuine drift)."""
    p = tmp_path / "skeleton.md"
    p.write_text("original body\n", encoding="utf-8")
    plan_hash = compute_skeleton_hash(p)

    # Simulate external modification
    p.write_text("modified body\n", encoding="utf-8")

    result = check_skeleton_hash(plan_hash, p)

    assert result.is_match is False
    assert result.is_legacy is False
    assert result.skeleton_missing is False
    assert result.plan_hash != result.current_hash


def test_check_legacy_when_plan_hash_empty(tmp_path: Path) -> None:
    """Empty plan_hash → is_legacy=True, is_match=False (no baseline)."""
    p = tmp_path / "skeleton.md"
    p.write_text("body\n", encoding="utf-8")

    result = check_skeleton_hash("", p)

    assert result.is_legacy is True
    assert result.is_match is False
    assert result.skeleton_missing is False


def test_check_missing_skeleton(tmp_path: Path) -> None:
    """skeleton.md missing → skeleton_missing=True, is_match=False."""
    missing = tmp_path / "skeleton.md"  # never created
    result = check_skeleton_hash("any-hash", missing)

    assert result.skeleton_missing is True
    assert result.is_match is False
    assert result.current_hash == ""
