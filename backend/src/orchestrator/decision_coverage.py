"""Decision-point coverage — semantic completeness gate for the design stage.

어휘 스캔(skeleton_checklist)이 못 잡는 *의미적* 빈칸을 taxonomy 기반으로 표면화한다.
각 fragment frontmatter 의 `decision_points` 는 "이 섹션에서 반드시 결정돼야 할 것"
(과거 LESSON/실패에서 추출한 공통 누락)을 데이터로 선언한다:

    decision_points:
      - id: multi_tenant
        ask: "데이터를 사용자별로 격리하나요, 전체 공유인가요?"
        detect: [사용자별, 격리, user_id, tenant]
        hint: "격리면 소유 컬럼(user_id) 필요"

판정(결정론, 이 모듈): 채워진 skeleton 의 해당 섹션 본문에 `detect` 키워드가
하나도 없으면 = 미결정 → clarify 후보. detect 는 pre-filter 다 — 실제 해소 여부의
최종 판단은 ha-design 스킬(LLM)이 AskUserQuestion 으로 확인한다.

`decision_points` 미선언 fragment 는 기존과 동일하게 동작 (additive).

연구 근거: taxonomy("common mistake types")로 유도한 질문이 zero-shot 보다 우수
(arXiv 2507.02858), 그리고 커버리지가 곧 "언제 멈출지" 정지 조건 (arXiv 2502.04485).

Entry points:
- load_decision_points(fragments_dir) -> {section_id: [DecisionPoint]}
- find_unresolved_decisions(skeleton_text, fragments_dir) -> [UnresolvedDecision]

Sibling: skeleton_checklist.py (lexical), consistency_checker.py (cross-section).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path

import yaml

from .context import split_sections_by_id

# Matches the leading YAML frontmatter block (mirrors profile_loader._FRONTMATTER_RE).
_FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---", re.DOTALL)

# Matches any unfilled angle-bracket placeholder span on a line (e.g. `<mutex / WAL>`).
# Lines containing such a span are excluded from detect scanning in its entirety —
# stripping only the span value is insufficient because the line's label (e.g. "동시성:")
# can itself fire a detect keyword, producing a false "resolved" verdict.
_PLACEHOLDER_LINE_RE = re.compile(r"<[^>\n]*>")


@dataclass(frozen=True)
class DecisionPoint:
    """A semantic decision that must be resolved for a section to be complete.

    section_id: owning fragment id (e.g. "persistence").
    point_id:   stable id within the section (e.g. "multi_tenant").
    ask:        Korean question shown to the user when unresolved.
    detect:     keywords whose presence in the section body marks the point
                addressed (case-insensitive substring; ANY match = addressed).
    hint:       optional answer-direction hint (empty string if omitted).
    """

    section_id: str
    point_id: str
    ask: str
    detect: tuple[str, ...]
    hint: str


@dataclass(frozen=True)
class UnresolvedDecision:
    """A decision point with no detect-keyword evidence in the skeleton."""

    section_id: str
    point_id: str
    question: str
    hint: str


def _parse_points(section_id: str, raw: object) -> list[DecisionPoint]:
    """Coerce the frontmatter `decision_points` value into DecisionPoint list.

    Silently drops malformed entries (missing id/ask) — formal validation is
    the job of `harness validate`, not the runtime path.
    """
    if not isinstance(raw, list):
        return []
    points: list[DecisionPoint] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        pid = item.get("id")
        ask = item.get("ask")
        if not isinstance(pid, str) or not isinstance(ask, str):
            continue
        detect_raw = item.get("detect", [])
        detect = (
            tuple(str(d) for d in detect_raw if isinstance(d, (str, int, float)))
            if isinstance(detect_raw, list)
            else ()
        )
        hint = item.get("hint", "")
        points.append(
            DecisionPoint(
                section_id=section_id,
                point_id=pid,
                ask=ask,
                detect=detect,
                hint=hint if isinstance(hint, str) else "",
            )
        )
    return points


def _filter_scaffolding_keywords(points: list[DecisionPoint], body: str) -> list[DecisionPoint]:
    """Drop detect keywords already present in the fragment's own template body.

    A keyword baked into the blank template (a heading like "### 백업 / 복구", a
    "- [ ] 비밀번호 해시" checklist item, an "OAuth 선택 시 …" guidance bullet) fires
    regardless of what the user decides, so it can never distinguish addressed
    from unaddressed — it only false-resolves the point once that scaffolding is
    echoed into the assembled skeleton. Placeholder (<...>) lines are excluded
    first, mirroring find_unresolved_decisions, so a keyword that lives only inside
    an unfilled placeholder is kept (it becomes real once the user fills it).

    Worst case a point loses every keyword and is always reported unresolved —
    the safe direction (over-ask) versus silently hiding a decision.
    """
    filled_lower = "\n".join(
        ln for ln in body.splitlines() if not _PLACEHOLDER_LINE_RE.search(ln)
    ).lower()
    result: list[DecisionPoint] = []
    for p in points:
        kept = tuple(kw for kw in p.detect if kw.lower() not in filled_lower)
        result.append(p if kept == p.detect else replace(p, detect=kept))
    return result


def load_decision_points(
    fragments_dir: Path | None = None,
) -> dict[str, list[DecisionPoint]]:
    """Parse every fragment's `decision_points` frontmatter into a dict.

    Returns {section_id: [DecisionPoint]} for fragments that declare at least
    one well-formed decision point. Fragments without the field are omitted.
    Missing dir → empty dict. Never raises on malformed files (skips them).
    """
    if fragments_dir is None or not fragments_dir.exists():
        return {}
    out: dict[str, list[DecisionPoint]] = {}
    for path in sorted(fragments_dir.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        m = _FRONTMATTER_RE.match(text)
        if not m:
            continue
        try:
            data = yaml.safe_load(m.group(1))
        except yaml.YAMLError:
            continue
        if not isinstance(data, dict):
            continue
        frag_id = data.get("id")
        if not isinstance(frag_id, str) or "decision_points" not in data:
            continue
        points = _parse_points(frag_id, data.get("decision_points"))
        if points:
            out[frag_id] = _filter_scaffolding_keywords(points, text[m.end() :])
    return out


def find_unresolved_decisions(
    skeleton_text: str,
    fragments_dir: Path | None = None,
) -> list[UnresolvedDecision]:
    """Return decision points with no detect-keyword evidence in the skeleton.

    Only sections actually present in the skeleton are examined (assembler only
    emits active sections). A point is *addressed* when any of its `detect`
    keywords appears (case-insensitive) anywhere in the section body — code
    fences included, since ER diagrams / schema tables are where persistence
    decisions get resolved (deliberately unlike the lexical clarity scan).

    Output order is deterministic: section order in the skeleton, then the
    declaration order of points within each section.
    """
    dp_by_id = load_decision_points(fragments_dir)
    if not dp_by_id:
        return []
    sections = split_sections_by_id(skeleton_text)

    results: list[UnresolvedDecision] = []
    for section_id, body in sections.items():
        points = dp_by_id.get(section_id)
        if not points:
            continue
        # Exclude lines that still contain an unfilled placeholder (<...>) before
        # running detect. The line label (e.g. "동시성:") can itself fire a detect
        # keyword, so removing only the span value is not enough — the whole line
        # must be dropped. Once the user replaces <...> with real content, the line
        # has no placeholder and is included again, allowing detect to work normally.
        filled_lines = [ln for ln in body.splitlines() if not _PLACEHOLDER_LINE_RE.search(ln)]
        body_lower = "\n".join(filled_lines).lower()
        for p in points:
            if any(kw.lower() in body_lower for kw in p.detect):
                continue
            results.append(
                UnresolvedDecision(
                    section_id=p.section_id,
                    point_id=p.point_id,
                    question=p.ask,
                    hint=p.hint,
                )
            )
    return results
