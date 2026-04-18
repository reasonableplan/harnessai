#!/usr/bin/env bash
# HarnessAI 설치 스크립트 (Unix/WSL/Git Bash)
#
# 사용법:
#   ./install.sh              # 상호작용 (기존 설치 있으면 diff 확인)
#   ./install.sh --force      # 확인 없이 덮어쓰기
#   ./install.sh --dry-run    # 실제 복사 없이 계획만 출력
#   CLAUDE_HOME=/custom/.claude ./install.sh    # 커스텀 타겟
#
# 동작:
#   1. harness/ → $CLAUDE_HOME/harness/
#   2. skills/{ha-*,_ha_shared} → $CLAUDE_HOME/skills/
#   3. $CLAUDE_HOME/harness/.install-manifest.json 에 파일 목록 + SHA256 기록
#   4. 재실행 시 manifest diff 로 변경 감지

set -eo pipefail  # nounset 제외 — 빈 배열 체크가 bash 3.2/msys 에서 trip 함

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
            echo "[FAIL] 알 수 없는 옵션: $arg" >&2
            exit 2
            ;;
    esac
done

# sha256 명령 탐지 (Linux: sha256sum, macOS: shasum -a 256)
if command -v sha256sum >/dev/null 2>&1; then
    sha256_cmd() { sha256sum "$1" | awk '{print $1}'; }
elif command -v shasum >/dev/null 2>&1; then
    sha256_cmd() { shasum -a 256 "$1" | awk '{print $1}'; }
else
    echo "[FAIL] sha256sum 또는 shasum 필요" >&2
    exit 3
fi

# 복사 계획 구성 — (source_abs, target_rel) 쌍
declare -a PLAN
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

echo "HarnessAI 설치 준비"
echo "  repo:   $REPO_ROOT"
echo "  target: $CLAUDE_HOME"
echo "  files:  ${#PLAN[@]}"
echo ""

# 기존 manifest 읽어 diff 계산
# manifest 파일 형식은 한 줄에 target + sha256 가 함께 있는 JSON 엔트리:
#   { "target": "harness/foo.md", "sha256": "abc123..." },
declare -A OLD_HASHES
if [ -f "$MANIFEST_PATH" ]; then
    while IFS=$'\t' read -r tgt hash; do
        [ -n "$tgt" ] && [ -n "$hash" ] && OLD_HASHES["$tgt"]="$hash"
    done < <(sed -n 's/.*"target": *"\([^"]*\)".*"sha256": *"\([0-9a-f]*\)".*/\1\t\2/p' "$MANIFEST_PATH")
fi

# 변경 분류
declare -a ADDED MODIFIED UNCHANGED
for entry in "${PLAN[@]}"; do
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

# manifest 에는 있지만 이번 복사 대상엔 없는 파일 (= 이전 설치 후 repo 에서 제거된 파일)
declare -a REMOVED
declare -A NEW_TARGETS
for entry in "${PLAN[@]}"; do
    NEW_TARGETS["${entry#*:}"]=1
done
for t in "${!OLD_HASHES[@]}"; do
    [ -z "${NEW_TARGETS[$t]:-}" ] && REMOVED+=("$t")
done

echo "변경 요약:"
echo "  added:     ${#ADDED[@]}"
echo "  modified:  ${#MODIFIED[@]}"
echo "  unchanged: ${#UNCHANGED[@]}"
echo "  removed:   ${#REMOVED[@]}"
echo ""

if [ "${#MODIFIED[@]}" -gt 0 ] && [ "$FORCE" -eq 0 ] && [ "$DRY_RUN" -eq 0 ]; then
    echo "수정될 파일:"
    for f in "${MODIFIED[@]}"; do echo "  M $f"; done
    echo ""
    if [ "${#REMOVED[@]}" -gt 0 ]; then
        echo "삭제될 파일 (repo 에서 제거됨 — manifest 는 보존):"
        for f in "${REMOVED[@]}"; do echo "  D $f"; done
        echo ""
    fi
    read -r -p "계속하시겠습니까? [y/N] " reply
    case "$reply" in
        [yY]|[yY][eE][sS]) ;;
        *) echo "중단."; exit 0 ;;
    esac
fi

if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] 실제 복사 생략."
    exit 0
fi

# 복사 + manifest 작성
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
for entry in "${PLAN[@]}"; do
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

echo "[OK] 설치 완료"
echo "  installed: $count files"
echo "  manifest:  $MANIFEST_PATH"
echo ""
echo "환경 변수 설정 (셸 프로파일에 추가 권장):"
echo "  export HARNESS_AI_HOME=\"$REPO_ROOT\""
echo ""
echo "다음: 새 Claude Code 세션에서 '/ha-init' 사용 가능"
