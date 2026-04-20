#!/usr/bin/env bash
# HarnessAI installer (Unix / WSL / Git Bash).
#
# Usage:
#   ./install.sh              # interactive (shows diff if previously installed)
#   ./install.sh --force      # overwrite without confirmation
#   ./install.sh --dry-run    # print the plan, do not copy
#   CLAUDE_HOME=/custom/.claude ./install.sh    # custom target
#
# What it does:
#   1. harness/ → $CLAUDE_HOME/harness/
#   2. skills/{ha-*,_ha_shared} → $CLAUDE_HOME/skills/
#   3. writes file list + SHA256 to $CLAUDE_HOME/harness/.install-manifest.json
#   4. on re-run, detects changes via manifest diff

set -euo pipefail
# nounset (set -u) is on. Guard empty-array expansion with ${arr[@]+"${arr[@]}"}.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
MANIFEST_PATH="$CLAUDE_HOME/harness/.install-manifest.json"

FORCE=0
DRY_RUN=0
for arg in "$@"; do
    case "$arg" in
        --force)   FORCE=1 ;;
        --dry-run) DRY_RUN=1 ;;
        -h|--help)
            sed -n '/^# HarnessAI/,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "[FAIL] unknown option: $arg" >&2
            exit 2
            ;;
    esac
done

# Detect SHA-256 tool (Linux: sha256sum, macOS: shasum -a 256)
if command -v sha256sum >/dev/null 2>&1; then
    sha256_cmd() { sha256sum "$1" | awk '{print $1}'; }
elif command -v shasum >/dev/null 2>&1; then
    sha256_cmd() { shasum -a 256 "$1" | awk '{print $1}'; }
else
    echo "[FAIL] sha256sum or shasum is required" >&2
    exit 3
fi

# Build copy plan — (source_abs, target_rel) pairs
PLAN=()
add_plan() {
    local src_dir="$1"
    local target_prefix="$2"
    while IFS= read -r -d '' f; do
        local rel="${f#"$src_dir"/}"
        PLAN+=("$f:$target_prefix/$rel")
    done < <(find "$src_dir" -type f -not -path '*/__pycache__/*' -not -name '*.pyc' -print0)
}

add_plan "$REPO_ROOT/harness" "harness"
for d in "$REPO_ROOT/skills"/ha-* "$REPO_ROOT/skills/_ha_shared"; do
    [ -d "$d" ] || continue
    add_plan "$d" "skills/$(basename "$d")"
done

echo "HarnessAI install plan"
echo "  repo:   $REPO_ROOT"
echo "  target: $CLAUDE_HOME"
echo "  files:  ${#PLAN[@]}"
echo ""

# Read existing manifest to compute diff.
# Each manifest entry is a single JSON line with target + sha256:
#   { "target": "harness/foo.md", "sha256": "abc123..." },
declare -A OLD_HASHES=()
if [ -f "$MANIFEST_PATH" ]; then
    while IFS=$'\t' read -r tgt hash; do
        [ -n "$tgt" ] && [ -n "$hash" ] && OLD_HASHES["$tgt"]="$hash"
    done < <(sed -n 's/.*"target": *"\([^"]*\)".*"sha256": *"\([0-9a-f]*\)".*/\1\t\2/p' "$MANIFEST_PATH")
fi

# Classify changes
ADDED=()
MODIFIED=()
UNCHANGED=()
for entry in ${PLAN[@]+"${PLAN[@]}"}; do
    src="${entry%%:*}"
    tgt_rel="${entry#*:}"
    new_hash=$(sha256_cmd "$src")
    old_hash="${OLD_HASHES[$tgt_rel]:-}"
    if [ -z "$old_hash" ]; then
        ADDED+=("$tgt_rel")
    elif [ "$old_hash" != "$new_hash" ]; then
        MODIFIED+=("$tgt_rel")
    else
        UNCHANGED+=("$tgt_rel")
    fi
done

# Files listed in the old manifest but missing from this run's plan
# (i.e. removed from the repo since the previous install).
REMOVED=()
declare -A NEW_TARGETS=()
for entry in ${PLAN[@]+"${PLAN[@]}"}; do
    NEW_TARGETS["${entry#*:}"]=1
done
for t in "${!OLD_HASHES[@]}"; do
    [ -z "${NEW_TARGETS[$t]:-}" ] && REMOVED+=("$t")
done

echo "Change summary:"
echo "  added:     ${#ADDED[@]}"
echo "  modified:  ${#MODIFIED[@]}"
echo "  unchanged: ${#UNCHANGED[@]}"
echo "  removed:   ${#REMOVED[@]}"
echo ""

if [ "${#MODIFIED[@]}" -gt 0 ] && [ "$FORCE" -eq 0 ] && [ "$DRY_RUN" -eq 0 ]; then
    echo "Will modify:"
    for f in ${MODIFIED[@]+"${MODIFIED[@]}"}; do echo "  M $f"; done
    echo ""
    if [ "${#REMOVED[@]}" -gt 0 ]; then
        echo "Will remove (absent from repo — manifest entry kept):"
        for f in ${REMOVED[@]+"${REMOVED[@]}"}; do echo "  D $f"; done
        echo ""
    fi
    read -r -p "Continue? [y/N] " reply
    case "$reply" in
        [yY]|[yY][eE][sS]) ;;
        *) echo "Aborted."; exit 0 ;;
    esac
fi

if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] no files copied."
    exit 0
fi

# Copy + write manifest
mkdir -p "$CLAUDE_HOME/harness" "$CLAUDE_HOME/skills"
NEW_MANIFEST=$(mktemp)
{
    echo "{"
    echo "  \"version\": \"0.1.0\","
    echo "  \"installed_at\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\","
    printf '  "source": "%s",\n' "$REPO_ROOT"
    echo "  \"files\": ["
} > "$NEW_MANIFEST"

count=0
total=${#PLAN[@]}
for entry in ${PLAN[@]+"${PLAN[@]}"}; do
    src="${entry%%:*}"
    tgt_rel="${entry#*:}"
    tgt_abs="$CLAUDE_HOME/$tgt_rel"
    mkdir -p "$(dirname "$tgt_abs")"
    cp "$src" "$tgt_abs"
    hash=$(sha256_cmd "$src")
    count=$((count + 1))
    sep=","
    [ "$count" -eq "$total" ] && sep=""
    printf '    { "target": "%s", "sha256": "%s" }%s\n' "$tgt_rel" "$hash" "$sep" >> "$NEW_MANIFEST"
done

{
    echo "  ]"
    echo "}"
} >> "$NEW_MANIFEST"

mv "$NEW_MANIFEST" "$MANIFEST_PATH"

echo "[OK] install complete"
echo "  installed: $count files"
echo "  manifest:  $MANIFEST_PATH"
echo ""
echo "Set this env var (add to your shell profile):"
echo "  export HARNESS_AI_HOME=\"$REPO_ROOT\""
echo ""
echo "Next: open a fresh Claude Code session and run '/ha-init'."
