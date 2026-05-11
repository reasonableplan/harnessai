"""Show how 6-axis answers reshape the skeleton.

Renders the same demo used in README "What it actually adapts":
two ScaleAxes on the python-cli profile, prints active section
counts and the diff. Used for Show HN / GIF / sanity check.

Run from repo root:
    cd backend && uv run python ../scripts/show_adapt_diff.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from src.orchestrator.plan_manager import ScaleAxes  # noqa: E402
from src.orchestrator.profile_loader import ProfileLoader  # noqa: E402

HARNESS_DIR = REPO_ROOT / "harness"
FRAGMENTS_DIR = HARNESS_DIR / "templates" / "skeleton"


def main() -> int:
    loader = ProfileLoader(harness_dir=HARNESS_DIR)
    profile = loader.load("python-cli")

    a = ScaleAxes(data_sensitivity="pii", lifecycle="mvp", availability="standard")
    b = ScaleAxes(data_sensitivity="none", lifecycle="poc", availability="casual")

    active_a, _trace_a = loader.compute_active_sections(a, [profile], FRAGMENTS_DIR)
    active_b, _trace_b = loader.compute_active_sections(b, [profile], FRAGMENTS_DIR)
    sec_a = set(active_a)
    sec_b = set(active_b)

    print(f"A  pii + mvp + standard  ->  {len(sec_a)} sections")
    print(f"B  none + poc + casual   ->  {len(sec_b)} sections")
    print(f"diff (A only)            ->  {sorted(sec_a - sec_b)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
