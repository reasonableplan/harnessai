"""capabilities — axes-driven capability inference.

Derives ``has.*`` atoms from user-intent axes (not profile declarations).
Profile-declared capabilities are handled by ProfileLoader.compute_has_keys.
"""

from __future__ import annotations

from src.orchestrator.plan_manager import ScaleAxes

# ---------------------------------------------------------------------------
# Single source of truth for known has.* atoms across the codebase.
#
# Maintenance contract (alphabetical order enforced by convention):
#   1. Add the new atom here (keep alphabetical).
#   2. Update at least one profile's provides_capabilities OR add a
#      derive_axes_capabilities mapping that emits it.
#   3. Update _HAS_KEY_PROVIDERS in consistency.py if backend profiles
#      can provide it (omit if intentionally untracked — see external_deps).
#   4. Reference the atom from a fragment's required_when expression.
#
# Tests in test_capability_atoms_consistency.py enforce these invariants.
#
# NOTE: external_deps is intentionally listed here but has no entry in
# _HAS_KEY_PROVIDERS — it is a documented gap awaiting a concrete provider.
# ---------------------------------------------------------------------------
KNOWN_CAPABILITY_ATOMS: frozenset[str] = frozenset(
    {
        "build_config",
        "cli_entrypoint",
        "complex_state",
        "env_config",
        "external_deps",  # gap: no profile provides this yet (intentional)
        "http_server",
        "ipc",
        "lifecycle",
        "navigation",
        "production_concerns",
        "sdk_surface",
        "storage",
        "ui",
        "users",
    }
)


def validate_capability_set(atoms: frozenset[str], context: str) -> None:
    """Raise ValueError if any atom is not in KNOWN_CAPABILITY_ATOMS.

    context: human label for the error message
             (e.g. "provides_capabilities of fastapi.md").

    This is infrastructure only — callers are responsible for deciding
    when to invoke it.  Step D of the reinforcement plan wires it into
    ProfileLoader.load().
    """
    unknown = atoms - KNOWN_CAPABILITY_ATOMS
    if unknown:
        raise ValueError(
            f"{context}: unknown capability atoms {sorted(unknown)} — "
            f"add to KNOWN_CAPABILITY_ATOMS or fix typo. "
            f"Known: {sorted(KNOWN_CAPABILITY_ATOMS)}"
        )


def derive_axes_capabilities(axes: ScaleAxes) -> frozenset[str]:
    """Capabilities inferred from user-intent axes (not profile declared).

    Phase 1 mapping (intentionally minimal — extend as concrete signals
    accumulate):
        data_sensitivity in [pii, payment] → users
        monetization in [subscription, payment] → users

    Rationale: PII / payment implies user identification != anonymous,
    so has.users should activate even if no auth-providing profile is
    present (legacy mobile-only case where user explicitly stated PII).

    Other axes (team_size, availability, lifecycle, user_scale) do not
    map to has.* atoms — they drive fragment activation through scale_*
    tokens already.
    """
    capabilities: set[str] = set()
    if axes.data_sensitivity in ("pii", "payment"):
        capabilities.add("users")
    if axes.monetization in ("subscription", "payment"):
        capabilities.add("users")
    return frozenset(capabilities)
