"""Skeleton stale marker utilities.

Provides functions to mark skeleton.md sections as stale when
``migrate-plan`` removes sections from ``plan.skeleton_sections.included``.

Used by:
  - harness CLI (``~/.claude/harness/bin/harness``)
  - tests (``tests/orchestrator/test_migrate.py``)

Design:
  Fragment ID → heading location mapping strategy (robust order):
    1. Extract heading title from fragment *.md file (``## {{section_number}}. <title>``)
       → search skeleton.md for ``## N. <title>``
    2. Fallback: infer 1-based index from ``included_order`` position
       → use the N-th ``## N. ...`` heading in skeleton.md

  Idempotent: if a ``<!-- STALE:`` comment already follows the heading, skip.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

_STALE_PREFIX = "<!-- STALE:"
_HEADING_RE = re.compile(r"^(##\s+\d+\.\s+.+)$", re.MULTILINE)
_FRONTMATTER_RE = re.compile(r"^---\r?\n.*?\r?\n---\r?\n?", re.DOTALL)

# STALE marker template — {today} is substituted at call time.
_STALE_MARKER_TMPL = (
    "<!-- STALE: 이 섹션은 더 이상 활성 아님 (migrate-plan {today}). "
    "plan.profiles 점검 후 제거하거나, paired profile 추가 시 활성. -->\n"
)


def extract_fragment_heading_title(fragment_file: Path) -> str | None:
    """Fragment *.md 파일에서 헤딩 텍스트 추출 (frontmatter 제거 후 첫 ## 라인).

    Returns:
        "HTTP API" 같은 제목 문자열 (번호·점 제거), 실패 시 None.
    """
    try:
        text = fragment_file.read_text(encoding="utf-8")
    except OSError:
        return None
    body = _FRONTMATTER_RE.sub("", text, count=1).lstrip()
    m = re.search(r"^##\s+\{\{section_number\}\}\.\s+(.+)$", body, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return None


def _find_heading_line_by_title(lines: list[str], title: str) -> int | None:
    """skeleton.md 라인 목록에서 ``## N. <title>`` 헤딩 인덱스 탐색 (0-based)."""
    pat = re.compile(r"^##\s+\d+\.\s+" + re.escape(title) + r"\s*$")
    for i, ln in enumerate(lines):
        if pat.match(ln.rstrip("\r\n")):
            return i
    return None


def _find_heading_line_by_number(
    heading_line_indices: list[int], num: int
) -> int | None:
    """skeleton.md 헤딩 목록에서 1-based 번호로 라인 인덱스 반환."""
    if 1 <= num <= len(heading_line_indices):
        return heading_line_indices[num - 1]
    return None


def _resolve_heading_indices(
    lines: list[str],
    removed_ids: list[str],
    included_order: list[str],
    fragments_dir: Path,
    *,
    quiet: bool,
) -> dict[str, int | None]:
    """각 fragment ID 에 대응하는 skeleton.md 헤딩 라인 인덱스(0-based) 반환.

    찾지 못한 ID 는 None 매핑 (caller 가 skip 처리).
    """
    import sys

    heading_line_indices = [
        i for i, ln in enumerate(lines) if _HEADING_RE.match(ln.rstrip("\r\n"))
    ]
    id_to_index: dict[str, int] = {sid: i + 1 for i, sid in enumerate(included_order)}

    result: dict[str, int | None] = {}
    for fid in removed_ids:
        frag_file = fragments_dir / f"{fid}.md"
        title = extract_fragment_heading_title(frag_file)
        line_idx: int | None = None
        if title:
            line_idx = _find_heading_line_by_title(lines, title)
        if line_idx is None:
            num = id_to_index.get(fid)
            if num is not None:
                line_idx = _find_heading_line_by_number(heading_line_indices, num)
        if line_idx is None and not quiet:
            print(
                f"[WARN] skeleton.md 에서 '{fid}' 섹션 헤딩을 찾지 못했습니다 (skip).",
                file=sys.stderr,
            )
        result[fid] = line_idx
    return result


def preview_skeleton_stale(
    skeleton_path: Path,
    removed_ids: list[str],
    included_order: list[str],
    fragments_dir: Path,
) -> list[str]:
    """dry-run 전용: STALE 마킹 가능한 fragment ID 목록 반환 (파일 미수정).

    이미 STALE 마커가 있거나 헤딩을 찾지 못한 ID 는 제외.

    Args:
        skeleton_path: skeleton.md 절대 경로
        removed_ids: STALE 마킹 후보 fragment ID 리스트
        included_order: plan.skeleton_sections.included 순서 (번호 추론용)
        fragments_dir: fragment *.md 위치 (헤딩 타이틀 추출용)

    Returns:
        마킹 가능한 fragment ID 리스트 (정렬됨).
    """
    try:
        content = skeleton_path.read_text(encoding="utf-8")
    except OSError:
        return []

    lines = content.splitlines(keepends=True)
    heading_map = _resolve_heading_indices(
        lines, removed_ids, included_order, fragments_dir, quiet=True
    )

    will_mark: list[str] = []
    for fid, hi in heading_map.items():
        if hi is None:
            continue
        next_line = lines[hi + 1].strip() if hi + 1 < len(lines) else ""
        if next_line.startswith(_STALE_PREFIX):
            continue
        will_mark.append(fid)

    return sorted(will_mark)


def mark_skeleton_stale(
    skeleton_path: Path,
    removed_ids: list[str],
    included_order: list[str],
    fragments_dir: Path,
    *,
    no_backup: bool,
    quiet: bool,
    today: str | None = None,
) -> tuple[list[str], str | None]:
    """skeleton.md 의 removed_ids 에 해당하는 섹션 헤딩 아래에 STALE 마커 삽입.

    Args:
        skeleton_path: skeleton.md 절대 경로
        removed_ids: STALE 마킹할 fragment ID 리스트
        included_order: plan.skeleton_sections.included 순서 (번호 추론용)
        fragments_dir: fragment *.md 위치 (헤딩 타이틀 추출용)
        no_backup: True 면 skeleton 백업 생략
        quiet: True 면 stderr INFO 억제
        today: YYYY-MM-DD 날짜 문자열 (None 이면 UTC today 자동 생성)

    Returns:
        (marked_ids, backup_path): 실제 마킹된 ID 리스트(정렬됨), 생성된 백업 경로.

    Raises:
        OSError: 백업 생성 또는 skeleton.md 저장 실패 시.
    """
    import sys

    _today = today or datetime.now(UTC).strftime("%Y-%m-%d")

    try:
        original = skeleton_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"[WARN] skeleton.md 읽기 실패 ({skeleton_path}): {exc}", file=sys.stderr)
        return [], None

    lines = original.splitlines(keepends=True)
    heading_map = _resolve_heading_indices(
        lines, removed_ids, included_order, fragments_dir, quiet=quiet
    )

    # 마킹 대상: 헤딩 찾은 것 + 아직 STALE 없는 것
    to_mark: list[tuple[int, str]] = []
    for fid, hi in heading_map.items():
        if hi is None:
            continue
        next_line = lines[hi + 1].strip() if hi + 1 < len(lines) else ""
        if next_line.startswith(_STALE_PREFIX):
            continue
        to_mark.append((hi, fid))

    if not to_mark:
        return [], None

    # 백업 (수정 전)
    backup_path: str | None = None
    if not no_backup:
        ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        backup_name = f".backup-pre-migrate-skeleton-{ts}.md"
        backup_file = skeleton_path.parent / backup_name
        try:
            backup_file.write_text(original, encoding="utf-8")
            backup_path = str(backup_file)
        except OSError as exc:
            print(
                f"[FATAL] skeleton 백업 생성 실패 ({backup_file}): {exc}",
                file=sys.stderr,
            )
            raise

    # 높은 인덱스부터 삽입 (앞쪽 삽입이 뒤쪽 인덱스에 영향 없도록)
    to_mark_sorted = sorted(to_mark, key=lambda t: t[0], reverse=True)
    marked_ids: list[str] = []
    for hi, fid in to_mark_sorted:
        marker = _STALE_MARKER_TMPL.format(today=_today)
        lines.insert(hi + 1, marker)
        marked_ids.append(fid)

    try:
        skeleton_path.write_text("".join(lines), encoding="utf-8")
    except OSError as exc:
        print(f"[FATAL] skeleton.md 저장 실패 ({skeleton_path}): {exc}", file=sys.stderr)
        raise

    if not quiet and marked_ids:
        print(
            f"[INFO] skeleton.md STALE 마커 삽입: {sorted(marked_ids)} → {skeleton_path}",
            file=sys.stderr,
        )

    return sorted(marked_ids), backup_path
