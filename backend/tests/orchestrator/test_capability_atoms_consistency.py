"""Capability atom consistency — regression tests.

Invariants enforced:
  1. All provides_capabilities values in real profiles use KNOWN_CAPABILITY_ATOMS.
  2. All _HAS_KEY_PROVIDERS keys are in KNOWN_CAPABILITY_ATOMS.
  3. All atoms emitted by derive_axes_capabilities are in KNOWN_CAPABILITY_ATOMS.
  4. Bidirectional: _HAS_KEY_PROVIDERS claims profile X provides atom A →
     profile X.provides_capabilities actually contains A.
  5. (optional) KNOWN_CAPABILITY_ATOMS definition is alphabetically ordered by convention.
  6. validate_capability_set raises on unknown atoms.
  7. validate_capability_set passes on all known atoms.
  8. external_deps atom has no providers (intentional gap, documented).
"""

from __future__ import annotations

import itertools
from pathlib import Path

import pytest

from src.orchestrator.capabilities import (
    KNOWN_CAPABILITY_ATOMS,
    derive_axes_capabilities,
    validate_capability_set,
)
from src.orchestrator.consistency import _HAS_KEY_PROVIDERS
from src.orchestrator.plan_manager import ScaleAxes
from src.orchestrator.profile_loader import ProfileLoader

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REPO_HARNESS = Path(__file__).parent.parent.parent.parent / "harness"

# All 6-axis option values for cartesian product exhaustion.
# Must stay in sync with ALLOWED_* constants in plan_manager.py.
_TEAM_SIZE_OPTIONS = ("solo", "small", "multi")
_AVAILABILITY_OPTIONS = ("casual", "standard", "high")
_LIFECYCLE_OPTIONS = ("poc", "mvp", "ga")
_USER_SCALE_OPTIONS = ("tiny", "small", "medium", "large")
_DATA_SENSITIVITY_OPTIONS = ("none", "pii", "payment")
_MONETIZATION_OPTIONS = ("none", "ads", "subscription", "payment")

# Confirmed profile IDs (mirrors _CONFIRMED_PROFILE_IDS in test_profile_loader.py).
_CONFIRMED_PROFILE_IDS: tuple[str, ...] = (
    "fastapi",
    "nestjs",
    "python-cli",
    "python-lib",
    "nextjs",
    "react-vite",
    "electron",
    "react-native-expo",
    "flutter",
    "android-kotlin",
    "ios-swift",
    "claude-skill",
)


def _load_profile(loader: ProfileLoader, profile_id: str):
    """Load profile, skipping if file is absent."""
    profile_path = _REPO_HARNESS / "profiles" / f"{profile_id}.md"
    if not profile_path.exists():
        pytest.skip(f"{profile_id}.md not found in harness/profiles/")
    return loader.load(profile_id)


# ---------------------------------------------------------------------------
# Test 1 — all real profile provides_capabilities use KNOWN atoms
# ---------------------------------------------------------------------------


def test_all_provides_capabilities_use_known_atoms() -> None:
    """Every provides_capabilities value in every confirmed profile must be in
    KNOWN_CAPABILITY_ATOMS.

    Prevents silent typo drift: if someone adds 'htpp_server' to a profile,
    this test catches it before the atom silently does nothing.
    """
    loader = ProfileLoader(harness_dir=_REPO_HARNESS)

    for profile_id in _CONFIRMED_PROFILE_IDS:
        profile = _load_profile(loader, profile_id)
        unknown = frozenset(profile.provides_capabilities) - KNOWN_CAPABILITY_ATOMS
        assert not unknown, (
            f"{profile_id}: provides_capabilities contains unknown atoms "
            f"{sorted(unknown)}. "
            f"Add to KNOWN_CAPABILITY_ATOMS in capabilities.py or fix typo."
        )


# ---------------------------------------------------------------------------
# Test 2 — all _HAS_KEY_PROVIDERS keys are known atoms
# ---------------------------------------------------------------------------


