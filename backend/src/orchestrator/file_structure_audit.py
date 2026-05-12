"""File structure drift audit — profile.file_structure vs actual directories.

Used by `harness integrity` to emit advisory WARNs when a project's directory
tree has diverged from what the profile declares in its `file_structure` field.

Design:
- WARN only (advisory) — never BLOCK.  Intentional expansions are allowed.
- Directories only — file drift is not tracked (too noisy).
- Skip standard noise dirs: node_modules, __pycache__, .git, .next, dist, etc.
- Top-3 depth limit (configurable) to avoid deep build-artefact noise.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.orchestrator.profile_loader import Profile

# Directories that should never appear in the "actual" scan — build artefacts,
# VCS dirs, test output dirs, etc.
_SKIP_DIRS: frozenset[str] = frozenset(
    {
        "node_modules",
        "__pycache__",
        ".git",
        ".next",
        ".expo",
        "dist",
        "build",
        ".build",
        "out",
        ".cache",
        ".turbo",
        ".gradle",
        ".idea",
        ".vscode",
        "__tests__",
        "tests",
        ".pytest_cache",
        "coverage",
        ".nyc_output",
        "target",  # Rust/Java build output
        "venv",
        ".venv",
        "env",
        ".env",  # Python virtualenv dirs
    }
)

# Inline comment pattern — strip "# ..." from the end of a tree line
_COMMENT_RE = re.compile(r"\s+#.*$")


@dataclass(frozen=True)
class DriftResult:
    """Result of comparing declared vs actual directory sets."""

    extras: list[str]   # dirs in actual but NOT in declared (intentional expansions)
    missing: list[str]  # dirs in declared but NOT in actual
    match: bool         # True when both extras and missing are empty


def parse_profile_file_structure(profile: Profile) -> set[str]:
    """Parse profile.file_structure (indented tree string) → set of relative dir paths.

    Only directory entries are returned (lines ending with '/' or having
    children in the indented tree).  Files are excluded — we audit directory
    drift only.

    Inline comments ('# ...') are stripped before parsing.
    Template placeholders like <domain> are preserved as-is (they will not
    match actual filesystem dirs and will appear in `missing` — expected).

    Example input (file_structure value):
        mobile/
          app/
            (auth)/
          src/
            shared/
              components/

    Example output:
        {'mobile/', 'mobile/app/', 'mobile/app/(auth)/', 'mobile/src/',
         'mobile/src/shared/', 'mobile/src/shared/components/'}
    """
    raw = profile.file_structure
    if not raw or not raw.strip():
        return set()

    return _parse_tree_to_dirs(raw)


def _parse_tree_to_dirs(tree_text: str) -> set[str]:
    """Convert indented tree text to a set of directory relative paths.

    Algorithm: maintain a stack of (indent_level, path_prefix) pairs.
    A line is a directory if it ends with '/' OR it has child lines
    at greater indentation.  We do a two-pass approach:
      pass 1 — collect all lines with their indent + name
      pass 2 — a line is a dir if the *next* line has strictly greater indent

    Template patterns (<domain>, <Domain>, etc.) are kept verbatim.
    """
    lines_raw: list[tuple[int, str]] = []  # (indent, name)
    for raw_line in tree_text.splitlines():
        stripped = raw_line.rstrip()
        if not stripped:
            continue
        # Strip inline comment
        stripped = _COMMENT_RE.sub("", stripped).rstrip()
        if not stripped:
            continue
        name = stripped.lstrip()
        if not name or name.startswith("#"):
            continue
        indent = len(stripped) - len(name)
        lines_raw.append((indent, name))

    if not lines_raw:
        return set()

    dirs: set[str] = set()
    stack: list[tuple[int, str]] = []  # (indent, full_path_so_far)

    for idx, (indent, name) in enumerate(lines_raw):
        # Pop stack entries whose indent >= current indent
        while stack and stack[-1][0] >= indent:
            stack.pop()

        prefix = stack[-1][1] if stack else ""
        full = prefix + name

        # Determine if this entry is a directory:
        #   - explicitly ends with '/'
        #   - next entry has strictly greater indent (it has children)
        is_dir = name.endswith("/")
        if not is_dir and idx + 1 < len(lines_raw):
            next_indent = lines_raw[idx + 1][0]
            if next_indent > indent:
                is_dir = True

        if is_dir:
            # Normalise: ensure trailing slash
            dir_path = full if full.endswith("/") else full + "/"
            dirs.add(dir_path)
            # Push onto stack (using dir_path so children get proper prefix)
            stack.append((indent, dir_path))
        else:
            # File — push with full path (no trailing slash) for child resolution,
            # but files are never added to dirs set
            stack.append((indent, full))

    return dirs


def scan_project_directories(
    project_root: Path,
    profile_path: str,
    top_n: int = 3,
) -> set[str]:
    """Scan actual directories in the project up to `top_n` depth.

    `profile_path` is the relative path under `project_root` where this
    profile applies (e.g. '.' for root, 'apps/mobile/' for monorepo sub-app).
    Entries in `_SKIP_DIRS` are excluded.

    Returns a set of relative dir paths (with trailing '/') relative to
    `scan_root` (= project_root / profile_path).

    Depth is measured from scan_root.  A directory at scan_root/a/b/c/ is at
    depth 3 and is included when top_n >= 3.
    """
    # Resolve scan root
    if profile_path in (".", ""):
        scan_root = project_root.resolve()
    else:
        scan_root = (project_root / profile_path.rstrip("/")).resolve()

    if not scan_root.exists() or not scan_root.is_dir():
        return set()

    result: set[str] = set()
    _collect_dirs(scan_root, scan_root, current_depth=1, top_n=top_n, out=result)
    return result


def _collect_dirs(
    scan_root: Path,
    current: Path,
    current_depth: int,
    top_n: int,
    out: set[str],
) -> None:
    """Recursively collect directory paths relative to scan_root."""
    if current_depth > top_n:
        return
    try:
        entries = list(current.iterdir())
    except PermissionError:
        return
    for entry in entries:
        if not entry.is_dir():
            continue
        if entry.name in _SKIP_DIRS or entry.name.startswith("."):
            continue
        rel = entry.relative_to(scan_root)
        # Use posix separators, trailing slash
        rel_str = rel.as_posix() + "/"
        out.add(rel_str)
        _collect_dirs(scan_root, entry, current_depth + 1, top_n, out)


def compute_drift(declared: set[str], actual: set[str]) -> DriftResult:
    """Compare declared (from profile) vs actual (from filesystem) dir sets.

    extras  = actual - declared  (added beyond profile spec)
    missing = declared - actual  (declared but not present)
    match   = True when both are empty
    """
    # Exclude template placeholder dirs from missing check — <domain>/ etc.
    # They will never exist on disk and are intentional variable names.
    declared_concrete = {d for d in declared if "<" not in d}

    extras = sorted(actual - declared)
    missing = sorted(declared_concrete - actual)
    return DriftResult(
        extras=extras,
        missing=missing,
        match=(not extras and not missing),
    )
