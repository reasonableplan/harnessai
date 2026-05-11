"""tasks.md dependency graph extraction + mermaid rendering 유닛 테스트 (Group 4 Step 3).

extract_task_graph() / render_mermaid() 의 동작을 커버.
pure function 테스트이므로 fixture 없이 문자열 직접 전달.
"""
from __future__ import annotations

import pytest

from src.orchestrator.tasks_schema import (
    TaskGraph,
    TaskNode,
    extract_task_graph,
    render_mermaid,
)

# ── helpers ───────────────────────────────────────────────────────────────────

_VALID_HEADER = "| ID | 에이전트 | 의존성 | 설명 | 상태 |\n|----|---------|--------|------|------|\n"


def _row(
    task_id: str = "T-001",
    agent: str = "mobile_coder_rn",
    depends: str = "-",
    desc: str = "설명",
    status: str = "대기",
) -> str:
    return f"| {task_id} | {agent} | {depends} | {desc} | {status} |\n"


def _table(*rows: str, header: str = _VALID_HEADER, phase: str | None = None) -> str:
    prefix = f"{phase}\n" if phase else ""
    return prefix + header + "".join(rows)


# ── Test 1: 단순 선형 그래프 ─────────────────────────────────────────────────


def test_extract_simple_linear_graph() -> None:
    """T-001 → T-002 → T-003 선형 의존성 — 3 nodes, depends_on 정확."""
    content = (
        _VALID_HEADER
        + _row("T-001", depends="-")
        + _row("T-002", depends="T-001")
        + _row("T-003", depends="T-002")
    )
    graph = extract_task_graph(content)
    assert len(graph.nodes) == 3

    ids = [n.task_id for n in graph.nodes]
    assert ids == ["T-001", "T-002", "T-003"]

    assert graph.nodes[0].depends_on == ()
    assert graph.nodes[1].depends_on == ("T-001",)
    assert graph.nodes[2].depends_on == ("T-002",)


# ── Test 2: 병렬 분기 그래프 ─────────────────────────────────────────────────


def test_extract_parallel_graph() -> None:
    """T-001 → T-002, T-001 → T-003 분기 — T-002/T-003 모두 depends=[T-001]."""
    content = (
        _VALID_HEADER
        + _row("T-001", depends="-")
        + _row("T-002", depends="T-001")
        + _row("T-003", depends="T-001")
    )
    graph = extract_task_graph(content)
    assert len(graph.nodes) == 3

    t002 = next(n for n in graph.nodes if n.task_id == "T-002")
    t003 = next(n for n in graph.nodes if n.task_id == "T-003")
    assert t002.depends_on == ("T-001",)
    assert t003.depends_on == ("T-001",)


# ── Test 3: 의존성 없음 — 대시 / 텍스트 토큰 ─────────────────────────────────


@pytest.mark.parametrize("dep_token", ["-", "—", "(없음)", "none", "없음", ""])
def test_extract_no_deps_uses_dash(dep_token: str) -> None:
    """의존성 컬럼이 none 토큰 → depends_on=()."""
    content = _VALID_HEADER + _row("T-001", depends=dep_token)
    graph = extract_task_graph(content)
    assert len(graph.nodes) == 1
    assert graph.nodes[0].depends_on == ()


# ── Test 4: 콤마 구분 다중 의존성 ───────────────────────────────────────────


def test_extract_multiple_deps_comma_separated() -> None:
    """'T-001, T-002' → depends_on=('T-001', 'T-002')."""
    content = _VALID_HEADER + _row("T-003", depends="T-001, T-002")
    graph = extract_task_graph(content)
    assert len(graph.nodes) == 1
    assert graph.nodes[0].depends_on == ("T-001", "T-002")


# ── Test 5: Phase 헤더 추적 ──────────────────────────────────────────────────


def test_extract_phase_tracking() -> None:
    """Phase 헤더별 node.phase 정확히 설정."""
    content = (
        "### Phase 1 — MVP\n"
        + _VALID_HEADER
        + _row("T-001", depends="-")
        + _row("T-002", depends="T-001")
        + "\n### Phase 2+ — 확장\n"
        + _VALID_HEADER
        + _row("T-101", depends="-")
    )
    graph = extract_task_graph(content)
    assert len(graph.nodes) == 3

    t001 = next(n for n in graph.nodes if n.task_id == "T-001")
    t002 = next(n for n in graph.nodes if n.task_id == "T-002")
    t101 = next(n for n in graph.nodes if n.task_id == "T-101")

    assert t001.phase == "Phase 1 — MVP"
    assert t002.phase == "Phase 1 — MVP"
    assert t101.phase == "Phase 2+ — 확장"


# ── Test 6: invalid task ID silent drop ──────────────────────────────────────


