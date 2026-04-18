"""Skeleton assembler — 섹션 조각 로드 + 조립.

설계 문서 §4 (skeleton 시스템) 참조.
- 조각 위치: ~/.claude/harness/templates/skeleton/<section_id>.md (글로벌)
            또는 {project}/.claude/harness/templates/skeleton/<section_id>.md (로컬)
- 로컬 override 우선
- 본문에서 frontmatter 제거 + {{section_number}} 치환
"""

from __future__ import annotations

import re
from pathlib import Path

DEFAULT_HARNESS_DIR = Path.home() / ".claude" / "harness"

_FRONTMATTER_RE = re.compile(r"^---\r?\n.*?\r?\n---\r?\n?", re.DOTALL)
_PLACEHOLDER_NUMBER = "{{section_number}}"

# 치환 안 된 템플릿 플레이스홀더 (예: <pkg>, <cmd_a>, <domain>). lowercase snake_case.
_ANGLE_PLACEHOLDER_RE = re.compile(r"<[a-z_][a-z0-9_]*>")
# non-filesystem 코드 블록 (예: ```python, ```ts) — 예제용 placeholder 허용.
_NON_FS_CODE_BLOCK_RE = re.compile(r"```(?!filesystem)\w*\n.*?\n```", re.DOTALL)
# 표준 HTML/MDX 태그 — 플레이스홀더 오탐 방지.
_HTML_TAGS = frozenset({
    "a", "abbr", "address", "area", "article", "aside", "audio",
    "b", "base", "bdi", "bdo", "blockquote", "body", "br", "button",
    "canvas", "caption", "cite", "code", "col", "colgroup",
    "data", "datalist", "dd", "del", "details", "dfn", "dialog", "div", "dl", "dt",
    "em", "embed", "fieldset", "figcaption", "figure", "footer", "form",
    "h1", "h2", "h3", "h4", "h5", "h6", "head", "header", "hgroup", "hr", "html",
    "i", "iframe", "img", "input", "ins",
    "kbd", "label", "legend", "li", "link",
    "main", "map", "mark", "meta", "meter",
    "nav", "noscript", "object", "ol", "optgroup", "option", "output",
    "p", "param", "picture", "pre", "progress",
    "q", "rp", "rt", "ruby", "s", "samp", "script", "section", "select",
    "slot", "small", "source", "span", "strong", "style", "sub", "summary", "sup",
    "table", "tbody", "td", "template", "textarea", "tfoot", "th", "thead",
    "time", "title", "tr", "track", "u", "ul", "var", "video", "wbr",
    # SVG
    "svg", "path", "rect", "circle", "line", "polyline", "polygon", "g",
    "ellipse", "defs", "use", "symbol", "mask", "pattern", "clippath",
    "lineargradient", "radialgradient", "stop", "text", "tspan",
})


class FragmentNotFoundError(LookupError):
    """섹션 조각 파일을 글로벌·로컬 어느 곳에서도 찾을 수 없음."""


def find_placeholders(text: str) -> dict[str, list[int]]:
    """assembled skeleton 에서 미치환 템플릿 placeholder (<pkg> 등) 탐색.

    - 코드 블록 (```python, ```ts 등) 내 예제 placeholder 는 제외.
    - ```filesystem 블록은 포함 (실제 경로여야 함 — LESSON-018 관련 정합성 게이트).
    - HTML/SVG 표준 태그 (`<div>`, `<pre>`, `<svg>` 등) 는 제외 — false positive 방지.
    - 라인 번호는 원본 기준 (sanitize 시 개행 유지).

    Returns:
        {placeholder_literal: [line_numbers]}. 없으면 빈 dict.
    """
    def _strip_block(m: re.Match[str]) -> str:
        # 개행만 남겨 라인 번호 보존
        return "\n" * m.group(0).count("\n")

    sanitized = _NON_FS_CODE_BLOCK_RE.sub(_strip_block, text)
    found: dict[str, list[int]] = {}
    for lineno, line in enumerate(sanitized.splitlines(), 1):
        # 인라인 백틱 코드 (`<pkg>` 같은 템플릿 예시) 제거 — 치환 안 해도 되는 형식 표시
        stripped = re.sub(r"`[^`\n]*`", "", line)
        for match in _ANGLE_PLACEHOLDER_RE.finditer(stripped):
            literal = match.group(0)
            # HTML/SVG 태그 제외
            tag_name = literal[1:-1]
            if tag_name in _HTML_TAGS:
                continue
            found.setdefault(literal, []).append(lineno)
    return found


class SkeletonAssembler:
    """섹션 조각 로드 + 조립.

    로컬 override 우선:
      1. {project}/.claude/harness/templates/skeleton/<id>.md
      2. {harness_dir}/templates/skeleton/<id>.md
    """

    def __init__(
        self,
        harness_dir: Path | None = None,
        project_dir: Path | None = None,
    ) -> None:
        self.harness_dir = (harness_dir or DEFAULT_HARNESS_DIR).resolve()
        self.project_dir = project_dir.resolve() if project_dir else None
        self._fragment_cache: dict[str, str] = {}

    def load_fragment(self, section_id: str) -> str:
        """조각 파일에서 frontmatter 제거된 body 텍스트 반환.

        Raises:
            FragmentNotFoundError: 글로벌/로컬 모두 없음
        """
        if section_id in self._fragment_cache:
            return self._fragment_cache[section_id]

        path = self._resolve_fragment_path(section_id)
        text = path.read_text(encoding="utf-8")
        body = _FRONTMATTER_RE.sub("", text, count=1).lstrip()
        self._fragment_cache[section_id] = body
        return body

    def assemble(
        self,
        section_ids: list[str],
        *,
        title: str = "Project Skeleton",
    ) -> str:
        """주어진 섹션 ID 순서대로 조립한다.

        - 각 조각의 {{section_number}} 자리에 1부터 시작하는 인덱스 치환
        - 섹션 사이는 빈 줄 두 개로 구분 (Markdown 가독성)
        - 빈 section_ids → 제목만 반환

        Args:
            section_ids: 조립할 섹션 ID 순서대로 (중복 자동 제거 — 첫 등장만 사용)
            title: skeleton 최상위 제목 (`# {title}`)
        """
        seen: set[str] = set()
        ordered: list[str] = []
        for sid in section_ids:
            if sid in seen:
                continue
            seen.add(sid)
            ordered.append(sid)

        parts: list[str] = [f"# {title}"]
        for idx, sid in enumerate(ordered, start=1):
            body = self.load_fragment(sid)
            body = body.replace(_PLACEHOLDER_NUMBER, str(idx))
            parts.append(body.rstrip())

        return "\n\n".join(parts) + "\n"

    # ── 내부 ────────────────────────────────────────────────────────────

    def _resolve_fragment_path(self, section_id: str) -> Path:
        if self.project_dir:
            local = (
                self.project_dir
                / ".claude"
                / "harness"
                / "templates"
                / "skeleton"
                / f"{section_id}.md"
            )
            if local.exists():
                return local
        global_path = (
            self.harness_dir / "templates" / "skeleton" / f"{section_id}.md"
        )
        if global_path.exists():
            return global_path
        raise FragmentNotFoundError(f"섹션 조각 '{section_id}.md' 를 찾을 수 없음")
