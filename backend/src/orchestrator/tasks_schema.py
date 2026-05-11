"""tasks.md schema validation and dependency graph extraction.

Enforces standard format for task tables produced by /ha-plan:
- Task ID: T-NNN (exactly 3 decimal digits) — no fractional IDs (T-024.5)
- Column order: ID | agent | depends | description | status (5 columns, fixed order)
- Status: one of VALID_STATUSES allow-list
- Phase headers (optional): ### Phase N[+] — <name>  or  ### Phase N[+]
- Dependencies: one of _DEPS_NONE_TOKENS for none, or comma-separated T-NNN IDs

Graph extraction (extract_task_graph / render_mermaid):
- Best-effort: invalid task IDs are silently skipped (unlike validate_tasks_md)
- Phase labels tracked per node for subgraph grouping in mermaid output
- render_mermaid produces GitHub-flavored mermaid flowchart (TD direction)

Design notes:
- _TASK_ID_VALID_RE is the *strict* validator (3 decimal digits only).
  ha-plan/run.py's _TASK_ID_CANDIDATE_RE is intentionally *lenient* for extraction
  so that malformed IDs are surfaced here rather than silently skipped.
- validate_tasks_md() is pure (no I/O) and returns a sorted list of violations.
- extract_task_graph() is pure (no I/O) and returns a TaskGraph dataclass.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Strict: exactly T-NNN where N is a decimal digit.
# Rejects: T-024.5, T-A01, T-1, T-10000, T-024_5
_TASK_ID_VALID_RE = re.compile(r"^T-\d{3}$")

# Phase header pattern — ### Phase N[+] optionally followed by " — <name>"
# Accepts: "### Phase 1 — MVP", "### Phase 2+ — 확장", "### Phase 10"
# Rejects: "## Phase 1" (wrong level), "### 1단계", "### phase 1" (lowercase)
_PHASE_HEADER_RE = re.compile(r"^### Phase \d+\+?( — .+)?$")

# Tokens that mean "no dependency" in the depends column (case-sensitive).
# Empty string covers cells with only whitespace (stripped to "").
_DEPS_NONE_TOKENS: frozenset[str] = frozenset({"-", "—", "(없음)", "none", "없음", ""})

# Column header aliases — each position in the 5-column table has a set of
# accepted header names.  All comparisons are case-sensitive.
_COL_ALIASES: tuple[frozenset[str], ...] = (
    frozenset({"ID", "id"}),                                            # col 0
    frozenset({"에이전트", "agent", "Agent"}),                           # col 1
    frozenset({"의존성", "depends", "Depends", "Dependency"}),           # col 2
    frozenset({"설명", "description", "Description", "desc", "Desc"}),  # col 3
    frozenset({"상태", "status", "Status"}),                             # col 4
)

# Human-readable labels for each column position (used in violation messages).
_COL_LABELS: tuple[str, ...] = (
    "ID (col 1)",
    "에이전트/agent (col 2)",
    "의존성/depends (col 3)",
    "설명/description (col 4)",
    "상태/status (col 5)",
)

# Valid status values — mirrors plan_manager task status policy and
# TASK_STATUS_NEEDS_REBUILD introduced in Group 3.
VALID_STATUSES: frozenset[str] = frozenset({
    "대기",
    "pending",
    "진행중",
    "in-progress",
    "완료",
    "done",
    "completed",
    "차단",
    "blocked",
    "needs_rebuild",
})


@dataclass(frozen=True)
class SchemaViolation:
    """A single tasks.md schema violation."""

    line_number: int
    kind: str  # "invalid_task_id" | "bad_column_order" | "invalid_status" | "bad_phase_header" | "bad_dependency"
    detail: str  # human-readable Korean explanation


def _is_separator_row(stripped: str) -> bool:
    """Return True for Markdown table separator rows like |---|---|...|."""
    # Must start with | and contain at least one '---' segment.
    if not stripped.startswith("|"):
        return False
    inner = stripped.strip("|")
    return all(
        cell.strip().replace("-", "").replace(":", "") == ""
        for cell in inner.split("|")
        if cell.strip()
    )


def _split_table_row(line: str) -> list[str] | None:
    """Split a Markdown table row into stripped cell strings.

    Returns None if the line is not a valid table row (no pipe chars).
    """
    stripped = line.strip()
    if "|" not in stripped:
        return None
    return [c.strip() for c in stripped.strip("|").split("|")]


def validate_tasks_md(content: str) -> list[SchemaViolation]:
    """Validate *content* of a tasks.md file against the standard schema.

    Returns a sorted list of violations (by line_number, then kind).
    An empty list means the content is fully compliant.

    The function is pure (no filesystem access).
    """
    violations: list[SchemaViolation] = []
    lines = content.splitlines()

    # State machine: track whether we are inside a table that has a validated
    # header row.  A non-pipe line after entering table mode exits it.
    in_table = False

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()

        # ── Phase header check ──────────────────────────────────────────────
        # Any line starting with "### Phase" or "## Phase" is treated as a
        # phase header candidate; validate its exact format.
        if stripped.startswith("### Phase") or stripped.startswith("## Phase"):
            if not _PHASE_HEADER_RE.match(stripped):
                violations.append(SchemaViolation(
                    line_number=idx,
                    kind="bad_phase_header",
                    detail=(
                        f"Phase 헤더 형식 위반 — `### Phase N[+] — <name>` 필요 "
                        f"(예: `### Phase 1 — MVP`). 실제: {stripped!r}"
                    ),
                ))
            # Phase headers reset table state: a new table section may follow.
            in_table = False
            continue

        # ── Separator row — skip, but stay in table mode ────────────────────
        if in_table and _is_separator_row(stripped):
            continue

        # ── Table rows (header or data) ─────────────────────────────────────
        if "|" in line:
            cells = _split_table_row(line)
            if cells is None or len(cells) != 5:
                # Wrong column count — exit table mode if we were in it.
                if in_table:
                    in_table = False
                continue

            if not in_table:
                # Potential header row — check column names.
                if all(cells[i] in _COL_ALIASES[i] for i in range(5)):
                    # Valid header: enter table mode.
                    in_table = True
                    continue
                # Has 5 cells but column names are wrong.
                # Check if this looks like a mismatched header (any cell
                # matches a known alias at the *wrong* position, or is an
                # unknown name for a column we recognise).
                for i in range(5):
                    # Report the first column that doesn't match its position.
                    if cells[i] not in _COL_ALIASES[i]:
                        # Only surface as a violation when the row actually
                        # looks like a header (contains at least one known alias
                        # at some position).
                        all_known = any(
                            cells[j] in _COL_ALIASES[j] for j in range(5)
                        )
                        if all_known:
                            violations.append(SchemaViolation(
                                line_number=idx,
                                kind="bad_column_order",
                                detail=(
                                    f"컬럼 헤더 순서/이름 위반 — "
                                    f"{_COL_LABELS[i]} 위치에 {cells[i]!r} "
                                    f"(허용: {sorted(_COL_ALIASES[i])})"
                                ),
                            ))
                        break
                continue

            # ── Data row (in_table=True, 5 cells) ──────────────────────────
            task_id, _agent, depends, _desc, status = cells

            # Task ID validation
            if task_id and not _TASK_ID_VALID_RE.match(task_id):
                violations.append(SchemaViolation(
                    line_number=idx,
                    kind="invalid_task_id",
                    detail=(
                        f"Task ID 형식 위반 — `T-NNN` (3자리 정수) 필요. "
                        f"실제: {task_id!r}"
                    ),
                ))

            # Status validation (skip empty cells gracefully)
            if status and status not in VALID_STATUSES:
                violations.append(SchemaViolation(
                    line_number=idx,
                    kind="invalid_status",
                    detail=(
                        f"상태 값 위반 — 허용: {sorted(VALID_STATUSES)}. "
                        f"실제: {status!r}"
                    ),
                ))

            # Dependency validation
            if depends not in _DEPS_NONE_TOKENS:
                dep_parts = [d.strip() for d in depends.split(",")]
                for dep in dep_parts:
                    if dep and not _TASK_ID_VALID_RE.match(dep):
                        violations.append(SchemaViolation(
                            line_number=idx,
                            kind="bad_dependency",
                            detail=(
                                f"의존성 항목 형식 위반 — `T-NNN` 만 허용. "
                                f"실제: {dep!r} (전체: {depends!r})"
                            ),
                        ))
                        break  # report once per row

            continue

        # ── Non-pipe line — exit table mode ─────────────────────────────────
        if in_table:
            in_table = False

    return sorted(violations, key=lambda v: (v.line_number, v.kind))


# ── Dependency graph extraction ───────────────────────────────────────────────


@dataclass(frozen=True)
class TaskNode:
    """One node in the task dependency graph."""

    task_id: str
    agent: str
    depends_on: tuple[str, ...]  # parsed valid T-NNN IDs from dependency column
    phase: str | None  # nearest preceding "### Phase N..." header label, or None


@dataclass(frozen=True)
class TaskGraph:
    """Parsed task dependency graph (ordered as encountered in tasks.md)."""

    nodes: tuple[TaskNode, ...]


def extract_task_graph(content: str) -> TaskGraph:
    """Parse tasks.md content into a TaskNode dependency graph.

    Best-effort extraction: invalid task IDs (non-T-NNN) are silently skipped.
    Caller is expected to run validate_tasks_md() separately for strict checking.

    Phase labels are tracked so each node knows which Phase section it belongs to.
    A node appearing before any "### Phase N" header has phase=None.

    The function is pure (no filesystem access).
    """
    nodes: list[TaskNode] = []
    lines = content.splitlines()
    current_phase: str | None = None
    in_table = False

    for line in lines:
        stripped = line.strip()

        # Track phase headers — same pattern as validate_tasks_md
        if stripped.startswith("### Phase") or stripped.startswith("## Phase"):
            # Extract label: strip leading "### " or "## "
            label = stripped.lstrip("#").strip()
            current_phase = label
            in_table = False
            continue

        # Skip separator rows
        if in_table and _is_separator_row(stripped):
            continue

        if "|" in line:
            cells = _split_table_row(line)
            if cells is None or len(cells) != 5:
                if in_table:
                    in_table = False
                continue

            if not in_table:
                # Check for valid header row to enter table mode
                if all(cells[i] in _COL_ALIASES[i] for i in range(5)):
                    in_table = True
                continue

            # Data row inside a valid table
            task_id, agent, depends, _desc, _status = cells

            # Skip rows with invalid task IDs (best-effort)
            if not task_id or not _TASK_ID_VALID_RE.match(task_id):
                continue

            # Parse dependency column
            if depends in _DEPS_NONE_TOKENS:
                dep_tuple: tuple[str, ...] = ()
            else:
                dep_parts = [d.strip() for d in depends.split(",")]
                dep_tuple = tuple(
                    d for d in dep_parts
                    if d and _TASK_ID_VALID_RE.match(d)
                )

            nodes.append(TaskNode(
                task_id=task_id,
                agent=agent,
                depends_on=dep_tuple,
                phase=current_phase,
            ))
            continue

        # Non-pipe line exits table mode
        if in_table:
            in_table = False

    return TaskGraph(nodes=tuple(nodes))


def render_mermaid(graph: TaskGraph, *, group_by_phase: bool = True) -> str:
    """Render a TaskGraph as a mermaid flowchart (TD direction).

    Output format (group_by_phase=True):
        flowchart TD
            subgraph "Phase 1 — MVP"
                T-001
                T-002
            end
            T-001 --> T-002

    group_by_phase=False produces a flat node list without subgraph blocks.
    Edges are rendered as: <prereq> --> <dependent>.
    Empty graph returns:  flowchart TD\\n    %% no tasks
    No trailing newline.
    """
    if not graph.nodes:
        return "flowchart TD\n    %% no tasks"

    lines: list[str] = ["flowchart TD"]

    if group_by_phase:
        # Collect nodes per phase, preserving encounter order
        # Use dict to maintain phase insertion order
        phase_nodes: dict[str | None, list[str]] = {}
        for node in graph.nodes:
            phase_nodes.setdefault(node.phase, []).append(node.task_id)

        for phase, task_ids in phase_nodes.items():
            if phase is not None:
                lines.append(f'    subgraph "{phase}"')
                for tid in task_ids:
                    lines.append(f"        {tid}")
                lines.append("    end")
            else:
                # Nodes without a phase label — render flat (no subgraph)
                for tid in task_ids:
                    lines.append(f"    {tid}")
    else:
        # Flat: list all nodes without subgraph grouping
        for node in graph.nodes:
            lines.append(f"    {node.task_id}")

    # Edges: for each node, draw prereq --> node for each dependency
    for node in graph.nodes:
        for dep in node.depends_on:
            lines.append(f"    {dep} --> {node.task_id}")

    return "\n".join(lines)
