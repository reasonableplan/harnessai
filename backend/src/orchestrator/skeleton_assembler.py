"""Skeleton assembler — load section fragments and assemble into skeleton.md.

Naming note (v0.10.0): "skeleton" is a *technique name* in harness engineering
(contract-first project specification with frozen sections), not a document
filename. The output file (currently `skeleton.md`) is scheduled to be renamed
to `spec.md` in v1.0.0 to separate the technique from the artifact. This class
name (`SkeletonAssembler`) stays — it refers to the technique.

See design doc §4 (skeleton system).
- Fragment locations: ~/.claude/harness/templates/skeleton/<section_id>.md (global)
                      or {project}/.claude/harness/templates/skeleton/<section_id>.md (local)
- Local override takes precedence
- Strips frontmatter and substitutes {{section_number}} placeholders
"""

from __future__ import annotations

import re
from pathlib import Path

DEFAULT_HARNESS_DIR = Path.home() / ".claude" / "harness"

_FRONTMATTER_RE = re.compile(r"^---\r?\n.*?\r?\n---\r?\n?", re.DOTALL)
_PLACEHOLDER_NUMBER = "{{section_number}}"

# Unreplaced template placeholders (e.g. <pkg>, <cmd_a>, <본문>).
# (?![A-Z]) excludes ASCII uppercase first char — protects TS generics (<T>, <K,V>).
# [^\W\d] matches Unicode letter or underscore (no digit) as first char.
# \w* matches subsequent Unicode word chars (letters, digits, _).
# KEEP IN SYNC with harness/bin/harness._PLACEHOLDER_RE (#15).
_ANGLE_PLACEHOLDER_RE = re.compile(r"<(?![A-Z])[^\W\d]\w*>")
# Non-filesystem code fences (```python, ```ts, …) — example placeholders allowed inside.
_NON_FS_CODE_BLOCK_RE = re.compile(r"```(?!filesystem)\w*\n.*?\n```", re.DOTALL)
# Inline backtick code spans — stripped before placeholder scanning.
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
# Standard HTML/MDX tags — excluded to prevent placeholder false positives.
# KEEP IN SYNC with harness/bin/harness._HTML_TAGS — drift is caught by
# backend/tests/skills/test_html_tags_sync.py.
_HTML_TAGS = frozenset(
    {
        "a",
        "abbr",
        "address",
        "area",
        "article",
        "aside",
        "audio",
        "b",
        "base",
        "bdi",
        "bdo",
        "blockquote",
        "body",
        "br",
        "button",
        "canvas",
        "caption",
        "cite",
        "code",
        "col",
        "colgroup",
        "data",
        "datalist",
        "dd",
        "del",
        "details",
        "dfn",
        "dialog",
        "div",
        "dl",
        "dt",
        "em",
        "embed",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "head",
        "header",
        "hgroup",
        "hr",
        "html",
        "i",
        "iframe",
        "img",
        "input",
        "ins",
        "kbd",
        "label",
        "legend",
        "li",
        "link",
        "main",
        "map",
        "mark",
        "meta",
        "meter",
        "nav",
        "noscript",
        "object",
        "ol",
        "optgroup",
        "option",
        "output",
        "p",
        "param",
        "picture",
        "pre",
        "progress",
        "q",
        "rp",
        "rt",
        "ruby",
        "s",
        "samp",
        "script",
        "section",
        "select",
        "slot",
        "small",
        "source",
        "span",
        "strong",
        "style",
        "sub",
        "summary",
        "sup",
        "table",
        "tbody",
        "td",
        "template",
        "textarea",
        "tfoot",
        "th",
        "thead",
        "time",
        "title",
        "tr",
        "track",
        "u",
        "ul",
        "var",
        "video",
        "wbr",
        # SVG
        "svg",
        "path",
        "rect",
        "circle",
        "line",
        "polyline",
        "polygon",
        "g",
        "ellipse",
        "defs",
        "use",
        "symbol",
        "mask",
        "pattern",
        "clippath",
        "lineargradient",
        "radialgradient",
        "stop",
        "text",
        "tspan",
    }
)


class FragmentNotFoundError(LookupError):
    """Section fragment file not found in either global or local locations."""


def find_placeholders(text: str) -> dict[str, list[int]]:
    """Locate unreplaced template placeholders (<pkg> etc.) in an assembled skeleton.

    Non-filesystem code fences are stripped (example placeholders allowed).
    ```filesystem blocks are kept — declared paths must be real (integrity gate).
    Standard HTML/SVG tags (<div>, <pre>, <svg>, …) are excluded to avoid
    false positives. Line numbers refer to the original text (newlines are
    preserved when sanitizing).

    Returns:
        {placeholder_literal: [line_numbers]}; empty dict if none.
    """

    def _strip_block(m: re.Match[str]) -> str:
        # Preserve newlines so line numbers stay accurate
        return "\n" * m.group(0).count("\n")

    sanitized = _NON_FS_CODE_BLOCK_RE.sub(_strip_block, text)
    found: dict[str, list[int]] = {}
    for lineno, line in enumerate(sanitized.splitlines(), 1):
        # Strip inline backtick code (e.g. `<pkg>` in markdown) — these are
        # illustrative format markers, not placeholders to replace.
        stripped = _INLINE_CODE_RE.sub("", line)
        for match in _ANGLE_PLACEHOLDER_RE.finditer(stripped):
            literal = match.group(0)
            tag_name = literal[1:-1]
            if tag_name in _HTML_TAGS:
                continue
            found.setdefault(literal, []).append(lineno)
    return found


class SkeletonAssembler:
    """Load section fragments and assemble them into skeleton.md.

    Local fragments override global ones:
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
        """Return fragment body text with frontmatter stripped.

        Raises:
            FragmentNotFoundError: if the fragment is not found globally or locally.
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
        """Assemble fragments in the given order.

        Each fragment's ``{{section_number}}`` placeholder is replaced with a
        1-based index. Sections are separated by blank lines for Markdown
        readability. An empty ``section_ids`` list returns just the title.

        Args:
            section_ids: section IDs in order. Duplicates are dropped (first wins).
            title: top-level skeleton title (``# {title}``).
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

    # Internals

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
        global_path = self.harness_dir / "templates" / "skeleton" / f"{section_id}.md"
        if global_path.exists():
            return global_path
        raise FragmentNotFoundError(f"section fragment '{section_id}.md' not found")
