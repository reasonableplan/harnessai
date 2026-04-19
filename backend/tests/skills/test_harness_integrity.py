"""harness CLI 의 `integrity` 서브커맨드 단위 테스트.

대상 함수: `check_integrity()` — skeleton.md 선언 ↔ 실재 FS 정합성 + placeholder.

모든 픽스처는 tmp_path 기반.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

# fixtures: harness_module (from conftest)


PLAN_MINIMAL = dedent("""
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
""").strip() + "\n"


def _make_project(tmp_path: Path, *, plan: bool = True, skeleton: str | None = None) -> Path:
    """tmp_path 에 docs/harness-plan.md (+ optional skeleton.md) 를 작성."""
    docs = tmp_path / "docs"
    docs.mkdir()
    if plan:
        (docs / "harness-plan.md").write_text(PLAN_MINIMAL, encoding="utf-8")
    if skeleton is not None:
        (docs / "skeleton.md").write_text(skeleton, encoding="utf-8")
    return tmp_path


def test_integrity_passes_on_clean_skeleton(harness_module, tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").touch()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "cli.py").touch()
    skeleton = dedent("""
        # Test

        ```filesystem
        pyproject.toml
        src/
          cli.py
        ```
    """).strip()
    project = _make_project(tmp_path, skeleton=skeleton)

    report = harness_module.Report()
    harness_module.check_integrity(project, None, report)
    assert report.error_count == 0, [i.message for i in report.issues if i.severity == "error"]


def test_integrity_fails_when_declared_path_missing(harness_module, tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").touch()
    # src/ 가 선언되었으나 실제로는 없음
    skeleton = dedent("""
        ```filesystem
        pyproject.toml
        src/
          missing.py
        ```
    """).strip()
    project = _make_project(tmp_path, skeleton=skeleton)

    report = harness_module.Report()
    harness_module.check_integrity(project, None, report)
    msgs = [i.message for i in report.issues if i.severity == "error"]
    assert any("src/" in m for m in msgs)
    assert any("missing.py" in m for m in msgs)


def test_integrity_warns_and_skips_when_skeleton_missing(harness_module, tmp_path: Path) -> None:
    """skeleton.md 없으면 WARN 만 내고 error 없이 통과 (초기 상태)."""
    project = _make_project(tmp_path, skeleton=None)
    report = harness_module.Report()
    harness_module.check_integrity(project, None, report)
    assert report.error_count == 0
    assert report.warn_count >= 1


def test_integrity_errors_when_plan_missing(harness_module, tmp_path: Path) -> None:
    # docs/harness-plan.md 자체가 없음
    project = tmp_path  # 빈 dir
    report = harness_module.Report()
    harness_module.check_integrity(project, None, report)
    assert report.error_count >= 1
    # file 필드에 harness-plan.md 가 들어가야 함 (message 는 "파일 없음")
    assert any(i.file == "harness-plan.md" for i in report.issues)


def test_integrity_detects_placeholders_in_body(harness_module, tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").touch()
    skeleton = dedent("""
        # Test

        Description of <pkg> module.

        ```filesystem
        pyproject.toml
        ```
    """).strip()
    project = _make_project(tmp_path, skeleton=skeleton)
    report = harness_module.Report()
    harness_module.check_integrity(project, None, report)
    errs = [i.message for i in report.issues if i.severity == "error"]
    assert any("<pkg>" in m for m in errs)


def test_integrity_ignores_placeholders_in_python_code_blocks(
    harness_module, tmp_path: Path
) -> None:
    """```python 블록 내 placeholder 는 예제로 간주, error 로 보고 안 함."""
    (tmp_path / "pyproject.toml").touch()
    skeleton = dedent("""
        # Test

        Example code (placeholder in block should be ignored):

        ```python
        def <func>():
            return <value>
        ```

        ```filesystem
        pyproject.toml
        ```
    """).strip()
    project = _make_project(tmp_path, skeleton=skeleton)
    report = harness_module.Report()
    harness_module.check_integrity(project, None, report)
    errs = [i.message for i in report.issues if i.severity == "error"]
    assert not any("<func>" in m or "<value>" in m for m in errs)


def test_integrity_silent_when_filesystem_block_absent(
    harness_module, tmp_path: Path
) -> None:
    """```filesystem 블록 없으면 silent pass (opt-in feature)."""
    skeleton = "# Test\n\nNo filesystem section.\n"
    project = _make_project(tmp_path, skeleton=skeleton)
    report = harness_module.Report()
    harness_module.check_integrity(project, None, report)
    assert report.error_count == 0
    # filesystem 블록이 없으면 WARN/ERROR 둘 다 없어야 함 (완전 silent)
    fs_related = [
        i for i in report.issues if "filesystem" in i.message.lower()
    ]
    assert fs_related == []


def test_integrity_placeholder_line_number_accurate_after_code_block(
    harness_module, tmp_path: Path
) -> None:
    """code block 뒤 placeholder 의 라인 번호가 원본과 일치 (H1 회귀 방지)."""
    (tmp_path / "pyproject.toml").touch()
    # 코드 블록 (line 3-7) 뒤 placeholder (line 9)
    skeleton = (
        "# Test\n"                   # 1
        "\n"                          # 2
        "```python\n"                 # 3
        "line 4 in block\n"           # 4
        "line 5 in block\n"           # 5
        "line 6 in block\n"           # 6
        "```\n"                       # 7
        "\n"                          # 8
        "<pkg> at line 9\n"           # 9
        "\n"                          # 10
        "```filesystem\n"
        "pyproject.toml\n"
        "```\n"
    )
    project = _make_project(tmp_path, skeleton=skeleton)
    report = harness_module.Report()
    harness_module.check_integrity(project, None, report)
    placeholder_err = next(
        (i for i in report.issues if "<pkg>" in i.message), None
    )
    assert placeholder_err is not None
    assert "line 9" in placeholder_err.message


def test_integrity_explicit_plan_override(harness_module, tmp_path: Path) -> None:
    """--plan 으로 plan 경로를 직접 지정 — default 탐색 경로 밖의 plan 허용."""
    (tmp_path / "pyproject.toml").touch()
    custom_dir = tmp_path / "custom"
    custom_dir.mkdir()
    plan_path = custom_dir / "my-plan.md"
    plan_path.write_text(PLAN_MINIMAL, encoding="utf-8")
    skeleton = "```filesystem\npyproject.toml\n```\n"
    (custom_dir / "skeleton.md").write_text(skeleton, encoding="utf-8")

    report = harness_module.Report()
    harness_module.check_integrity(tmp_path, plan_path, report)
    assert report.error_count == 0
