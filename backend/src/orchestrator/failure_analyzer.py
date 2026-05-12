"""failure_analyzer — 빌드/테스트 출력에서 실패 파일 추출 + tasks.md 태스크 매핑.

/ha-verify 단계 2.5 자동화: 수동 grep 대신 `harness analyze-failure` 로
실패 항목 → T-ID 매핑을 기계적으로 수행.

지원 포맷:
  pytest : FAILED tests/api/test_auth.py::test_login
  pyright: src/services/auth.py:42 — ...  (또는 :42:5)
  eslint : src/foo.tsx:42:5  error  ...
  jest   : FAIL src/foo.test.tsx  /  at ... (src/foo.tsx:42:1)
  tsc    : src/foo.tsx(42,5): error TS...

설계 원칙:
- 경로 정규화: Windows 백슬래시 → 슬래시, 상대 경로 유지
- 중복 제거: 같은 파일은 한 번만
- 매칭: tasks.md 행 + 그 스펙 블록 안 파일명 substring 검색
- 결과: JSON stdout (failures / matches / unmatched_failures)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# ── 파일 경로 추출 정규식 ──────────────────────────────────────────────────────

# pytest: "FAILED tests/api/test_auth.py::test_login_missing_fields"
_PYTEST_RE = re.compile(r"^FAILED\s+([^\s:]+)", re.MULTILINE)

# pyright 출력: "src/services/auth.py:42:5 — ..." 또는 ":42 — ..."
# Windows 경로 "C:\path\file.py:42" 도 커버
_PYRIGHT_RE = re.compile(r"^([^\s:][^\s]*\.py):\d+", re.MULTILINE)

# eslint: "  /abs/path/foo.tsx" 줄 OR "src/foo.tsx:42:5  error"
_ESLINT_LINE_RE = re.compile(r"^([^\s][^\s]*\.[jt]sx?):\d+:\d+\s+(?:error|warning)", re.MULTILINE)

# jest: "FAIL src/foo.test.tsx"
_JEST_FAIL_RE = re.compile(r"^FAIL\s+([^\s]+)", re.MULTILINE)

# jest stack: "at Object.<anonymous> (src/foo.tsx:42:1)"
_JEST_STACK_RE = re.compile(r"\(([^)\s:][^)\s]*\.[jt]sx?):\d+:\d+\)", re.MULTILINE)

# tsc: "src/foo.tsx(42,5): error TS..." 또는 Windows "C:\path\foo.tsx(42,5):"
_TSC_RE = re.compile(r"^([^\s(][^\s(]*\.[jt]sx?)\(\d+,\d+\):\s+error", re.MULTILINE)


def _normalize_path(raw: str) -> str:
    """Windows 백슬래시 → 슬래시, 드라이브 문자 정규화."""
    return raw.replace("\\", "/").strip()


def extract_failed_files(output: str) -> list[str]:
    """빌드/테스트 출력 텍스트에서 실패 파일 경로를 추출해 중복 없이 반환.

    지원: pytest, pyright, eslint, jest, tsc.
    경로는 상대 경로 또는 절대 경로 그대로 반환 (정규화만).
    """
    found: dict[str, None] = {}  # 삽입 순서 보존 중복 제거

    for pattern in (_PYTEST_RE, _PYRIGHT_RE, _ESLINT_LINE_RE, _JEST_FAIL_RE, _JEST_STACK_RE, _TSC_RE):
        for m in pattern.finditer(output):
            normalized = _normalize_path(m.group(1))
            if normalized and normalized not in found:
                found[normalized] = None

    return list(found.keys())


# ── tasks.md 파싱 + 매칭 ──────────────────────────────────────────────────────

# tasks.md 행: | T-001 | agent | depends | description | status |
_TASK_ROW_RE = re.compile(
    r"^\|\s*(T-\d+)\s*\|",
    re.MULTILINE,
)


def _extract_spec_blocks(tasks_text: str) -> dict[str, str]:
    """tasks.md 에서 각 T-NNN 의 스펙 블록 텍스트를 추출.

    스펙 블록 = 해당 T-NNN 행 + 다음 T-NNN 행 시작 전까지의 텍스트.
    """
    blocks: dict[str, str] = {}
    positions = [(m.group(1), m.start()) for m in _TASK_ROW_RE.finditer(tasks_text)]
    for i, (tid, start) in enumerate(positions):
        end = positions[i + 1][1] if i + 1 < len(positions) else len(tasks_text)
        blocks[tid] = tasks_text[start:end]
    return blocks


def match_failures_to_tasks(
    failed_files: list[str],
    tasks_text: str,
) -> tuple[list[dict[str, object]], list[str]]:
    """실패 파일 목록을 tasks.md 스펙 블록에서 검색해 T-ID 매핑.

    반환:
        matches: [{"task_id": "T-003", "files": [...matched files...]}, ...]
        unmatched_failures: 어떤 T-ID 에도 매핑 안 된 파일 목록
    """
    spec_blocks = _extract_spec_blocks(tasks_text)

    # 파일명(basename) + 경로 조각 둘 다로 매칭
    matches: list[dict[str, object]] = []
    matched_files: set[str] = set()

    for tid, block in spec_blocks.items():
        task_matched: list[str] = []
        for fpath in failed_files:
            basename = Path(fpath).name
            # 경로 substring 매칭 (슬래시 정규화 후)
            block_normalized = block.replace("\\", "/")
            if basename in block_normalized or fpath in block_normalized:
                task_matched.append(fpath)
                matched_files.add(fpath)
        if task_matched:
            matches.append({"task_id": tid, "files": task_matched})

    unmatched = [f for f in failed_files if f not in matched_files]
    return matches, unmatched


def analyze_failure(output: str, tasks_text: str) -> dict[str, object]:
    """output 텍스트 + tasks.md 텍스트 → JSON 결과 dict.

    결과 구조:
    {
      "failures": [...],
      "matches": [{"task_id": "T-003", "files": [...]}, ...],
      "unmatched_failures": [...]
    }
    """
    failed_files = extract_failed_files(output)
    matches, unmatched = match_failures_to_tasks(failed_files, tasks_text)
    return {
        "failures": failed_files,
        "matches": matches,
        "unmatched_failures": unmatched,
    }


# ── CLI entry (harness analyze-failure 에서 subprocess 호출) ─────────────────


def main(argv: list[str] | None = None) -> int:
    """CLI entry: analyze-failure <output-file> --tasks <tasks.md>.

    사용법:
      python -m src.orchestrator.failure_analyzer <output-file> [--tasks <path>]
      python -m src.orchestrator.failure_analyzer - [--tasks <path>]  # stdin

    종료 코드:
      0: 정상 (실패 0개 포함)
      1: I/O 오류
      2: 사용 오류
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="harness analyze-failure",
        description="빌드/테스트 출력에서 실패 파일 추출 + tasks.md 태스크 매핑",
    )
    parser.add_argument(
        "output_file",
        help="분석할 출력 파일 경로 (- 면 stdin)",
    )
    parser.add_argument(
        "--tasks",
        default="docs/tasks.md",
        help="tasks.md 경로 (기본: <cwd>/docs/tasks.md)",
    )

    args = parser.parse_args(argv)

    # output 읽기
    if args.output_file == "-":
        try:
            output_text = sys.stdin.read()
        except OSError as exc:
            print(f"[FAIL] stdin 읽기 실패: {exc}", file=sys.stderr)
            return 1
    else:
        output_path = Path(args.output_file)
        if not output_path.exists():
            print(f"[FAIL] output 파일 없음: {output_path}", file=sys.stderr)
            return 1
        try:
            output_text = output_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"[FAIL] output 파일 읽기 실패: {exc}", file=sys.stderr)
            return 1

    # tasks.md 읽기
    tasks_path = Path(args.tasks)
    if not tasks_path.exists():
        print(f"[FAIL] tasks.md 없음: {tasks_path}", file=sys.stderr)
        return 1
    try:
        tasks_text = tasks_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"[FAIL] tasks.md 읽기 실패: {exc}", file=sys.stderr)
        return 1

    result = analyze_failure(output_text, tasks_text)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
