"""consistency — profile consistency violation detection.

Detects activation triggers that no loaded profile can fulfill.
Used by ha-design and ha-review to surface advisory warnings when a
section requires a has.* capability that no present profile provides.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.orchestrator.scale_expression import EvalContext, ExpressionParseError
from src.orchestrator.scale_expression import evaluate as scale_evaluate

# Imported lazily at call time to avoid circular import:
# consistency → profile_loader → consistency would be circular.
# The Profile type is only used in the function signature; we use
# TYPE_CHECKING to keep the annotation without triggering the cycle.
if TYPE_CHECKING:
    from src.orchestrator.profile_loader import Profile


# Profile IDs that provide each has.* capability. Used by
# find_consistency_violations() to detect "section requires backend
# capability X but no profile provides X".
#
# Order doesn't matter inside the frozenset. New backend profiles
# (e.g. django, axum) should be added here when introduced.
_HAS_KEY_PROVIDERS: dict[str, frozenset[str]] = {
    # nextjs added: RSC + Server Actions + Route Handlers provide an HTTP surface.
    "http_server": frozenset({"fastapi", "nestjs", "nextjs"}),
    "cli_entrypoint": frozenset({"python-cli"}),
    # electron added: main-process IPC bridge (contextBridge / ipcMain).
    "ipc": frozenset({"electron"}),
    "sdk_surface": frozenset({"python-lib"}),
    # ui / storage / production_concerns / etc. — multiple profile types
    # can provide these (mobile is also "ui"); not a useful consistency
    # signal, so we leave them unmapped.
}


@dataclass(frozen=True)
class ConsistencyViolation:
    """A section's activation expression requires a has.* atom that no
    loaded profile provides. Surfaced as advisory — user may still
    proceed if they have an external provider (e.g. managed backend)."""

    section_id: str
    trigger_expression: str  # the required_when expression
    missing_atom: str        # the has.* atom that's unmet (e.g. "http_server")
    expected_providers: tuple[str, ...]  # profile IDs that *could* provide it


def find_consistency_violations(
    active_with_trace: dict[str, str],
    profiles: list[Profile],
    external_capabilities: frozenset[str] | None = None,
) -> list[ConsistencyViolation]:
    """Detect activation triggers that no loaded profile can fulfill.

    For each (section, required_when) in trace, evaluate the expression
    using scale_expression.evaluate with a context where only the mapped
    atoms are considered "provided". If the expression evaluates to False
    when all unmapped atoms are treated as True (only mapped-but-absent atoms
    are False), then the section cannot be satisfied by the current profile set.

    Uses scale_expression.evaluate for correct OR/AND semantics — a section
    with "has.http_server or has.ui" is NOT a violation if has.ui is provided,
    even though has.http_server is missing.

    Atoms with empty provider sets in _HAS_KEY_PROVIDERS are skipped (not a
    consistency signal — avoids false positives for provider-less capabilities).

    external_capabilities: Group 1-D — user-declared has.* atoms from BaaS /
    external services (e.g. Firebase). Atoms listed here are treated as
    satisfied regardless of which profiles are loaded — this prevents
    false-positive violations for the common BaaS case where no backend
    profile is present but the service is provided externally.
    None is treated as an empty set (backward-compatible).

    Sorted by (section_id, missing_atom) for deterministic output.
    """
    # Import here to avoid circular dependency at module load time.
    from src.orchestrator.plan_manager import ScaleAxes  # noqa: PLC0415

    present_profile_ids: frozenset[str] = frozenset(p.id for p in profiles)
    external_caps: frozenset[str] = external_capabilities or frozenset()
    _HAS_ATOM_RE = re.compile(r"\bhas\.(\w+)\b")

    violations: list[ConsistencyViolation] = []
    for section_id, expression in active_with_trace.items():
        # Build a has_keys set where:
        # - atoms mapped in _HAS_KEY_PROVIDERS with providers: True only if a provider is present
        #   OR the atom is declared in external_capabilities (BaaS escape hatch)
        # - atoms mapped in _HAS_KEY_PROVIDERS with empty providers: always True (not a signal)
        # - atoms NOT in _HAS_KEY_PROVIDERS (unmapped): always True (out of scope for checking)
        has_keys_for_check: set[str] = set()
        for atom_key, providers in _HAS_KEY_PROVIDERS.items():
            if not providers:
                # Empty provider set — not a consistency signal, treat as satisfied
                has_keys_for_check.add(atom_key)
            elif (providers & present_profile_ids) or (atom_key in external_caps):
                # At least one provider is present, OR user declared it via external_capabilities
                has_keys_for_check.add(atom_key)
            # else: atom is mapped, no provider present, not in external_caps — leave out

        # Add all has.* atoms found in this expression that are NOT in _HAS_KEY_PROVIDERS.
        # Unmapped atoms have no known provider set → not a consistency signal → always True.
        for atom_key in _HAS_ATOM_RE.findall(expression):
            if atom_key not in _HAS_KEY_PROVIDERS:
                has_keys_for_check.add(atom_key)

        # Use a neutral ScaleAxes for expression evaluation — axis comparisons
        # are not what we're checking here.
        ctx = EvalContext(
            axes=ScaleAxes(),
            has_keys=frozenset(has_keys_for_check),
            scale_tokens=frozenset(),
        )

        try:
            result = scale_evaluate(expression, ctx)
        except ExpressionParseError:
            # Already handled conservatively in compute_active_sections; skip here.
            continue

        if not result:
            # The expression cannot be satisfied by current profiles (nor external_caps).
            # Find which mapped atoms are missing (for reporting) — exclude atoms that
            # were declared in external_capabilities (they are satisfied externally).
            missing_atoms = sorted(
                atom_key
                for atom_key, providers in _HAS_KEY_PROVIDERS.items()
                if providers
                and not (providers & present_profile_ids)
                and atom_key not in external_caps
                and f"has.{atom_key}" in expression
            )
            for missing_atom in missing_atoms:
                providers_for_atom = _HAS_KEY_PROVIDERS[missing_atom]
                violations.append(
                    ConsistencyViolation(
                        section_id=section_id,
                        trigger_expression=expression,
                        missing_atom=missing_atom,
                        expected_providers=tuple(sorted(providers_for_atom)),
                    )
                )

    violations.sort(key=lambda v: (v.section_id, v.missing_atom))
    return violations
