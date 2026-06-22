"""Tests for converge.py — code↔spec convergence (Track A4, TDD).

Design doc: backend/docs/spec-kit-absorption-design.md §4 A4
"""

from __future__ import annotations

import re

import pytest

from src.orchestrator.converge import (
    ConvergeFinding,
    allocate_task_ids,
    append_tasks,
    filter_uncovered,
    find_missing_endpoints,
)

_SKELETON = """\
## 1. 개요

intro

## 8. HTTP API

- **`GET /api/users`** — list users
- **`POST /api/users`** — create user
- **`GET /api/orders/{id}`** — get one order

## 9. 영속성

db
"""

_TASKS = """\
## 12. 태스크 분해

### 태스크 목록 (Phase 테이블 — 파서 고정 5컬럼, 순서 변경 금지)
| ID | 에이전트 | 의존성 | 설명 | 상태 |
|---|---|---|---|---|
| T-001 | backend_coder | - | users API | done |
| T-002 | backend_coder | T-001 | 인증 | 대기 |

### 진행 상태
- `대기` — 아직 시작 안 함
"""

_TASK_ROW_RE = re.compile(r"^\|\s*(T-\d+)\s*\|", re.MULTILINE)


# ---------------------------------------------------------------------------
# find_missing_endpoints
# ---------------------------------------------------------------------------


class TestFindMissingEndpoints:
    def test_declared_but_absent_is_reported(self) -> None:
        # source implements only /api/users
        src = ['@router.get("/api/users")\n@router.post("/api/users")\n']
        findings = find_missing_endpoints(_SKELETON, src)
        ids = {f.identifier for f in findings}
        assert ids == {"GET /api/orders/{id}"}

    def test_all_present_is_empty(self) -> None:
        src = ["/api/users /api/orders here are all prefixes"]
        assert find_missing_endpoints(_SKELETON, src) == []

    def test_no_http_section_returns_empty(self) -> None:
        skel = "## 1. 개요\n\nno endpoints here\n"
        assert find_missing_endpoints(skel, ["whatever"]) == []

    def test_finding_kind_and_detail(self) -> None:
        findings = find_missing_endpoints(_SKELETON, ["nothing matches"])
        assert findings  # all three missing
        for f in findings:
            assert f.kind == "missing_endpoint"
            assert isinstance(f, ConvergeFinding)
        # static prefix strips the {param} tail
        order = next(f for f in findings if "orders" in f.identifier)
        assert order.detail == "/api/orders"

    def test_param_prefix_match_avoids_false_positive(self) -> None:
        # router prefix + param route: only the static prefix needs to appear
        src = ['router = APIRouter(prefix="/api/orders")\n@router.get("/{id}")\n']
        findings = find_missing_endpoints(_SKELETON, src + ['"/api/users"'])
        assert findings == []  # all static prefixes present


# ---------------------------------------------------------------------------
# allocate_task_ids
# ---------------------------------------------------------------------------


class TestAllocateTaskIds:
    def test_sequential_after_max(self) -> None:
        assert allocate_task_ids(_TASKS, 2) == ["T-003", "T-004"]

    def test_empty_tasks_starts_at_one(self) -> None:
        assert allocate_task_ids("no task rows here", 1) == ["T-001"]

    def test_handles_gaps_uses_max(self) -> None:
        text = "| T-001 | a | - | x | done |\n| T-005 | a | - | y | 대기 |\n"
        assert allocate_task_ids(text, 1) == ["T-006"]

    def test_zero_padded_width_three(self) -> None:
        assert allocate_task_ids("", 1) == ["T-001"]


# ---------------------------------------------------------------------------
# filter_uncovered
# ---------------------------------------------------------------------------


class TestFilterUncovered:
    def test_identifier_already_in_tasks_is_filtered(self) -> None:
        findings = [
            ConvergeFinding("missing_endpoint", "GET /api/orders/{id}", "/api/orders"),
        ]
        tasks = _TASKS + "| T-003 | backend_coder | - | impl GET /api/orders/{id} | 대기 |\n"
        assert filter_uncovered(findings, tasks) == []

    def test_uncovered_passes_through(self) -> None:
        findings = [
            ConvergeFinding("missing_endpoint", "GET /api/orders/{id}", "/api/orders"),
        ]
        assert filter_uncovered(findings, _TASKS) == findings


# ---------------------------------------------------------------------------
# append_tasks
# ---------------------------------------------------------------------------


class TestAppendTasks:
    _FINDINGS = [
        ConvergeFinding("missing_endpoint", "GET /api/orders/{id}", "/api/orders"),
        ConvergeFinding("missing_endpoint", "DELETE /api/users", "/api/users"),
    ]

    def test_appends_rows_with_new_ids(self) -> None:
        new_text, added = append_tasks(_TASKS, self._FINDINGS)
        assert [tid for tid, _ in added] == ["T-003", "T-004"]
        ids = _TASK_ROW_RE.findall(new_text)
        assert ids == ["T-001", "T-002", "T-003", "T-004"]

    def test_new_rows_are_valid_five_columns(self) -> None:
        new_text, _ = append_tasks(_TASKS, self._FINDINGS)
        row = next(ln for ln in new_text.splitlines() if "T-003" in ln)
        # 5 columns → 6 pipes
        assert row.count("|") == 6
        assert row.strip().endswith("대기 |")
        assert "GET /api/orders/{id}" in row

    def test_idempotent_second_run_adds_nothing(self) -> None:
        new_text, added1 = append_tasks(_TASKS, self._FINDINGS)
        assert added1
        new_text2, added2 = append_tasks(new_text, self._FINDINGS)
        assert added2 == []
        assert new_text2 == new_text

    def test_empty_findings_is_noop(self) -> None:
        new_text, added = append_tasks(_TASKS, [])
        assert added == []
        assert new_text == _TASKS

    def test_inserts_after_last_task_row_not_in_legend(self) -> None:
        new_text, _ = append_tasks(_TASKS, self._FINDINGS[:1])
        lines = new_text.splitlines()
        t002 = next(i for i, ln in enumerate(lines) if ln.startswith("| T-002"))
        t003 = next(i for i, ln in enumerate(lines) if ln.startswith("| T-003"))
        legend = next(i for i, ln in enumerate(lines) if "진행 상태" in ln)
        assert t002 < t003 < legend  # new row before the legend section

    def test_no_task_table_raises(self) -> None:
        with pytest.raises(ValueError, match="task"):
            append_tasks("## tasks\n\nno rows at all\n", self._FINDINGS)
