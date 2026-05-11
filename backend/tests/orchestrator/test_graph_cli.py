"""harness graph CLI 서브커맨드 테스트 (Group 4 Step 3).

subprocess 로 harness CLI 를 직접 실행하여 동작 검증.
임시 파일/디렉토리는 tmp_path fixture 로 격리.
"""
from __future__ import annotations

import glob
import subprocess
import sys
from pathlib import Path

import pytest

# harness CLI 절대 경로
_HARNESS_CLI = Path.home() / ".claude" / "harness" / "bin" / "harness"

# 챙겼니 tasks.md 샘플 — CLI 테스트용 최소 내용
_SAMPLE_TASKS_MD = """\
# Tasks — 테스트

### Phase 1 — MVP

| ID | 에이전트 | 의존성 | 설명 | 상태 |
|---|---|---|---|---|
| T-001 | mobile_coder_rn | - | 초기화 | 대기 |
| T-002 | mobile_coder_rn | T-001 | 설정 | 대기 |
| T-003 | mobile_coder_rn | T-001, T-002 | 컴포넌트 | 대기 |

### Phase 2+ — 확장

| ID | 에이전트 | 의존성 | 설명 | 상태 |
|---|---|---|---|---|
| T-101 | mobile_coder_rn | - | 캐시 | 대기 |
"""

_SECTION_HEADER = "## 의존성 그래프 (자동 생성)"


def _run_harness(*args: str) -> subprocess.CompletedProcess[str]:
    """harness CLI 를 현재 Python 인터프리터로 실행."""
    return subprocess.run(
        [sys.executable, str(_HARNESS_CLI), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


# ── Test 12: stdout 출력 — flowchart TD 포함 ──────────────────────────────────


def test_cli_graph_stdout(tmp_path: Path) -> None:
    """임시 tasks.md + harness graph <path> → stdout 에 'flowchart TD' 포함."""
    tasks_file = tmp_path / "tasks.md"
    tasks_file.write_text(_SAMPLE_TASKS_MD, encoding="utf-8")

    result = _run_harness("graph", str(tasks_file))

    assert result.returncode == 0, (
        f"exit code {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "flowchart TD" in result.stdout, (
        f"'flowchart TD' 없음. stdout:\n{result.stdout}"
    )
    # 파일은 변경되지 않아야 함
    assert tasks_file.read_text(encoding="utf-8") == _SAMPLE_TASKS_MD


# ── Test 13: --inject — 섹션 추가 ─────────────────────────────────────────────


def test_cli_graph_inject_creates_section(tmp_path: Path) -> None:
    """tasks.md 에 섹션 없음 + --inject → 파일 끝에 섹션 추가."""
    tasks_file = tmp_path / "tasks.md"
    tasks_file.write_text(_SAMPLE_TASKS_MD, encoding="utf-8")

    result = _run_harness("graph", str(tasks_file), "--inject")

    assert result.returncode == 0, (
        f"exit code {result.returncode}\nstderr: {result.stderr}"
    )
    updated = tasks_file.read_text(encoding="utf-8")
    assert _SECTION_HEADER in updated, (
        f"섹션 헤더 없음. 파일 내용:\n{updated}"
    )
    assert "```mermaid" in updated
    assert "flowchart TD" in updated


# ── Test 14: --inject 멱등성 ───────────────────────────────────────────────────


def test_cli_graph_inject_idempotent(tmp_path: Path) -> None:
    """--inject 두 번 실행 → 섹션 헤더 1개만 (중복 없음), 본문 정상."""
    tasks_file = tmp_path / "tasks.md"
    tasks_file.write_text(_SAMPLE_TASKS_MD, encoding="utf-8")

    # 1차 inject
    r1 = _run_harness("graph", str(tasks_file), "--inject")
    assert r1.returncode == 0, f"1차 inject 실패:\n{r1.stderr}"

    # 2차 inject
    r2 = _run_harness("graph", str(tasks_file), "--inject")
    assert r2.returncode == 0, f"2차 inject 실패:\n{r2.stderr}"

    updated = tasks_file.read_text(encoding="utf-8")
    count = updated.count(_SECTION_HEADER)
    assert count == 1, (
        f"섹션 헤더가 {count}개 발견 — 중복 추가됨:\n{updated}"
    )
    # mermaid 블록도 1개만
    assert updated.count("```mermaid") == 1


# ── Test 15: --inject 백업 생성 ───────────────────────────────────────────────


def test_cli_graph_inject_creates_backup(tmp_path: Path) -> None:
    """--inject 후 .backup-pre-graph-inject-*.md 파일 존재."""
    tasks_file = tmp_path / "tasks.md"
    tasks_file.write_text(_SAMPLE_TASKS_MD, encoding="utf-8")

    result = _run_harness("graph", str(tasks_file), "--inject")
    assert result.returncode == 0, f"inject 실패:\n{result.stderr}"

    backup_files = list(tmp_path.glob(".backup-pre-graph-inject-*.md"))
    assert backup_files, (
        f"백업 파일 없음. {tmp_path} 내용: {list(tmp_path.iterdir())}"
    )
    # 백업 내용이 원본과 동일해야 함
    backup_content = backup_files[0].read_text(encoding="utf-8")
    assert backup_content == _SAMPLE_TASKS_MD, "백업 내용이 원본과 다름"
