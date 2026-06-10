"""SECTION_TITLES ↔ fragment frontmatter 동기화 회귀 테스트.

제목이 사실상 스키마다 — skeleton 조립 헤딩, consistency checker, 섹션 hash,
extract_section_by_id, 역방향 contract 검증이 전부 제목→ID 매핑에 의존한다.
fragment 의 `name:` 과 context.SECTION_TITLES 가 어긋나면 이 기능들이
경고 없이 침묵 사망하므로, 양방향 동기를 여기서 고정한다.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.orchestrator.context import SECTION_TITLES

REPO_ROOT = Path(__file__).resolve().parents[3]
FRAGMENTS_DIR = REPO_ROOT / "harness" / "templates" / "skeleton"

_FRONTMATTER_RE = re.compile(r"^---\r?\n(.*?)\r?\n---", re.DOTALL)


def _frontmatter_fields(text: str, name: str) -> dict[str, str]:
    m = _FRONTMATTER_RE.match(text)
    assert m, f"{name}: frontmatter 블록 없음"
    fields: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields


def _fragment_files() -> list[Path]:
    # "_" prefix 는 fragment 가 아닌 메타 문서 (_README.md 등) — 제외.
    files = [p for p in FRAGMENTS_DIR.glob("*.md") if not p.name.startswith("_")]
    assert files, f"fragments 디렉토리 비어 있음: {FRAGMENTS_DIR}"
    return files


def test_every_fragment_name_matches_section_titles() -> None:
    """모든 fragment 의 frontmatter name 이 SECTION_TITLES[id] 와 토씨까지 일치."""
    for p in _fragment_files():
        fields = _frontmatter_fields(p.read_text(encoding="utf-8"), p.name)
        sid = fields.get("id")
        name = fields.get("name")
        assert sid in SECTION_TITLES, (
            f"{p.name}: id '{sid}' 가 SECTION_TITLES 에 없음 — "
            "context.py 와 fragment 중 한쪽이 stale"
        )
        assert SECTION_TITLES[sid] == name, (
            f"{p.name}: name '{name}' != SECTION_TITLES['{sid}'] "
            f"'{SECTION_TITLES[sid]}' — 제목 키잉 기능 전부 침묵 사망"
        )


_BODY_HEADING_RE = re.compile(
    r"^## \{\{section_number\}\}\.\s+(.+?)\s*$", re.MULTILINE
)


def test_every_fragment_body_heading_matches_name() -> None:
    """fragment 본문 헤딩(조립 시 skeleton 에 박히는 실제 제목)도 name 과 일치."""
    for p in _fragment_files():
        text = p.read_text(encoding="utf-8")
        fields = _frontmatter_fields(text, p.name)
        m = _BODY_HEADING_RE.search(text)
        assert m, f"{p.name}: '## {{{{section_number}}}}. <제목>' 헤딩 없음"
        assert m.group(1).strip() == fields.get("name"), (
            f"{p.name}: 본문 헤딩 '{m.group(1).strip()}' != frontmatter name "
            f"'{fields.get('name')}' — 조립된 skeleton 과 메타데이터가 어긋남"
        )


def test_every_section_title_has_fragment() -> None:
    """SECTION_TITLES 의 모든 ID 에 대응 fragment 파일 존재 (역방향)."""
    fragment_ids = {
        _frontmatter_fields(p.read_text(encoding="utf-8"), p.name).get("id")
        for p in _fragment_files()
    }
    missing = sorted(sid for sid in SECTION_TITLES if sid not in fragment_ids)
    assert not missing, f"fragment 파일 없는 SECTION_TITLES 항목: {missing}"


def test_canonical_order_matches_section_titles() -> None:
    """CANONICAL_SECTION_ORDER 는 SECTION_TITLES 와 동일 키셋 (S-1).

    어긋나면 신형 섹션이 canonical 위치 없이 또 dangling 하게 된다.
    """
    from src.orchestrator.context import CANONICAL_SECTION_ORDER

    assert len(CANONICAL_SECTION_ORDER) == len(set(CANONICAL_SECTION_ORDER)), "중복 ID"
    assert set(CANONICAL_SECTION_ORDER) == set(SECTION_TITLES), (
        f"차이: {set(CANONICAL_SECTION_ORDER) ^ set(SECTION_TITLES)}"
    )
    assert CANONICAL_SECTION_ORDER[-2:] == ("tasks", "notes")
