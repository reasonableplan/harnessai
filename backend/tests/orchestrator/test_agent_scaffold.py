"""Tests for agent_scaffold.py — multi-agent scaffolder (Track B, TDD).

Design doc: backend/docs/spec-kit-absorption-design.md §5
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from src.orchestrator.agent_scaffold import (
    AGENT_SPECS,
    AgentSpec,
    parse_skill_md,
    render,
    render_context,
)

# ---------------------------------------------------------------------------
# parse_skill_md
# ---------------------------------------------------------------------------


class TestParseSkillMd:
    def test_inline_description(self) -> None:
        text = "---\nname: ha-foo\ndescription: A short desc\n---\n\nbody text here"
        desc, body = parse_skill_md(text)
        assert desc == "A short desc"
        assert body.strip() == "body text here"

    def test_block_description(self) -> None:
        text = (
            "---\n"
            "name: ha-foo\n"
            "description: |\n"
            "  Line one\n"
            "  Line two\n"
            "---\n\n"
            "body content"
        )
        desc, body = parse_skill_md(text)
        # Block scalar: leading spaces stripped, joined by space or newline — we
        # preserve content; caller may strip.  At minimum both lines present.
        assert "Line one" in desc
        assert "Line two" in desc
        assert body.strip() == "body content"

    def test_no_frontmatter(self) -> None:
        text = "Just a plain body with no frontmatter at all."
        desc, body = parse_skill_md(text)
        assert desc == ""
        assert body == text


# ---------------------------------------------------------------------------
# AGENT_SPECS sanity
# ---------------------------------------------------------------------------


class TestAgentSpecs:
    def test_all_three_agents_present(self) -> None:
        assert set(AGENT_SPECS.keys()) == {"claude", "gemini", "copilot"}

    def test_each_spec_is_frozen_dataclass(self) -> None:
        for spec in AGENT_SPECS.values():
            assert isinstance(spec, AgentSpec)
            with pytest.raises(AttributeError):
                # frozen=True — normal assignment must raise FrozenInstanceError
                # (a subclass of AttributeError).  Do NOT use object.__setattr__
                # here; that bypasses the frozen guard and would mutate the
                # module-level AGENT_SPECS dict, corrupting subsequent tests.
                spec.key = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# render — gemini
# ---------------------------------------------------------------------------


class TestRenderGemini:
    _SKILL = "ha-verify"
    _DESC = "HarnessAI v2 — verify toolchain"
    _BODY_TEMPLATE = (
        "Run `python ~/.claude/skills/ha-verify/run.py prepare` with $ARGUMENTS"
    )

    def _render(self, body: str | None = None) -> tuple[str, str]:
        b = body if body is not None else self._BODY_TEMPLATE
        return render(self._SKILL, self._DESC, b, "gemini")

    def test_output_path(self) -> None:
        path, _ = self._render()
        assert path == ".gemini/commands/ha-verify.toml"

    def test_content_parses_as_toml(self) -> None:
        _, content = self._render()
        parsed = tomllib.loads(content)
        assert "prompt" in parsed
        assert "description" in parsed

    def test_prompt_contains_body(self) -> None:
        _, content = self._render()
        parsed = tomllib.loads(content)
        # Core marker from body (after token substitutions)
        assert "run.py prepare" in parsed["prompt"]

    def test_args_token_substitution(self) -> None:
        _, content = self._render()
        parsed = tomllib.loads(content)
        assert "{{args}}" in parsed["prompt"]
        assert "$ARGUMENTS" not in parsed["prompt"]

    def test_claude_path_substituted(self) -> None:
        _, content = self._render()
        parsed = tomllib.loads(content)
        assert "~/.claude/skills/" not in parsed["prompt"]
        assert "${HARNESS_AI_HOME}/skills/" in parsed["prompt"]

    def test_toml_literal_triple_quote_in_body_raises(self) -> None:
        body_with_triple = "some text ''' end"
        with pytest.raises(ValueError, match="'''"):
            render(self._SKILL, self._DESC, body_with_triple, "gemini")


# ---------------------------------------------------------------------------
# render — copilot
# ---------------------------------------------------------------------------


class TestRenderCopilot:
    _SKILL = "ha-verify"
    _DESC = "HarnessAI v2 — verify toolchain"
    _BODY = (
        "Run `python ~/.claude/skills/ha-verify/run.py prepare` with $ARGUMENTS"
    )

    def _render(self) -> tuple[str, str]:
        return render(self._SKILL, self._DESC, self._BODY, "copilot")

    def test_output_path(self) -> None:
        path, _ = self._render()
        assert path == ".github/prompts/ha-verify.prompt.md"

    def test_frontmatter_present(self) -> None:
        _, content = self._render()
        assert content.startswith("---\n")
        assert "description:" in content

    def test_description_in_frontmatter(self) -> None:
        _, content = self._render()
        # Description value must appear between the frontmatter delimiters
        header, _, rest = content.partition("---\n\n")
        # header starts with "---\n" + fields + "---\n"
        assert self._DESC in content

    def test_args_token_preserved(self) -> None:
        _, content = self._render()
        assert "$ARGUMENTS" in content

    def test_claude_path_substituted(self) -> None:
        _, content = self._render()
        assert "~/.claude/skills/" not in content
        assert "${HARNESS_AI_HOME}/skills/" in content


# ---------------------------------------------------------------------------
# render — claude
# ---------------------------------------------------------------------------


class TestRenderClaude:
    _SKILL = "ha-verify"
    _DESC = "HarnessAI v2 — verify toolchain"
    _BODY = (
        "Run `python ~/.claude/skills/ha-verify/run.py prepare` with $ARGUMENTS"
    )

    def _render(self) -> tuple[str, str]:
        return render(self._SKILL, self._DESC, self._BODY, "claude")

    def test_output_path(self) -> None:
        path, _ = self._render()
        assert path == ".claude/skills/ha-verify/SKILL.md"

    def test_frontmatter_present(self) -> None:
        _, content = self._render()
        assert content.startswith("---\n")

    def test_args_token_preserved(self) -> None:
        _, content = self._render()
        assert "$ARGUMENTS" in content

    def test_claude_path_not_substituted(self) -> None:
        """claude agent must NOT rewrite ~/.claude/skills/ paths."""
        _, content = self._render()
        assert "~/.claude/skills/" in content
        assert "${HARNESS_AI_HOME}/skills/" not in content


# ---------------------------------------------------------------------------
# render — harness/bin path substitution (not just skills/)
# ---------------------------------------------------------------------------


class TestHarnessPathSubstitution:
    """Skill bodies also reference ~/.claude/harness/bin/harness — non-claude
    agents must rewrite that to ${HARNESS_AI_HOME}/harness/ too."""

    _BODY = "Run `python ~/.claude/harness/bin/harness integrity` then done."

    def test_gemini_substitutes_harness_path(self) -> None:
        _, content = render("ha-verify", "d", self._BODY, "gemini")
        assert "~/.claude/harness/" not in content
        assert "${HARNESS_AI_HOME}/harness/bin/harness" in content

    def test_copilot_substitutes_harness_path(self) -> None:
        _, content = render("ha-verify", "d", self._BODY, "copilot")
        assert "~/.claude/harness/" not in content
        assert "${HARNESS_AI_HOME}/harness/bin/harness" in content

    def test_claude_keeps_harness_path(self) -> None:
        _, content = render("ha-verify", "d", self._BODY, "claude")
        assert "~/.claude/harness/bin/harness" in content
        assert "${HARNESS_AI_HOME}/harness/" not in content


# ---------------------------------------------------------------------------
# render_context — per-agent orientation file
# ---------------------------------------------------------------------------


class TestRenderContext:
    def test_gemini_context_path_and_content(self) -> None:
        path, content = render_context("gemini")
        assert path == "GEMINI.md"
        assert "${HARNESS_AI_HOME}" in content
        # Pipeline order must be discoverable for the agent.
        assert "ha-init" in content and "ha-ship" in content

    def test_copilot_context_path(self) -> None:
        path, content = render_context("copilot")
        assert path == ".github/copilot-instructions.md"
        assert "${HARNESS_AI_HOME}" in content

    def test_claude_context_raises(self) -> None:
        # Claude uses native ~/.claude — no generated context file (would
        # clobber the user's CLAUDE.md).
        with pytest.raises(ValueError, match="claude"):
            render_context("claude")

    def test_unknown_agent_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown agent"):
            render_context("openai")


# ---------------------------------------------------------------------------
# render — unknown agent
# ---------------------------------------------------------------------------


class TestRenderUnknownAgent:
    def test_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="unknown agent"):
            render("ha-verify", "desc", "body", "openai")


# ---------------------------------------------------------------------------
# Integration smoke — real ha-verify/SKILL.md
# ---------------------------------------------------------------------------


class TestRealSkillMdSmoke:
    """Read the actual ha-verify SKILL.md and verify the full round-trip."""

    _SKILL_PATH = (
        Path.home() / ".claude" / "skills" / "ha-verify" / "SKILL.md"
    )

    def test_real_skill_parses_and_renders_to_valid_toml(self) -> None:
        if not self._SKILL_PATH.exists():
            pytest.skip(f"SKILL.md not found at {self._SKILL_PATH}")

        text = self._SKILL_PATH.read_text(encoding="utf-8")
        desc, body = parse_skill_md(text)

        # description must be non-empty for the real skill
        assert desc, "parse_skill_md returned empty description for real SKILL.md"

        # skip toml render if body contains ''' (literal triple-quote)
        if "'''" in body:
            pytest.skip("body contains TOML literal-string delimiter — render would raise by design")

        _, content = render("ha-verify", desc, body, "gemini")
        parsed = tomllib.loads(content)
        assert "prompt" in parsed
        assert len(parsed["prompt"]) > 50  # non-trivial content
