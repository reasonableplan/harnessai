"""Multi-agent scaffolder — Track B (Spec Kit integrations pattern).

Converts an agent-neutral SKILL.md source into per-agent command files
(Gemini TOML, Copilot prompt.md, Claude SKILL.md) without touching the
filesystem.  All I/O is the caller's responsibility; this module is pure
string-in / string-out.

Design doc: backend/docs/spec-kit-absorption-design.md §5
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Agent spec table
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentSpec:
    """Per-agent adapter: output path template, format, and token mappings."""

    key: str
    commands_dir: str     # e.g. ".gemini/commands"
    file_template: str    # e.g. "{name}.toml"  (claude uses "{name}/SKILL.md")
    fmt: str              # "toml" | "md_frontmatter"
    args_token: str       # $ARGUMENTS is replaced with this in body
    context_file: str


AGENT_SPECS: dict[str, AgentSpec] = {
    "claude": AgentSpec(
        key="claude",
        commands_dir=".claude/skills",
        file_template="{name}/SKILL.md",
        fmt="md_frontmatter",
        args_token="$ARGUMENTS",          # no substitution for claude
        context_file="CLAUDE.md",
    ),
    "gemini": AgentSpec(
        key="gemini",
        commands_dir=".gemini/commands",
        file_template="{name}.toml",
        fmt="toml",
        args_token="{{args}}",
        context_file="GEMINI.md",
    ),
    "copilot": AgentSpec(
        key="copilot",
        commands_dir=".github/prompts",
        file_template="{name}.prompt.md",
        fmt="md_frontmatter",
        args_token="$ARGUMENTS",          # same token as claude
        context_file=".github/copilot-instructions.md",
    ),
}

# ---------------------------------------------------------------------------
# Frontmatter parser
# ---------------------------------------------------------------------------

# Matches the opening and closing --- delimiters of YAML frontmatter.
_FM_RE = re.compile(r"^---\r?\n(.*?)^---\r?\n", re.DOTALL | re.MULTILINE)

# Inline description:  description: some text
_DESC_INLINE_RE = re.compile(r"^description:\s*(.+)$", re.MULTILINE)

# Block-scalar description:
#   description: |
#     line one
#     line two
# Captures all indented continuation lines that follow the `|` marker.
_DESC_BLOCK_RE = re.compile(
    r"^description:\s*\|\s*\r?\n((?:[ \t]+.+\r?\n?)*)",
    re.MULTILINE,
)


def parse_skill_md(text: str) -> tuple[str, str]:
    """Parse an agent-neutral SKILL.md and return (description, body).

    - description: extracted from frontmatter `description:` field.
      Supports both inline (``description: foo``) and block-scalar
      (``description: |\\n  line one\\n  line two``) forms.
      Returns "" when no frontmatter is present.
    - body: everything after the closing ``---`` of the frontmatter,
      including the leading newline.  When there is no frontmatter,
      body == text (the full input).
    """
    m = _FM_RE.search(text)
    if m is None:
        return "", text

    fm_content = m.group(1)
    body_start = m.end()
    body = text[body_start:]

    # Try block-scalar first (more specific pattern).
    block = _DESC_BLOCK_RE.search(fm_content)
    if block:
        raw_lines = block.group(1).splitlines()
        # Strip common leading whitespace (first non-empty line determines indent).
        stripped = [line.rstrip() for line in raw_lines]
        # Remove leading indent (YAML block scalars use consistent indentation).
        if stripped:
            indent = len(stripped[0]) - len(stripped[0].lstrip())
            stripped = [line[indent:] if len(line) >= indent else line for line in stripped]
        description = "\n".join(stripped).strip()
        return description, body

    # Inline form.
    inline = _DESC_INLINE_RE.search(fm_content)
    if inline:
        return inline.group(1).strip(), body

    return "", body


# ---------------------------------------------------------------------------
# Path helper
# ---------------------------------------------------------------------------

_CLAUDE_PATH_RE = re.compile(r"~/\.claude/skills/")
_HARNESS_REPLACEMENT = "${HARNESS_AI_HOME}/skills/"


def _substitute_body(body: str, spec: AgentSpec) -> str:
    """Apply token and path substitutions to the command body.

    1. args token: replace $ARGUMENTS with spec.args_token.
       (For claude and copilot the token is identical, so effectively a no-op.)
    2. run.py path: replace ~/.claude/skills/ with ${HARNESS_AI_HOME}/skills/
       for every agent except claude (claude uses ~/.claude natively).
    """
    result = body.replace("$ARGUMENTS", spec.args_token)

    if spec.key != "claude":
        result = _CLAUDE_PATH_RE.sub(_HARNESS_REPLACEMENT, result)

    return result


# ---------------------------------------------------------------------------
# Format renderers
# ---------------------------------------------------------------------------


def _render_toml(description: str, body: str) -> str:
    """Render Gemini TOML using a TOML literal multi-line string (''').

    The literal string form means backslashes and double-quotes inside
    the Markdown body do NOT need escaping.  However, ''' itself is
    forbidden inside a literal string — we raise ValueError so the
    caller can decide how to handle it.

    The TOML ``description`` key uses a basic single-line string, so only
    the first non-empty line of *description* is used (block-scalar sources
    may contain embedded newlines which are illegal in a TOML basic string).
    """
    if "'''" in body:
        raise ValueError(
            "body contains TOML literal-string delimiter (''') — "
            "cannot render as TOML literal multi-line string without escaping"
        )

    # Use only the first non-empty line: TOML basic strings forbid newlines.
    first_line = next(
        (line.strip() for line in description.splitlines() if line.strip()),
        description,
    )
    # Escape double-quotes in description for the basic string value.
    safe_desc = first_line.replace('"', '\\"')

    return f'description = "{safe_desc}"\n\nprompt = \'\'\'\n{body}\n\'\'\'\n'


def _render_md_frontmatter(description: str, body: str) -> str:
    """Render markdown with YAML frontmatter (claude / copilot)."""
    return f"---\ndescription: {description}\n---\n\n{body}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render(skill_name: str, description: str, body: str, agent: str) -> tuple[str, str]:
    """Render a skill for the given agent.

    Parameters
    ----------
    skill_name:
        Bare skill name, e.g. ``"ha-verify"``.
    description:
        One-line description extracted from the neutral SKILL.md.
    body:
        Command body text (everything after the frontmatter closing ``---``).
    agent:
        One of ``"claude"``, ``"gemini"``, ``"copilot"``.

    Returns
    -------
    (relative_output_path, file_content)
        relative_output_path is relative to the project root, e.g.
        ``".gemini/commands/ha-verify.toml"``.

    Raises
    ------
    ValueError
        If *agent* is not a key in AGENT_SPECS, or if the TOML literal
        delimiter conflict is detected.
    """
    if agent not in AGENT_SPECS:
        raise ValueError(
            f"unknown agent {agent!r} — must be one of {sorted(AGENT_SPECS)}"
        )

    spec = AGENT_SPECS[agent]

    # Build output path.
    filename = spec.file_template.format(name=skill_name)
    output_path = f"{spec.commands_dir}/{filename}"

    # Apply body transformations.
    transformed_body = _substitute_body(body, spec)

    # Render to target format.
    if spec.fmt == "toml":
        content = _render_toml(description, transformed_body)
    else:
        content = _render_md_frontmatter(description, transformed_body)

    return output_path, content
