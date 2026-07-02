"""Regression tests for the standalone `harness` CLI expression validator.

Focus: `_validate_required_when_expression` must accept parenthesized
required_when expressions (the backend scale_expression parser handles them,
so the CLI validator must not reject them) while still rejecting invalid
atoms/axes and structurally broken parentheses.

The `harness` bin is a script (no .py suffix) not under normal import, so it
is loaded via importlib. Loading executes only module-level definitions
(imports + constants + HARNESS_ROOT resolution) — no side effects.
"""

from __future__ import annotations

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

_BIN = Path(__file__).resolve().parents[3] / "harness" / "bin" / "harness"


def _load_harness_module():
    # Extensionless script → specify a source loader explicitly.
    loader = SourceFileLoader("harness_cli", str(_BIN))
    spec = importlib.util.spec_from_loader("harness_cli", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    # @dataclass at module top-level resolves cls.__module__ via sys.modules —
    # register before exec so the decorators can find the module.
    sys.modules["harness_cli"] = mod
    loader.exec_module(mod)
    return mod


harness_cli = _load_harness_module()
_validate = harness_cli._validate_required_when_expression


# ── parentheses now accepted (the #1 false-positive fix) ─────────────────

_ENVIRONMENTS_EXPR = (
    "(has.http_server or has.ui or has.navigation or has.cli_entrypoint) "
    "and (lifecycle in [mvp, ga] or availability in [standard, high])"
)


def test_parenthesized_expression_accepted() -> None:
    assert _validate(_ENVIRONMENTS_EXPR) is None


def test_simple_parens_accepted() -> None:
    assert _validate("(has.storage or has.users) and scale.small_or_larger") is None


# ── still valid without parens (no regression) ──────────────────────────


@pytest.mark.parametrize(
    "expr",
    [
        "always",
        "has.storage",
        "scale.medium_or_larger",
        "has.http_server or has.ui",
        "lifecycle in [mvp, ga]",
        "data_sensitivity == pii",
        "has.storage and scale.small_or_larger",
    ],
)
def test_valid_expressions_pass(expr: str) -> None:
    assert _validate(expr) is None


# ── invalid content still rejected ──────────────────────────────────────


def test_unbalanced_parens_rejected() -> None:
    err = _validate("(has.storage or has.users")
    assert err is not None
    assert "괄호" in err or "(" in err


def test_unknown_atom_rejected_inside_parens() -> None:
    err = _validate("(has.bogus_atom or has.ui)")
    assert err is not None


def test_unknown_axis_rejected() -> None:
    err = _validate("bogus_axis == pii")
    assert err is not None
    assert "axis" in err.lower()


def test_empty_expression_rejected() -> None:
    assert _validate("   ") is not None
