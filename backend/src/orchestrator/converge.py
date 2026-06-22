"""Code↔spec convergence — Track A4 (Spec Kit /converge absorption).

Detects components declared in skeleton.md but absent from the source tree, and
renders them as new tasks.md rows so the gap becomes *actionable* rather than
advisory (ha-review only reports the same signal as a WARN).

Pure functions — detection takes pre-read source texts, append takes tasks.md
text — so the logic is fully testable without a filesystem.

Design doc: backend/docs/spec-kit-absorption-design.md §4 A4
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.orchestrator.context import extract_section_by_id

# skeleton interface.http 표기: **`GET /api/users`** (ha-review 와 동일 패턴)
_HTTP_METHOD_PATH_RE = re.compile(r"`(GET|POST|PUT|PATCH|DELETE)\s+(/[^\s`]+)`")

# tasks.md Phase 테이블의 태스크 행 (5컬럼 고정): | T-NNN | ...
_TASK_ROW_RE = re.compile(r"^\|\s*(T-\d+)\s*\|", re.MULTILINE)
_TASK_ROW_LINE_RE = re.compile(r"^\|\s*(T-\d+)\s*\|")

# 회수 태스크 기본값 — HTTP 엔드포인트 구현은 backend 담당.
_CONVERGE_AGENT = "backend_coder"
_DESC_TEMPLATE = "선언-미구현 엔드포인트 구현: {identifier}"


@dataclass(frozen=True)
class ConvergeFinding:
    """A component declared in the skeleton but missing from the source tree."""

    kind: str          # "missing_endpoint"
    identifier: str    # 사람이 읽는 식별자, e.g. "GET /api/users"
    detail: str        # 매칭에 쓴 정적 prefix, e.g. "/api/users"


def find_missing_endpoints(
    skeleton_text: str, source_texts: list[str]
) -> list[ConvergeFinding]:
    """skeleton interface.http 에 선언됐지만 소스 어디에도 없는 엔드포인트.

    path 의 정적 prefix ("{param}" 앞부분) 가 소스 전체에서 한 번도 안 보이면 보고.
    router prefix 조합 (`APIRouter(prefix=...)` + `@router.get("/{id}")`) 으로 인한
    false positive 를 보수적으로 회피한다 (ha-review 역방향 contract 와 동일 규칙).
    """
    section = extract_section_by_id(skeleton_text, "interface.http")
    if not section:
        return []
    declared = sorted(
        {(m.group(1), m.group(2)) for m in _HTTP_METHOD_PATH_RE.finditer(section)}
    )
    findings: list[ConvergeFinding] = []
    for method, path_str in declared:
        prefix = path_str.split("{")[0].rstrip("/") or path_str
        if not any(prefix in h for h in source_texts):
            findings.append(
                ConvergeFinding(
                    kind="missing_endpoint",
                    identifier=f"{method} {path_str}",
                    detail=prefix,
                )
            )
    return findings


def allocate_task_ids(tasks_text: str, count: int) -> list[str]:
    """tasks.md 의 최대 T-NNN 다음부터 count 개의 새 ID (zero-padded 3자리)."""
    ids = [int(m.group(1).split("-")[1]) for m in _TASK_ROW_RE.finditer(tasks_text)]
    start = (max(ids) + 1) if ids else 1
    return [f"T-{n:03d}" for n in range(start, start + count)]


def filter_uncovered(
    findings: list[ConvergeFinding], tasks_text: str
) -> list[ConvergeFinding]:
    """이미 태스크로 존재하는 finding 제거 (멱등성).

    회수 태스크 설명에 identifier 를 그대로 박으므로, identifier 가 tasks.md 에
    이미 등장하면 (수동 태스크든 이전 회수든) 중복 추가하지 않는다.
    """
    return [f for f in findings if f.identifier not in tasks_text]


def _render_task_row(task_id: str, description: str) -> str:
    return f"| {task_id} | {_CONVERGE_AGENT} | - | {description} | 대기 |"


def append_tasks(
    tasks_text: str, findings: list[ConvergeFinding]
) -> tuple[str, list[tuple[str, str]]]:
    """미회수 finding 을 tasks.md 의 Phase 테이블 마지막 태스크 행 뒤에 append.

    Returns:
        (new_tasks_text, [(task_id, identifier), ...]) — 추가된 태스크 목록.
        추가할 게 없으면 (tasks_text, []) 를 그대로 반환 (no-op).

    Raises:
        ValueError — tasks.md 에 태스크 행이 하나도 없을 때 (삽입 위치 불명;
        /ha-plan 이 선행돼야 함).
    """
    uncovered = filter_uncovered(findings, tasks_text)
    if not uncovered:
        return tasks_text, []

    new_ids = allocate_task_ids(tasks_text, len(uncovered))
    added: list[tuple[str, str]] = []
    new_rows: list[str] = []
    for tid, finding in zip(new_ids, uncovered, strict=True):
        desc = _DESC_TEMPLATE.format(identifier=finding.identifier)
        new_rows.append(_render_task_row(tid, desc))
        added.append((tid, finding.identifier))

    lines = tasks_text.split("\n")
    last_row_idx = -1
    for i, line in enumerate(lines):
        if _TASK_ROW_LINE_RE.match(line):
            last_row_idx = i
    if last_row_idx == -1:
        raise ValueError(
            "tasks.md 에 태스크 행(| T-NNN |)이 없음 — /ha-plan 을 먼저 실행하세요."
        )

    lines[last_row_idx + 1 : last_row_idx + 1] = new_rows
    return "\n".join(lines), added
