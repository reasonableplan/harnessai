"""Cross-section consistency checks for skeleton.md / tasks.md.

Used by /ha-redesign (after applied) and (eventually) /ha-review to surface drift
where re-derivation or task additions break the implicit reference graph between
sections — the structural defect that the v0.7.0 mutation-propagation track was
created to address.

Findings are advisory (severity="info"|"warn") — never blocking. The point is to
give the next agent or reviewer a concrete checklist, not to gate progress with
heuristic rules. A blocker would need stronger guarantees than regex can provide.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from src.orchestrator.context import SECTION_TITLES
from src.orchestrator.task_id import SKELETON_HEADING_RE, TASK_ROW_RE

# CamelCase token of length ≥4 to filter noise. Captures component/class names
# such as GameScreen, PushToTalkButton, DetectionAlertSheet. Lower bound avoids
# matching plain words like "ID" or "OK".
_CAMELCASE_RE = re.compile(r"\b([A-Z][a-z]+(?:[A-Z][a-z]*)+)\b")

# Section reference inside text: "§13" or "§ 13".
_SECTION_REF_RE = re.compile(r"§\s*\d+")

# Component-bearing sections, keyed by fragment ID — NOT heading number.
# Heading numbers are assigned dynamically at assembly time (skeleton_assembler
# enumerates the active fragment set), so which section lands at §13 varies per
# project's 6-axis activation. view.components holds the canonical component
# tree; state.flow and core.logic are where each component must be wired in.
_COMPONENT_DEFINITION_IDS = ("view.components",)
_COMPONENT_REFERENCE_IDS = ("state.flow", "core.logic")

# Inverted SECTION_TITLES — heading title → section ID. Titles are unique and
# the assembler enforces them verbatim, so exact match is the reliable key.
_TITLE_TO_ID = {title: sid for sid, title in SECTION_TITLES.items()}


@dataclass(frozen=True)
class ConsistencyFinding:
    """Single consistency check result.

    severity:
        - "info":   informational — likely benign drift, surface for review.
        - "warn":   probable issue — re-derivation may have missed a section.
    """

    severity: str
    pattern: str  # short label: "isolated-component" | "task-no-reference"
    message: str
    target: str  # the identifier (component name, T-XXX, etc.) the finding is about


def _split_sections(skel_text: str) -> dict[str, str]:
    """Return {section_id: body} resolved by matching heading titles.

    Headings whose title is not a known SECTION_TITLES entry are skipped —
    they cannot be addressed by ID and no check targets them.
    """
    matches = list(SKELETON_HEADING_RE.finditer(skel_text))
    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        section_id = _TITLE_TO_ID.get(m.group(2).strip())
        if section_id is None:
            continue
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(skel_text)
        sections[section_id] = skel_text[body_start:body_end]
    return sections


def _components_in_section(body: str) -> set[str]:
    """Extract CamelCase identifiers (length ≥ 4) from a section body."""
    return {m.group(1) for m in _CAMELCASE_RE.finditer(body) if len(m.group(1)) >= 4}


def check_isolated_components(skel_text: str) -> list[ConsistencyFinding]:
    """Components defined in view.components that never appear in state.flow/core.logic.

    A defined-but-unreferenced component is the canonical drift symptom:
    re-derivation added a UI piece without wiring its trigger or behavior.
    """
    sections = _split_sections(skel_text)
    defined: set[str] = set()
    for sid in _COMPONENT_DEFINITION_IDS:
        if sid in sections:
            defined |= _components_in_section(sections[sid])

    referenced: set[str] = set()
    for sid in _COMPONENT_REFERENCE_IDS:
        if sid in sections:
            referenced |= _components_in_section(sections[sid])

    findings: list[ConsistencyFinding] = []
    for name in sorted(defined - referenced):
        findings.append(
            ConsistencyFinding(
                severity="info",
                pattern="isolated-component",
                target=name,
                message=(
                    f"Component '{name}' defined in '{_COMPONENT_DEFINITION_IDS[0]}' "
                    f"but not referenced in {'/'.join(_COMPONENT_REFERENCE_IDS)} — "
                    "possible state-machine or pseudo-code wiring miss."
                ),
            )
        )
    return findings


def check_task_skeleton_references(
    tasks_text: str, skel_text: str
) -> list[ConsistencyFinding]:
    """Tasks with no §N reference and no view.components-component reference.

    A task that mentions neither a section number nor a known component is likely
    isolated from the skeleton — the implementer has nothing to anchor against.
    """
    sections = _split_sections(skel_text)
    known_components: set[str] = set()
    for sid in _COMPONENT_DEFINITION_IDS:
        if sid in sections:
            known_components |= _components_in_section(sections[sid])

    findings: list[ConsistencyFinding] = []
    for m in TASK_ROW_RE.finditer(tasks_text):
        task_id = m.group(1)
        description = m.group(4)

        has_section_ref = bool(_SECTION_REF_RE.search(description))
        mentioned_components = _components_in_section(description)
        has_component_ref = bool(mentioned_components & known_components)

        if not has_section_ref and not has_component_ref:
            findings.append(
                ConsistencyFinding(
                    severity="warn",
                    pattern="task-no-reference",
                    target=task_id,
                    message=(
                        f"Task '{task_id}' description has no §N reference and no "
                        "known view.components component name — implementer may lack anchor."
                    ),
                )
            )
    return findings


def run_all_checks(
    *, skeleton_text: str, tasks_text: str | None = None
) -> list[ConsistencyFinding]:
    """Run every cross-section consistency check and return aggregated findings.

    tasks_text is optional — task-level checks are skipped if absent (e.g. when
    the project has not reached the "planned" pipeline state yet).
    """
    findings: list[ConsistencyFinding] = []
    findings.extend(check_isolated_components(skeleton_text))
    # Distinguish "no tasks file" (None) from "empty tasks file" (""). The empty
    # case yields zero findings naturally, but running the check preserves the
    # type contract that callers expect.
    if tasks_text is not None:
        findings.extend(check_task_skeleton_references(tasks_text, skeleton_text))
    return findings