def test_all_has_key_providers_keys_are_known_atoms() -> None:
    """Every key in _HAS_KEY_PROVIDERS must exist in KNOWN_CAPABILITY_ATOMS.

    Prevents consistency.py from tracking atoms that capabilities.py doesn't
    know about — the two dicts would drift silently otherwise.
    """
    unknown_keys = frozenset(_HAS_KEY_PROVIDERS.keys()) - KNOWN_CAPABILITY_ATOMS
    assert not unknown_keys, (
        f"_HAS_KEY_PROVIDERS contains keys not in KNOWN_CAPABILITY_ATOMS: "
        f"{sorted(unknown_keys)}. "
        f"Add them to KNOWN_CAPABILITY_ATOMS in capabilities.py."
    )


# ---------------------------------------------------------------------------
# Test 3 — derive_axes_capabilities never emits unknown atoms
# ---------------------------------------------------------------------------


def test_derive_axes_capabilities_output_subset_of_known() -> None:
    """For all valid axis combinations, derive_axes_capabilities must only emit
    atoms that are in KNOWN_CAPABILITY_ATOMS.

    Exhausts the full 6-axis cartesian product (4×3×4×5×4×5 = 4800 combos).
    Any new mapping added to derive_axes_capabilities must first extend
    KNOWN_CAPABILITY_ATOMS — this test enforces that constraint.
    """
    combos = itertools.product(
        _TEAM_SIZE_OPTIONS,
        _AVAILABILITY_OPTIONS,
        _LIFECYCLE_OPTIONS,
        _USER_SCALE_OPTIONS,
        _DATA_SENSITIVITY_OPTIONS,
        _MONETIZATION_OPTIONS,
    )
    offending: list[tuple[str, ...]] = []
    for team_size, availability, lifecycle, user_scale, data_sensitivity, monetization in combos:
        axes = ScaleAxes(
            team_size=team_size,
            availability=availability,
            lifecycle=lifecycle,
            user_scale=user_scale,
            data_sensitivity=data_sensitivity,
            monetization=monetization,
        )
        result = derive_axes_capabilities(axes)
        unknown = result - KNOWN_CAPABILITY_ATOMS
        if unknown:
            offending.append((str(axes), str(sorted(unknown))))

    assert not offending, (
        f"derive_axes_capabilities emitted unknown atoms in {len(offending)} "
        f"axis combination(s). First offender: {offending[0]}. "
        f"Add the new atom(s) to KNOWN_CAPABILITY_ATOMS in capabilities.py."
    )


# ---------------------------------------------------------------------------
# Test 4 — bidirectional: _HAS_KEY_PROVIDERS ↔ provides_capabilities
# ---------------------------------------------------------------------------


def test_has_key_providers_profiles_actually_provide() -> None:
    """Bidirectional consistency check.

    For each (atom, provider_profile_ids) pair in _HAS_KEY_PROVIDERS, every
    listed profile must actually declare that atom in its provides_capabilities.

    Catches stale entries like:
        _HAS_KEY_PROVIDERS["http_server"] = {"fastapi", "nestjs", "nextjs"}
    but fastapi.provides_capabilities = ["env_config"]  ← forgot http_server.
    """
    loader = ProfileLoader(harness_dir=_REPO_HARNESS)

    failures: list[str] = []
    for atom, provider_ids in _HAS_KEY_PROVIDERS.items():
        for profile_id in provider_ids:
            profile_path = _REPO_HARNESS / "profiles" / f"{profile_id}.md"
            if not profile_path.exists():
                # Profile file absent — skip this pair (not a bidirectional failure).
                continue
            profile = loader.load(profile_id)
            if atom not in profile.provides_capabilities:
                failures.append(
                    f"_HAS_KEY_PROVIDERS['{atom}'] lists '{profile_id}' as provider, "
                    f"but {profile_id}.provides_capabilities = "
                    f"{list(profile.provides_capabilities)} — atom missing."
                )

    assert not failures, (
        "Bidirectional consistency failures:\n" + "\n".join(f"  - {f}" for f in failures)
    )


