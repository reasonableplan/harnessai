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
    find_placeholders,
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


# ── find_placeholders ──────────────────────────────────────────────


def test_find_placeholders_empty_text_returns_empty() -> None:
    assert find_placeholders("") == {}


def test_find_placeholders_clean_skeleton() -> None:
    text = dedent("""
        # Project
        ## Stack
        Python, FastAPI
    """).strip()
    assert find_placeholders(text) == {}


def test_find_placeholders_reports_body_placeholders_with_line_numbers() -> None:
    text = dedent("""
        # Project
        Description of <pkg> module.

        Next line references <cmd_a> again.
    """).strip()
    result = find_placeholders(text)
    assert result == {"<pkg>": [2], "<cmd_a>": [4]}


def test_find_placeholders_ignores_non_filesystem_code_blocks() -> None:
    text = dedent("""
        # Project

        ```python
        def <func_name>():  # placeholder in example code — should be ignored
            return <return_type>
        ```

        Real placeholder at line 8: <pkg>
    """).strip()
    result = find_placeholders(text)
    assert list(result.keys()) == ["<pkg>"]
    assert result["<pkg>"] == [8]


def test_find_placeholders_catches_filesystem_block_placeholders() -> None:
    text = dedent("""
        # Project

        ```filesystem
        src/<pkg>/
          cli.py
        ```
    """).strip()
    result = find_placeholders(text)
    assert "<pkg>" in result
    assert result["<pkg>"] == [4]


def test_find_placeholders_line_numbers_preserved_after_code_block_strip() -> None:
    """코드 블록 치환 시 개행 보존 — placeholder 라인 번호가 원본과 일치."""
    text = dedent("""
        # Header

        ```python
        line 4 in block
        line 5 in block
        line 6 in block
        ```

        <pkg> at line 9
    """).strip()
    result = find_placeholders(text)
    assert result["<pkg>"] == [9]


def test_find_placeholders_multiple_occurrences_same_placeholder() -> None:
    text = "<pkg>\n<pkg>\n<pkg>"
    result = find_placeholders(text)
    assert result == {"<pkg>": [1, 2, 3]}


def test_find_placeholders_excludes_html_tags() -> None:
    """ui-assistant 2차 E2E 에서 발견: <div>, <pre> 등 HTML 태그 false positive 방지."""
    text = dedent("""
        # React 컴포넌트 예시

        `<div>` 안에 렌더, `<pre>` 로 코드 표시. `<svg><path>` 아이콘.

        실제 placeholder: <pkg>
    """).strip()
    result = find_placeholders(text)
    assert result == {"<pkg>": [5]}
    assert "<div>" not in result
    assert "<pre>" not in result
    assert "<svg>" not in result
    assert "<path>" not in result


def test_find_placeholders_keeps_snake_case_placeholders() -> None:
    """HTML 이 아닌 snake_case 는 placeholder 로 유지 (<name>, <type>, <value> 등)."""
    text = "<name> and <type> and <value> are placeholders"
    result = find_placeholders(text)
    assert "<name>" in result
    assert "<type>" in result
    assert "<value>" in result


def test_find_placeholders_excludes_inline_backtick_examples() -> None:
    """ui-assistant 2차 E2E 에서 발견: 마크다운 인라인 코드 안의 <pkg> 는
    '템플릿 형식 표시' 이지 실제 치환 대상 아님."""
    text = dedent("""
        ## 의존성 변경 포맷

        | 날짜 | 패키지 |
        | `<YYYY-MM-DD>` | `<pkg>` |

        실제 누락 placeholder: <missing>
    """).strip()
    result = find_placeholders(text)
    assert "<pkg>" not in result           # 백틱 안 → 템플릿 예시
    assert "<YYYY-MM-DD>" not in result    # 동일
    assert "<missing>" in result           # 백틱 밖 → 실제 누락
