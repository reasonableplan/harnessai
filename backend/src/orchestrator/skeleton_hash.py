"""Skeleton.md hash computation + plan comparison utilities.

Used by:
- ha-design commit / ha-redesign apply: write current hash to plan
- ha-plan / ha-build / ha-verify / ha-review / ha-redesign prepare: compare and warn
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from src.orchestrator.context import split_sections_by_id


def compute_section_hashes(skeleton_path: Path) -> dict[str, str]:
    """Per-section SHA-256 keyed by section ID (resolved via heading title).

    Same LF normalization as compute_skeleton_hash. Missing file → {}.
    Snapshot is written by ha-design commit / ha-redesign apply so that
    redesign can diff sections and derive stale done-tasks deterministically
    instead of relying on the impact agent's recall.
    """
    if not skeleton_path.exists():
        return {}
    text = skeleton_path.read_text(encoding="utf-8", errors="replace")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return {
        section_id: hashlib.sha256(body.encode("utf-8")).hexdigest()
        for section_id, body in split_sections_by_id(normalized).items()
    }


def compute_skeleton_hash(skeleton_path: Path) -> str:
    """SHA-256 hex of skeleton.md content. Normalizes line endings to
    LF before hashing so cross-platform (CRLF/LF) edits don't false-
    positive. Returns empty string if file missing."""
    if not skeleton_path.exists():
        return ""
    raw = skeleton_path.read_bytes()
    # Normalize CRLF/LF to LF for stable hashes across Windows/Unix
    normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(normalized).hexdigest()


@dataclass(frozen=True)
class SkeletonHashCheckResult:
    """Outcome of comparing plan.skeleton_hash to current skeleton.md."""

    plan_hash: str  # what plan claims (possibly empty for legacy)
    current_hash: str  # what skeleton.md is right now
    is_legacy: bool  # plan_hash is empty (no baseline)
    is_match: bool  # plan_hash == current_hash (False also when legacy)
    skeleton_missing: bool  # skeleton.md does not exist


def check_skeleton_hash(plan_hash: str, skeleton_path: Path) -> SkeletonHashCheckResult:
    """Compare a recorded plan.skeleton_hash to the live skeleton.md.

    Empty plan_hash means legacy plan — no comparison possible (returns
    is_legacy=True, is_match=False, but callers should not treat that
    as a mismatch).

    Missing skeleton.md returns skeleton_missing=True; callers usually
    skip the warning since the file might not exist yet (pre-design).
    """
    skeleton_missing = not skeleton_path.exists()
    current = compute_skeleton_hash(skeleton_path) if not skeleton_missing else ""
    is_legacy = not plan_hash
    is_match = bool(plan_hash) and (plan_hash == current) and not skeleton_missing
    return SkeletonHashCheckResult(
        plan_hash=plan_hash,
        current_hash=current,
        is_legacy=is_legacy,
        is_match=is_match,
        skeleton_missing=skeleton_missing,
    )
