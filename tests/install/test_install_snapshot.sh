#!/usr/bin/env bash
# install.sh 스냅샷 테스트 — fresh / re-run (no changes) / source modified 3 시나리오.
#
# 실행:
#   ./tests/install/test_install_snapshot.sh
#
# 성공 시 exit 0. 실패 시 exit 1 + 실패 케이스 출력.

set -eo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

FAILED=0
PASSED=0

assert() {
    local desc="$1"
    local cond="$2"
    if eval "$cond"; then
        PASSED=$((PASSED + 1))
        echo "  PASS: $desc"
    else
        FAILED=$((FAILED + 1))
        echo "  FAIL: $desc"
        echo "        cond: $cond"
    fi
}

TMP_HOME=$(mktemp -d)
trap "rm -rf '$TMP_HOME'" EXIT
TARGET="$TMP_HOME/.claude"
MANIFEST="$TARGET/harness/.install-manifest.json"

# 헬퍼: install 출력에서 "X: N" 형식 카운트 추출
count_field() {
    local field="$1"
    local output="$2"
    echo "$output" | grep -E "^  $field:" | head -1 | grep -oE '[0-9]+' | head -1
}

# ── Case 1: Fresh install ──────────────────────────────────────────
echo "[Case 1] Fresh install"
OUTPUT=$(CLAUDE_HOME="$TARGET" ./install.sh --force)
TOTAL_FILES=$(count_field "files" "$OUTPUT")
assert "manifest exists" "[ -f '$MANIFEST' ]"
assert "manifest is valid JSON" "python3 -m json.tool '$MANIFEST' >/dev/null 2>&1"
assert "harness/bin/harness copied" "[ -f '$TARGET/harness/bin/harness' ]"
assert "all 7 ha-* skills copied" "[ \$(ls -d '$TARGET'/skills/ha-* | wc -l) -eq 7 ]"
assert "_ha_shared copied" "[ -f '$TARGET/skills/_ha_shared/utils.py' ]"
assert "installed harness validate passes" "python3 '$TARGET/harness/bin/harness' validate >/dev/null 2>&1"
assert "file count ≥ 40 (sanity)" "[ '$TOTAL_FILES' -ge 40 ]"

# ── Case 2: Re-run with no source changes ─────────────────────────
echo "[Case 2] Re-run no changes"
OUTPUT=$(CLAUDE_HOME="$TARGET" ./install.sh --force)
UNCHANGED=$(count_field "unchanged" "$OUTPUT")
MODIFIED=$(count_field "modified" "$OUTPUT")
assert "all files unchanged ($UNCHANGED == $TOTAL_FILES)" "[ '$UNCHANGED' = '$TOTAL_FILES' ]"
assert "zero modified" "[ '$MODIFIED' = '0' ]"

# ── Case 3: Modify source, re-run ─────────────────────────────────
echo "[Case 3] Source modified → install detects"
TMP_SRC=$(mktemp -d)
cp -r harness skills install.sh "$TMP_SRC/"
echo "# test-only" >> "$TMP_SRC/harness/profiles/_base.md"
OUTPUT=$(CLAUDE_HOME="$TARGET" "$TMP_SRC/install.sh" --force)
MODIFIED=$(count_field "modified" "$OUTPUT")
UNCHANGED=$(count_field "unchanged" "$OUTPUT")
EXPECTED_UNCHANGED=$((TOTAL_FILES - 1))
assert "detected exactly 1 modified" "[ '$MODIFIED' = '1' ]"
assert "$EXPECTED_UNCHANGED unchanged" "[ '$UNCHANGED' = '$EXPECTED_UNCHANGED' ]"
rm -rf "$TMP_SRC"

# ── Case 4: Dry-run should not modify target ──────────────────────
echo "[Case 4] --dry-run does not modify target"
# 기존 manifest mtime 저장
BEFORE_MTIME=$(stat -c %Y "$MANIFEST" 2>/dev/null || stat -f %m "$MANIFEST")
sleep 1
CLAUDE_HOME="$TARGET" ./install.sh --dry-run >/dev/null
AFTER_MTIME=$(stat -c %Y "$MANIFEST" 2>/dev/null || stat -f %m "$MANIFEST")
assert "dry-run leaves manifest untouched" "[ '$BEFORE_MTIME' = '$AFTER_MTIME' ]"

echo ""
echo "=== Result: PASSED=$PASSED FAILED=$FAILED ==="
[ "$FAILED" -eq 0 ]
