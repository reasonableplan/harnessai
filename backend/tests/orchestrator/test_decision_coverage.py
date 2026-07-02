"""Tests for decision_coverage — semantic decision-point coverage over skeleton.

Design: 설계 단계 의미 기반 인터뷰. Fragment frontmatter 의 decision_points 를
읽어, 채워진 skeleton 본문에 각 point 의 detect 키워드가 하나도 없으면 '미결정'
으로 판정 → clarify 후보로 반환. 어휘 스캔(skeleton_checklist)이 못 잡는 의미적
빈칸(다중 사용자/soft delete/동시성 등)을 taxonomy 기반으로 표면화한다.
"""

from __future__ import annotations

from pathlib import Path

from src.orchestrator.decision_coverage import (
    DecisionPoint,
    UnresolvedDecision,
    find_unresolved_decisions,
    load_decision_points,
)


def _write_fragment(dir_: Path, frag_id: str, name: str, body: str, dp_yaml: str = "") -> None:
    """Write a minimal fragment .md with optional decision_points frontmatter."""
    fm = f"---\nid: {frag_id}\nname: {name}\nrequired_when: scale.small_or_larger\n"
    if dp_yaml:
        fm += dp_yaml
    fm += "---\n"
    (dir_ / f"{frag_id}.md").write_text(fm + body, encoding="utf-8")


_PERSISTENCE_DP = """decision_points:
  - id: multi_tenant
    ask: "데이터를 사용자별로 격리하나요, 전체 공유인가요?"
    detect: [사용자별, 격리, user_id, tenant]
    hint: "격리면 소유 컬럼(user_id) 필요"
  - id: soft_delete
    ask: "삭제는 완전 삭제인가요, 복구 가능(soft delete)인가요?"
    detect: [soft, deleted_at, 복구, 영구 삭제]
    hint: "soft delete 면 deleted_at 컬럼"
"""


# ── load_decision_points ────────────────────────────────────────────────


def test_load_parses_decision_points(tmp_path: Path) -> None:
    _write_fragment(tmp_path, "persistence", "저장소 / 스키마", "본문", _PERSISTENCE_DP)
    dp = load_decision_points(tmp_path)
    assert "persistence" in dp
    pts = dp["persistence"]
    assert [p.point_id for p in pts] == ["multi_tenant", "soft_delete"]
    assert pts[0].detect == ("사용자별", "격리", "user_id", "tenant")
    assert isinstance(pts[0], DecisionPoint)
    assert pts[0].ask.startswith("데이터를")


def test_fragment_without_decision_points_absent(tmp_path: Path) -> None:
    _write_fragment(tmp_path, "overview", "개요", "본문")  # no dp_yaml
    dp = load_decision_points(tmp_path)
    assert "overview" not in dp


def test_malformed_frontmatter_skipped(tmp_path: Path) -> None:
    (tmp_path / "broken.md").write_text("no frontmatter here", encoding="utf-8")
    (tmp_path / "badyaml.md").write_text("---\nid: x\n: : :\n---\nbody", encoding="utf-8")
    dp = load_decision_points(tmp_path)
    assert dp == {}


def test_missing_dir_returns_empty(tmp_path: Path) -> None:
    assert load_decision_points(tmp_path / "nonexistent") == {}


def test_decision_point_missing_required_field_skipped(tmp_path: Path) -> None:
    """A point without id or ask is dropped; well-formed siblings survive."""
    dp_yaml = (
        "decision_points:\n"
        "  - id: good\n"
        '    ask: "질문?"\n'
        "    detect: [키워드]\n"
        "  - detect: [무id]\n"  # missing id + ask
    )
    _write_fragment(tmp_path, "persistence", "저장소 / 스키마", "본문", dp_yaml)
    dp = load_decision_points(tmp_path)
    assert [p.point_id for p in dp["persistence"]] == ["good"]


# ── find_unresolved_decisions ───────────────────────────────────────────


def _skeleton(persistence_body: str) -> str:
    return f"# Project Skeleton\n\n## 1. 개요\n설명\n\n## 2. 저장소 / 스키마\n{persistence_body}\n"


def test_unresolved_when_no_detect_keyword(tmp_path: Path) -> None:
    _write_fragment(tmp_path, "persistence", "저장소 / 스키마", "b", _PERSISTENCE_DP)
    skel = _skeleton("PostgreSQL 사용. tasks 테이블 id, title.")
    unresolved = find_unresolved_decisions(skel, tmp_path)
    ids = {(u.section_id, u.point_id) for u in unresolved}
    assert ("persistence", "multi_tenant") in ids
    assert ("persistence", "soft_delete") in ids


def test_resolved_when_detect_keyword_present(tmp_path: Path) -> None:
    _write_fragment(tmp_path, "persistence", "저장소 / 스키마", "b", _PERSISTENCE_DP)
    # user_id column addresses multi_tenant; deleted_at addresses soft_delete.
    skel = _skeleton("tasks: id PK, user_id FK, title, deleted_at datetime null")
    unresolved = find_unresolved_decisions(skel, tmp_path)
    assert unresolved == []


def test_partial_resolution(tmp_path: Path) -> None:
    _write_fragment(tmp_path, "persistence", "저장소 / 스키마", "b", _PERSISTENCE_DP)
    skel = _skeleton("tasks: id PK, user_id FK, title")  # multi_tenant ok, soft_delete not
    unresolved = find_unresolved_decisions(skel, tmp_path)
    ids = {(u.section_id, u.point_id) for u in unresolved}
    assert ("persistence", "soft_delete") in ids
    assert ("persistence", "multi_tenant") not in ids


def test_section_absent_from_skeleton_skipped(tmp_path: Path) -> None:
    _write_fragment(tmp_path, "persistence", "저장소 / 스키마", "b", _PERSISTENCE_DP)
    skel = "# Project Skeleton\n\n## 1. 개요\n설명 only, no persistence section\n"
    unresolved = find_unresolved_decisions(skel, tmp_path)
    assert unresolved == []


def test_detect_is_case_insensitive(tmp_path: Path) -> None:
    dp_yaml = (
        "decision_points:\n"
        "  - id: pagination\n"
        '    ask: "페이지네이션?"\n'
        "    detect: [Pagination, cursor, offset]\n"
    )
    _write_fragment(tmp_path, "persistence", "저장소 / 스키마", "b", dp_yaml)
    skel = _skeleton("results use CURSOR-based paging")
    assert find_unresolved_decisions(skel, tmp_path) == []


def test_unresolved_carries_question_and_hint(tmp_path: Path) -> None:
    _write_fragment(tmp_path, "persistence", "저장소 / 스키마", "b", _PERSISTENCE_DP)
    skel = _skeleton("PostgreSQL only")
    unresolved = find_unresolved_decisions(skel, tmp_path)
    mt = next(u for u in unresolved if u.point_id == "multi_tenant")
    assert isinstance(mt, UnresolvedDecision)
    assert mt.question == "데이터를 사용자별로 격리하나요, 전체 공유인가요?"
    assert "user_id" in mt.hint


def test_deterministic_order(tmp_path: Path) -> None:
    """Output order is stable: section order in skeleton, then point order."""
    _write_fragment(tmp_path, "persistence", "저장소 / 스키마", "b", _PERSISTENCE_DP)
    skel = _skeleton("PostgreSQL only")
    u1 = find_unresolved_decisions(skel, tmp_path)
    u2 = find_unresolved_decisions(skel, tmp_path)
    assert [x.point_id for x in u1] == [x.point_id for x in u2]
    assert [x.point_id for x in u1] == ["multi_tenant", "soft_delete"]
