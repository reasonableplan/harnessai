"""V5: failure_analyzer 단위 + 통합 테스트.

대상: extract_failed_files, match_failures_to_tasks, analyze_failure, CLI main()
"""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

import pytest

from src.orchestrator.failure_analyzer import (
    analyze_failure,
    extract_failed_files,
    match_failures_to_tasks,
)
from src.orchestrator.failure_analyzer import (
    main as analyzer_main,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


# ── extract_failed_files ──────────────────────────────────────────────────────


def test_extract_pytest_failed() -> None:
    """pytest FAILED 행 → 파일 경로 추출."""
    output = dedent("""\
        FAILED tests/api/test_auth.py::test_login_missing_fields
        FAILED tests/models/test_user.py::test_duplicate_email
    """)
    result = extract_failed_files(output)
    assert "tests/api/test_auth.py" in result
    assert "tests/models/test_user.py" in result


def test_extract_pyright_errors() -> None:
    """pyright 오류 행 → 파일 경로 추출."""
    output = dedent("""\
        src/services/auth.py:42 — Argument of type "str | None" is not assignable
        src/services/auth.py:67:5 — Return type mismatch
    """)
    result = extract_failed_files(output)
    assert "src/services/auth.py" in result
    # 중복 없이 한 번만
    assert result.count("src/services/auth.py") == 1


def test_extract_eslint_errors() -> None:
    """eslint 오류 행 → 파일 경로 추출."""
    output = "src/components/Login.tsx:42:5  error  no-unused-vars\n"
    result = extract_failed_files(output)
    assert "src/components/Login.tsx" in result


def test_extract_jest_fail() -> None:
    """jest FAIL 행 → 파일 경로 추출."""
    output = dedent("""\
        FAIL src/services/__tests__/auth.test.tsx
        FAIL src/screens/LoginScreen.test.tsx
    """)
    result = extract_failed_files(output)
    assert "src/services/__tests__/auth.test.tsx" in result
    assert "src/screens/LoginScreen.test.tsx" in result


def test_extract_jest_stack() -> None:
    """jest 스택 트레이스 at ... (file:line:col) → 파일 추출."""
    output = "    at Object.<anonymous> (src/utils/token.tsx:15:3)\n"
    result = extract_failed_files(output)
    assert "src/utils/token.tsx" in result


def test_extract_tsc_errors() -> None:
    """tsc 오류 행 → 파일 경로 추출."""
    output = "src/api/client.tsx(42,5): error TS2345: Argument of type ...\n"
    result = extract_failed_files(output)
    assert "src/api/client.tsx" in result


def test_extract_no_failures_returns_empty() -> None:
    """실패 신호 없는 출력 → 빈 리스트."""
    output = "All tests passed.\n42 passed in 1.23s\n"
    result = extract_failed_files(output)
    assert result == []


def test_extract_deduplicates_paths() -> None:
    """같은 파일이 여러 줄에 걸쳐 등장 → 한 번만 포함."""
    output = dedent("""\
        FAILED tests/api/test_auth.py::test_a
        FAILED tests/api/test_auth.py::test_b
        FAILED tests/api/test_auth.py::test_c
    """)
    result = extract_failed_files(output)
    assert result.count("tests/api/test_auth.py") == 1


def test_extract_windows_backslash_normalized() -> None:
    """Windows 백슬래시 경로 → 슬래시로 정규화."""
    output = "src\\services\\auth.py:42 — error\n"
    result = extract_failed_files(output)
    # 정규화 후 슬래시 경로로 포함
    assert any("/" in f for f in result)


def test_extract_mixed_formats() -> None:
    """여러 포맷 혼합 → 모두 추출."""
    output = dedent("""\
        FAILED tests/api/test_auth.py::test_login
        src/services/auth.py:42 — Type error
        src/components/Login.tsx:10:5  error  no-console
        FAIL src/screens/__tests__/Login.test.tsx
    """)
    result = extract_failed_files(output)
    assert "tests/api/test_auth.py" in result
    assert "src/services/auth.py" in result
    assert "src/components/Login.tsx" in result
    assert "src/screens/__tests__/Login.test.tsx" in result


# ── match_failures_to_tasks ───────────────────────────────────────────────────

_TASKS_MD_SAMPLE = dedent("""\
    | T-001 | backend_coder | - | 사용자 모델 | todo |

    **생성/수정 파일**:
    - `src/models/user.py`
    - `tests/models/test_user.py`

    | T-002 | backend_coder | T-001 | 인증 API | todo |

    **생성/수정 파일**:
    - `src/services/auth.py`
    - `src/api/auth_router.py`
    - `tests/api/test_auth.py`

    | T-003 | frontend_coder | T-002 | 로그인 화면 | todo |

    **생성/수정 파일**:
    - `src/screens/LoginScreen.tsx`
    - `src/screens/__tests__/LoginScreen.test.tsx`
""")


def test_match_single_task() -> None:
    """단일 파일 실패 → 해당 T-ID 매핑."""
    failed = ["tests/api/test_auth.py"]
    matches, unmatched = match_failures_to_tasks(failed, _TASKS_MD_SAMPLE)
    assert len(matches) == 1
    assert matches[0]["task_id"] == "T-002"
    assert "tests/api/test_auth.py" in matches[0]["files"]
    assert unmatched == []


def test_match_multiple_tasks() -> None:
    """여러 태스크에 걸친 실패 → 각 T-ID 매핑."""
    failed = ["tests/models/test_user.py", "src/services/auth.py"]
    matches, unmatched = match_failures_to_tasks(failed, _TASKS_MD_SAMPLE)
    task_ids = {m["task_id"] for m in matches}
    assert "T-001" in task_ids
    assert "T-002" in task_ids
    assert unmatched == []


def test_match_unmatched_file() -> None:
    """tasks.md 에 없는 파일 → unmatched_failures 에 포함."""
    failed = ["src/unknown/mystery.py"]
    matches, unmatched = match_failures_to_tasks(failed, _TASKS_MD_SAMPLE)
    assert matches == []
    assert "src/unknown/mystery.py" in unmatched


def test_match_empty_failures() -> None:
    """실패 파일 없으면 matches=[], unmatched=[]."""
    matches, unmatched = match_failures_to_tasks([], _TASKS_MD_SAMPLE)
    assert matches == []
    assert unmatched == []


def test_match_basename_matching() -> None:
    """경로가 달라도 basename 일치하면 매핑."""
    failed = ["test_auth.py"]  # 경로 없이 basename 만
    matches, unmatched = match_failures_to_tasks(failed, _TASKS_MD_SAMPLE)
    task_ids = {m["task_id"] for m in matches}
    assert "T-002" in task_ids


# ── analyze_failure 통합 ──────────────────────────────────────────────────────


def test_analyze_failure_full_flow() -> None:
    """전체 흐름: pytest 출력 + tasks.md → JSON 결과 구조 검증."""
    output = dedent("""\
        FAILED tests/api/test_auth.py::test_login_missing_fields
        FAILED tests/models/test_user.py::test_duplicate_email
        src/services/auth.py:42 — Type error
    """)
    result = analyze_failure(output, _TASKS_MD_SAMPLE)

    assert "failures" in result
    assert "matches" in result
    assert "unmatched_failures" in result

    assert "tests/api/test_auth.py" in result["failures"]
    assert "tests/models/test_user.py" in result["failures"]

    task_ids = {m["task_id"] for m in result["matches"]}
    assert "T-001" in task_ids
    assert "T-002" in task_ids


def test_analyze_failure_no_failures() -> None:
    """실패 없는 출력 → failures=[], matches=[], unmatched_failures=[]."""
    result = analyze_failure("All tests passed.\n", _TASKS_MD_SAMPLE)
    assert result["failures"] == []
    assert result["matches"] == []
    assert result["unmatched_failures"] == []


# ── CLI main() 통합 테스트 ────────────────────────────────────────────────────


def test_cli_with_output_file(tmp_path: Path) -> None:
    """CLI: output-file 경로 + tasks.md → JSON 출력."""
    output_file = tmp_path / "pytest-output.txt"
    output_file.write_text("FAILED tests/api/test_auth.py::test_login\n", encoding="utf-8")
    tasks_file = tmp_path / "tasks.md"
    tasks_file.write_text(_TASKS_MD_SAMPLE, encoding="utf-8")

    rc = analyzer_main([str(output_file), "--tasks", str(tasks_file)])
    assert rc == 0


def test_cli_missing_output_file(tmp_path: Path) -> None:
    """CLI: output 파일 없으면 exit 1."""
    tasks_file = tmp_path / "tasks.md"
    tasks_file.write_text(_TASKS_MD_SAMPLE, encoding="utf-8")

    rc = analyzer_main([str(tmp_path / "nonexistent.txt"), "--tasks", str(tasks_file)])
    assert rc == 1


def test_cli_missing_tasks_file(tmp_path: Path) -> None:
    """CLI: tasks.md 없으면 exit 1."""
    output_file = tmp_path / "output.txt"
    output_file.write_text("FAILED tests/test_foo.py::test_bar\n", encoding="utf-8")

    rc = analyzer_main([str(output_file), "--tasks", str(tmp_path / "nonexistent.md")])
    assert rc == 1


def test_cli_json_output_structure(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """CLI: stdout 이 유효한 JSON + 필수 키 포함."""
    output_file = tmp_path / "output.txt"
    output_file.write_text(
        "FAILED tests/models/test_user.py::test_dup\nsrc/services/auth.py:10 — Type error\n",
        encoding="utf-8",
    )
    tasks_file = tmp_path / "tasks.md"
    tasks_file.write_text(_TASKS_MD_SAMPLE, encoding="utf-8")

    rc = analyzer_main([str(output_file), "--tasks", str(tasks_file)])
    assert rc == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "failures" in data
    assert "matches" in data
    assert "unmatched_failures" in data
    assert isinstance(data["failures"], list)
    assert isinstance(data["matches"], list)
    assert isinstance(data["unmatched_failures"], list)