def test_extract_invalid_task_id_dropped() -> None:
    """T-024.5 (invalid) 는 nodes 에 포함되지 않음 — best-effort 추출."""
    content = (
        _VALID_HEADER
        + _row("T-001", depends="-")
        + _row("T-024.5", depends="T-001")  # invalid — should be skipped
    )
    graph = extract_task_graph(content)
    ids = [n.task_id for n in graph.nodes]
    assert ids == ["T-001"], f"T-024.5 가 nodes 에 포함됨: {ids}"


# ── Test 7: mermaid 기본 렌더 ─────────────────────────────────────────────────


def test_render_mermaid_basic() -> None:
    """2 nodes (T-001 → T-002) — 'flowchart TD' + 'T-001 --> T-002' 포함."""
    graph = TaskGraph(nodes=(
        TaskNode(task_id="T-001", agent="a", depends_on=(), phase=None),
        TaskNode(task_id="T-002", agent="a", depends_on=("T-001",), phase=None),
    ))
    result = render_mermaid(graph)
    assert result.startswith("flowchart TD")
    assert "T-001 --> T-002" in result


# ── Test 8: mermaid Phase subgraph 그룹화 ────────────────────────────────────


def test_render_mermaid_with_phase_subgraphs() -> None:
    """Phase 1 / Phase 2 nodes — 각 phase 별 subgraph 블록 포함."""
    graph = TaskGraph(nodes=(
        TaskNode(task_id="T-001", agent="a", depends_on=(), phase="Phase 1 — MVP"),
        TaskNode(task_id="T-002", agent="a", depends_on=("T-001",), phase="Phase 1 — MVP"),
        TaskNode(task_id="T-101", agent="a", depends_on=(), phase="Phase 2+ — 확장"),
    ))
    result = render_mermaid(graph, group_by_phase=True)
    assert 'subgraph "Phase 1 — MVP"' in result
    assert 'subgraph "Phase 2+ — 확장"' in result
    assert result.count("end") >= 2
    # T-001 이 Phase 1 subgraph 내부에 있어야 함
    p1_start = result.index('subgraph "Phase 1 — MVP"')
    p1_end = result.index("end", p1_start)
    p1_block = result[p1_start:p1_end]
    assert "T-001" in p1_block
    assert "T-002" in p1_block


# ── Test 9: mermaid flat (no phases) ─────────────────────────────────────────


def test_render_mermaid_no_phases_flat() -> None:
    """group_by_phase=False → subgraph 없음, flat node 목록."""
    graph = TaskGraph(nodes=(
        TaskNode(task_id="T-001", agent="a", depends_on=(), phase="Phase 1 — MVP"),
        TaskNode(task_id="T-002", agent="a", depends_on=("T-001",), phase="Phase 1 — MVP"),
    ))
    result = render_mermaid(graph, group_by_phase=False)
    assert "subgraph" not in result
    assert "T-001" in result
    assert "T-002" in result
    assert "T-001 --> T-002" in result


# ── Test 10: 빈 그래프 ───────────────────────────────────────────────────────


def test_render_mermaid_empty_graph() -> None:
    """빈 TaskGraph → 'flowchart TD\\n    %% no tasks'."""
    graph = TaskGraph(nodes=())
    result = render_mermaid(graph)
    assert result == "flowchart TD\n    %% no tasks"


# ── Test 11: 챙겼니 실제 tasks.md 일부 (e2e) ──────────────────────────────────


def test_render_mermaid_chaenggyeotni_sample() -> None:
    """챙겼니 tasks.md 의 T-001~T-005 로 graph 생성 — 파싱+렌더 성공, 모든 task 포함."""
    content = (
        "### Phase 1 — MVP\n"
        "| ID | 에이전트 | 의존성 | 설명 | 상태 |\n"
        "|---|---|---|---|---|\n"
        "| T-001 | mobile_coder_rn | - | 프로젝트 초기화 | done |\n"
        "| T-002 | mobile_coder_rn | T-001 | NativeWind + theme | 대기 |\n"
        "| T-003 | mobile_coder_rn | T-002 | shared/components | 대기 |\n"
        "| T-004 | mobile_coder_rn | T-001 | core/ 순수 로직 | 대기 |\n"
        "| T-005 | mobile_coder_rn | T-001 | Storage wrappers | 대기 |\n"
    )
    graph = extract_task_graph(content)
    assert len(graph.nodes) == 5

    ids = {n.task_id for n in graph.nodes}
    assert ids == {"T-001", "T-002", "T-003", "T-004", "T-005"}

    # T-003 depends on T-002, T-004 depends on T-001
    t003 = next(n for n in graph.nodes if n.task_id == "T-003")
    t004 = next(n for n in graph.nodes if n.task_id == "T-004")
    assert t003.depends_on == ("T-002",)
    assert t004.depends_on == ("T-001",)

    # mermaid 렌더 성공
    result = render_mermaid(graph)
    assert result.startswith("flowchart TD")
    assert "T-001" in result
    assert "T-002 --> T-003" in result
    assert "T-001 --> T-004" in result