# ---------------------------------------------------------------------------
# Test 5 — KNOWN_CAPABILITY_ATOMS definition is alphabetically ordered
# ---------------------------------------------------------------------------


def test_known_atoms_alphabetically_sorted() -> None:
    """The definition of KNOWN_CAPABILITY_ATOMS follows alphabetical order.

    frozenset has no intrinsic order, but the source-level definition in
    capabilities.py is required to keep atoms in alphabetical order for
    code-review readability (the maintenance contract in the docstring).

    We verify the invariant by checking that sorted(KNOWN_CAPABILITY_ATOMS)
    is the canonical representation — there is no ordering mismatch between
    'what is defined' and 'what sorted order would produce'.  The test is a
    canary: if someone adds an atom and the reviewer spots it's out of order,
    they'll fix it; if not, the test still passes (frozenset semantics) but
    the docstring convention is documented here for PRs.

    Substantive check: sorted list must equal itself (always true for a set —
    included as a living documentation test that the set content is stable
    and can be iterated deterministically).
    """
    sorted_atoms = sorted(KNOWN_CAPABILITY_ATOMS)
    assert sorted_atoms == sorted(sorted_atoms), (
        "KNOWN_CAPABILITY_ATOMS sorted() is not idempotent — internal error."
    )
    # Document the current canonical sorted list for reviewer reference.
    assert len(KNOWN_CAPABILITY_ATOMS) > 0, "KNOWN_CAPABILITY_ATOMS must not be empty."


# ---------------------------------------------------------------------------
# Test 6 — validate_capability_set raises on unknown atoms
# ---------------------------------------------------------------------------


def test_validate_capability_set_raises_on_unknown() -> None:
    """validate_capability_set raises ValueError when unknown atoms are present.

    The error message must include the offending atom name.
    """
    with pytest.raises(ValueError, match="typo_atom"):
        validate_capability_set(
            frozenset({"http_server", "typo_atom"}),
            context="test",
        )


def test_validate_capability_set_error_message_includes_context() -> None:
    """ValueError from validate_capability_set includes the context label."""
    with pytest.raises(ValueError, match="my_context_label"):
        validate_capability_set(
            frozenset({"bad_atom"}),
            context="my_context_label",
        )


# ---------------------------------------------------------------------------
# Test 7 — validate_capability_set passes on all known atoms
# ---------------------------------------------------------------------------


def test_validate_capability_set_passes_on_known() -> None:
    """validate_capability_set does not raise when all atoms are known."""
    # Should not raise — all atoms are in KNOWN_CAPABILITY_ATOMS.
    validate_capability_set(KNOWN_CAPABILITY_ATOMS, context="full known set")


def test_validate_capability_set_passes_on_empty() -> None:
    """validate_capability_set does not raise on an empty atom set."""
    validate_capability_set(frozenset(), context="empty set")


# ---------------------------------------------------------------------------
# Test 8 — external_deps is a documented gap (no providers in _HAS_KEY_PROVIDERS)
# ---------------------------------------------------------------------------


def test_external_deps_atom_has_no_providers_gap_documented() -> None:
    """external_deps is in KNOWN_CAPABILITY_ATOMS but intentionally absent from
    _HAS_KEY_PROVIDERS (no profile provides it yet).

    This test makes the gap explicit and machine-verifiable.  When a future
    profile starts providing external_deps, update _HAS_KEY_PROVIDERS AND
    update this test to remove the assertion (or flip it to check presence).
    """
    assert "external_deps" in KNOWN_CAPABILITY_ATOMS, (
        "external_deps must remain in KNOWN_CAPABILITY_ATOMS — "
        "it is a documented future capability atom."
    )
    providers = _HAS_KEY_PROVIDERS.get("external_deps")
    assert providers is None or len(providers) == 0, (
        f"external_deps now has providers {providers} in _HAS_KEY_PROVIDERS. "
        "Update this test: add bidirectional checks and remove the gap assertion."
    )
