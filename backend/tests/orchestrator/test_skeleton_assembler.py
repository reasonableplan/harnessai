"""skeleton_assembler 단위 테스트.

모든 픽스처는 tmp_path 기반.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from src.orchestrator.skeleton_assembler import (
    FragmentNotFoundError,
    SkeletonAssembler,
)


def _write_fragment(
    dir_: Path,
    section_id: str,
    *,
    title: str | None = None,
    body_extra: str = "",
) -> Path:
    """조각 파일 작성 — frontmatter + {{section_number}} 본문."""
    dir_.mkdir(parents=True, exist_ok=True)
    title = title or section_id.title()
    text = dedent(
        f"""\
        ---
        id: {section_id}
        name: {title}
        required_when: always
        description: test fragment
        ---

        ## {{{{section_number}}}}. {title}

        Body content for {section_id}.
        {body_extra}
        """
    )
    path = dir_ / f"{section_id}.md"
    path.write_text(text, encoding="utf-8")
    return path


# ── 조각 로드 ─────────────────────────────────────────────────────────


def test_load_fragment_strips_frontmatter(tmp_path: Path) -> None:
    harness = tmp_path / "harness"
    _write_fragment(harness / "templates" / "skeleton", "overview")
    asm = SkeletonAssembler(harness_dir=harness)
    body = asm.load_fragment("overview")
    assert "---" not in body[:10]  # frontmatter 제거됨
    assert "## {{section_number}}. Overview" in body
    assert "Body content for overview." in body


def test_load_fragment_caches(tmp_path: Path) -> None:
    harness = tmp_path / "harness"
    _write_fragment(harness / "templates" / "skeleton", "overview")
    asm = SkeletonAssembler(harness_dir=harness)
    a = asm.load_fragment("overview")
    b = asm.load_fragment("overview")
    assert a is b


def test_missing_fragment_raises(tmp_path: Path) -> None:
    harness = tmp_path / "harness"
    (harness / "templates" / "skeleton").mkdir(parents=True)
    asm = SkeletonAssembler(harness_dir=harness)
    with pytest.raises(FragmentNotFoundError):
        asm.load_fragment("nonexistent")


def test_local_override_wins(tmp_path: Path) -> None:
    harness = tmp_path / "harness"
    project = tmp_path / "project"

    _write_fragment(harness / "templates" / "skeleton", "overview", body_extra="GLOBAL")
    _write_fragment(
        project / ".claude" / "harness" / "templates" / "skeleton",
        "overview",
        body_extra="LOCAL",
    )

    asm = SkeletonAssembler(harness_dir=harness, project_dir=project)
    body = asm.load_fragment("overview")
    assert "LOCAL" in body
    assert "GLOBAL" not in body


# ── 조립 ─────────────────────────────────────────────────────────────


def test_assemble_substitutes_section_numbers(tmp_path: Path) -> None:
    harness = tmp_path / "harness"
    frag_dir = harness / "templates" / "skeleton"
    _write_fragment(frag_dir, "overview", title="Overview")
    _write_fragment(frag_dir, "stack", title="Stack")
    _write_fragment(frag_dir, "errors", title="Errors")

    asm = SkeletonAssembler(harness_dir=harness)
    out = asm.assemble(["overview", "stack", "errors"], title="Project X")

    assert out.startswith("# Project X")
    # 섹션 번호 치환 확인
    assert "## 1. Overview" in out
    assert "## 2. Stack" in out
    assert "## 3. Errors" in out
    # 플레이스홀더 잔재 없음
    assert "{{section_number}}" not in out


def test_assemble_dedupes_section_ids(tmp_path: Path) -> None:
    """중복 섹션 ID 입력 시 첫 등장만 사용 (재번호 없음)."""
    harness = tmp_path / "harness"
    frag_dir = harness / "templates" / "skeleton"
    _write_fragment(frag_dir, "a")
    _write_fragment(frag_dir, "b")

    asm = SkeletonAssembler(harness_dir=harness)
    out = asm.assemble(["a", "b", "a", "b"])
    # b 가 두 번 등장하면 안 됨 — section_number 가 한 번만
    assert out.count("## 1. A") == 1
    assert out.count("## 2. B") == 1


def test_assemble_empty_returns_only_title(tmp_path: Path) -> None:
    harness = tmp_path / "harness"
    (harness / "templates" / "skeleton").mkdir(parents=True)
    asm = SkeletonAssembler(harness_dir=harness)
    out = asm.assemble([], title="Empty")
    assert out.strip() == "# Empty"


def test_assemble_uses_default_title(tmp_path: Path) -> None:
    harness = tmp_path / "harness"
    _write_fragment(harness / "templates" / "skeleton", "overview")
    asm = SkeletonAssembler(harness_dir=harness)
    out = asm.assemble(["overview"])
    assert out.startswith("# Project Skeleton")


def test_assemble_missing_fragment_raises(tmp_path: Path) -> None:
    harness = tmp_path / "harness"
    _write_fragment(harness / "templates" / "skeleton", "overview")
    asm = SkeletonAssembler(harness_dir=harness)
    with pytest.raises(FragmentNotFoundError, match="ghost"):
        asm.assemble(["overview", "ghost"])


def test_assemble_with_local_override(tmp_path: Path) -> None:
    """프로젝트 로컬 조각이 글로벌을 이긴다."""
    harness = tmp_path / "harness"
    project = tmp_path / "project"

    _write_fragment(harness / "templates" / "skeleton", "overview", body_extra="GLOBAL")
    _write_fragment(
        project / ".claude" / "harness" / "templates" / "skeleton",
        "overview",
        body_extra="LOCAL",
    )

    asm = SkeletonAssembler(harness_dir=harness, project_dir=project)
    out = asm.assemble(["overview"])
    assert "LOCAL" in out
    assert "GLOBAL" not in out
