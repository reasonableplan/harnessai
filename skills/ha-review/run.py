#!/usr/bin/env python3
"""HarnessAI v2 — `/ha-review` 백엔드.

ai-slop 휴리스틱 (7번째 훅) 도 여기에 직접 구현.
보안 훅 (SecurityHooks.from_profile().run_all()) + mobile 룰도 prepare/record 양쪽에서 자동 실행.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "_ha_shared"))
from utils import (  # noqa: E402, I001
    HARNESS_HOME,
    MOBILE_PROFILE_IDS as _MOBILE_PROFILE_IDS,
    FRONTEND_PROFILE_IDS as _FRONTEND_PROFILE_IDS,
    assert_state,
    get_active_profiles,
    info,
    load_plan,
    record_verify,
    regress,
    resolve_guideline_paths,
    save_plan,
    transition,
    untracked_pseudo_diff,
)

# backend src import — utils.py 가 backend/ 를 sys.path 에 추가 보장
from src.orchestrator.security_hooks import (  # noqa: E402
    SecurityHooks,
    detect_local_packages,
    parse_skeleton_stack_whitelist,
    parse_tsconfig_path_prefixes,
    strip_doc_files_from_diff,
)
from src.orchestrator.context import extract_section_by_id  # noqa: E402
from src.orchestrator.skeleton_hash import check_skeleton_hash  # noqa: E402


# ── ai-slop 패턴 (7번째 훅) ─────────────────────────────────────────


_AI_SLOP_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"^\s*\"\"\"[^\"]{200,}\"\"\"\s*$", re.MULTILINE),
        "장황한 docstring (>200자) — 핵심만 남기고 축약",
        "WARN",
    ),
    (
        re.compile(r"try:\s*\n\s+[^\n]+\n\s*except\s+\w+:\s*\n\s+raise\s*\n", re.MULTILINE),
        "의미 없는 try/except (re-raise 만) — 제거 권장",
        "WARN",
    ),
    (
        re.compile(r"#\s*(TODO|FIXME|XXX)\b", re.IGNORECASE),
        "신규 TODO/FIXME — 이슈 번호 + 담당자 명시 또는 해결",
        "WARN",
    ),
    (
        re.compile(r"^def\s+_unused_\w+", re.MULTILINE),
        "unused 함수 prefix — 제거 권장",
        "WARN",
    ),
    (
        re.compile(r"^\s*pass\s*#.*later", re.MULTILINE | re.IGNORECASE),
        "임시 pass 흔적 — 구현 누락",
        "BLOCK",
    ),
    (
        re.compile(
            r"_\w*(?:BACKOFF|RETRY|ATTEMPT|DELAY|WAIT|TIMEOUT|SLEEP)\w*\s*=\s*"
            r"[\(\[][^,)\]]+(?:,\s*[^,)\]]+){2,}[\)\]]"
            r"[\s\S]{0,500}?"
            r"(?:max_(?:retries|attempts|tries)\s*=\s*[12]\b|range\s*\(\s*[12]\s*\))",
            re.MULTILINE,
        ),
        "dead 상수 의심 (LESSON-018) — 상수 정의 범위 vs 실제 사용 범위 확인",
        "WARN",
    ),
]


# 문서 diff 제외 — backend strip_doc_files_from_diff 로 이관 (LESSON-030,
# SecurityHooks/mobile 룰 입력에도 동일 적용).
_strip_non_code_from_diff = strip_doc_files_from_diff


def _ai_slop_scan(text: str) -> list[dict[str, str]]:
    """diff 에서 코드 파일만 추려서 ai-slop 패턴 검사."""
    code_only = _strip_non_code_from_diff(text)
    findings: list[dict[str, str]] = []
    for pat, msg, sev in _AI_SLOP_PATTERNS:
        for m in pat.finditer(code_only):
            findings.append({"hook": "ai-slop", "severity": sev, "message": msg, "snippet": m.group(0)[:100]})
    return findings


# ── 테스트 분포 체크 ──────────────────────────────────────────────
#
# 프로파일별 path 아래 src/ ↔ tests/ 대응을 확인해 커버리지 공백 / 편중 감지.
# - Python: ast.FunctionDef 중 def test_* 카운트
# - JS/TS: describe() / it() / test() 호출 정규식 카운트
# - src 모듈 있는데 tests/ 없음 → BLOCK
# - 편차 10x 이상 → WARN (I/O 경계 커버리지 부족 신호)


_JS_TEST_CALL_RE = re.compile(r"^\s*(describe|it|test)\s*\(", re.MULTILINE)

# 스캔에서 제외할 디렉토리 (빌드 산출물/의존성/캐시).
_SKIP_DIRS = frozenset({
    "node_modules", ".next", "dist", "build", ".turbo", ".svelte-kit",
    ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
    ".git", "coverage", ".coverage",
})
# 테스트 디렉토리 이름 (소스 스캔 시 제외, 테스트 스캔 시 포함).
_TEST_DIR_NAMES = frozenset({"tests", "test", "__tests__", "spec"})


def _iter_files(root: Path, patterns: tuple[str, ...]) -> list[Path]:
    """root 아래 pattern 매칭 파일을 skip dir 제외하고 평면 수집."""
    results: list[Path] = []
    for pat in patterns:
        for p in root.rglob(pat):
            if any(part in _SKIP_DIRS for part in p.parts):
                continue
            results.append(p)
    return sorted(results)


def _language_from_profile(profile_id: str, toolchain_test: str | None) -> str:
    """profile → 'python' | 'javascript' | 'unknown' 판정.

    우선순위: toolchain.test 커맨드 키워드 > profile id 접두사.
    """
    cmd = (toolchain_test or "").lower()
    if "pytest" in cmd or "python" in cmd:
        return "python"
    if "vitest" in cmd or "jest" in cmd or "playwright" in cmd:
        return "javascript"
    pid = (profile_id or "").lower()
    if "python" in pid or pid == "fastapi":
        return "python"
    if "react" in pid or "next" in pid or "vite" in pid:
        return "javascript"
    return "unknown"


def _python_test_file_counts(files: list[Path], base: Path) -> dict[str, int]:
    """Python 테스트 파일들의 def test_* 함수 수 카운트 (AST)."""
    result: dict[str, int] = {}
    for py in files:
        if py.name in ("__init__.py", "conftest.py"):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (SyntaxError, OSError):
            continue
        count = sum(
            1 for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name.startswith("test_")
        )
        try:
            key = str(py.relative_to(base))
        except ValueError:
            key = str(py)
        result[key] = count
    return result


def _js_test_file_counts(files: list[Path], base: Path) -> dict[str, int]:
    """JS/TS 테스트 파일들의 describe/it/test 호출 수."""
    result: dict[str, int] = {}
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            key = str(f.relative_to(base))
        except ValueError:
            key = str(f)
        result[key] = len(_JS_TEST_CALL_RE.findall(text))
    return result


def _find_python_test_files(profile_root: Path, project_root: Path) -> list[Path]:
    """profile_root 아래 tests/ 또는 project_root/tests (모노리포 레이아웃 fallback)."""
    candidates: list[Path] = []
    for base in (profile_root / "tests", profile_root / "test"):
        if base.exists() and base.is_dir():
            candidates.extend(_iter_files(base, ("test_*.py", "*_test.py")))
    # profile_root 가 project_root 하위면 루트의 tests/ 도 후보
    if profile_root != project_root:
        for base in (project_root / "tests", project_root / "test"):
            if base.exists() and base.is_dir():
                candidates.extend(_iter_files(base, ("test_*.py", "*_test.py")))
    # 중복 제거 (대소문자 무관 경로)
    seen: set[str] = set()
    out: list[Path] = []
    for p in candidates:
        key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _find_js_test_files(profile_root: Path) -> list[Path]:
    """profile_root 아래 test/spec 파일 (tests/, __tests__/, 콜로케이션 모두)."""
    return _iter_files(
        profile_root,
        (
            "*.test.ts", "*.test.tsx", "*.test.js", "*.test.jsx",
            "*.spec.ts", "*.spec.tsx", "*.spec.js", "*.spec.jsx",
        ),
    )


def _scan_source_modules(src_dir: Path, lang: str) -> list[str]:
    """src/ 아래 구현 모듈 파일 수집 (테스트/더미/빌드 산출물 제외)."""
    modules: list[str] = []

    def _is_test_path(p: Path) -> bool:
        if ".test." in p.name or ".spec." in p.name:
            return True
        return any(part in _TEST_DIR_NAMES for part in p.parts)

    if lang == "python":
        for p in _iter_files(src_dir, ("*.py",)):
            if p.name == "__init__.py" or _is_test_path(p):
                continue
            modules.append(str(p.relative_to(src_dir)))
    elif lang == "javascript":
        for p in _iter_files(src_dir, ("*.ts", "*.tsx", "*.js", "*.jsx")):
            if p.name.endswith(".d.ts") or _is_test_path(p):
                continue
            modules.append(str(p.relative_to(src_dir)))
    return modules


def _check_test_distribution(
    project: Path,
    profile_id: str,
    profile_path: str,
    toolchain_test: str | None,
) -> list[dict[str, str]]:
    """단일 프로파일의 테스트 분포 체크. 찾은 이슈를 dict 리스트로 반환."""
    findings: list[dict[str, str]] = []
    lang = _language_from_profile(profile_id, toolchain_test)
    if lang == "unknown":
        return findings

    project_root = project.resolve()
    root = (project / profile_path).resolve() if profile_path != "." else project_root
    src_dir = root / "src"
    if not src_dir.exists():
        return findings  # src/ 없는 프로파일은 skip

    modules = _scan_source_modules(src_dir, lang)
    if not modules:
        return findings

    if lang == "python":
        test_files = _find_python_test_files(root, project_root)
        test_counts = _python_test_file_counts(test_files, root)
    else:
        test_files = _find_js_test_files(root)
        test_counts = _js_test_file_counts(test_files, root)

    total = sum(test_counts.values())
    if total == 0:
        findings.append({
            "hook": "test-distribution",
            "severity": "BLOCK",
            "message": (
                f"[{profile_id} @ {profile_path}] src/ 에 {len(modules)} 모듈 존재, "
                f"테스트 파일 0개 (tests/, __tests__/, *.test.*, *.spec.* 전부 미검출)"
            ),
            "profile_path": profile_path,
        })
        return findings

    nonzero = [c for c in test_counts.values() if c > 0]
    if len(nonzero) >= 2:
        ratio = max(nonzero) / min(nonzero)
        if ratio >= 10:
            top_file, top_n = max(test_counts.items(), key=lambda kv: kv[1])
            bot_file, bot_n = min(
                ((k, v) for k, v in test_counts.items() if v > 0),
                key=lambda kv: kv[1],
            )
            findings.append({
                "hook": "test-distribution",
                "severity": "WARN",
                "message": (
                    f"[{profile_id} @ {profile_path}] 테스트 분포 편차 {ratio:.1f}x "
                    f"— {top_file}({top_n}) vs {bot_file}({bot_n}). "
                    f"I/O 경계 모듈 커버리지 부족 의심"
                ),
                "profile_path": profile_path,
            })
    return findings


# ── mobile 보안 룰 ──────────────────────────────────────────────────
#
# 활성 profile 이 mobile 인 경우에만 적용. non-mobile profile_id → 빈 리스트.

# mobile secret storage 위반 패턴 (BLOCK)
_MOBILE_SECRET_STORAGE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"AsyncStorage\.setItem\s*\(.*[Tt]oken", re.MULTILINE),
        "AsyncStorage 에 토큰 저장 금지 — react-native-keychain 또는 expo-secure-store 사용",
    ),
    (
        re.compile(r"SharedPreferences.*[Tt]oken|[Tt]oken.*SharedPreferences", re.MULTILINE),
        "SharedPreferences 에 토큰 저장 금지 — Android Keystore 또는 EncryptedSharedPreferences 사용",
    ),
    (
        re.compile(r"UserDefaults.*[Tt]oken|[Tt]oken.*UserDefaults", re.MULTILINE),
        "UserDefaults 에 토큰 저장 금지 — iOS Keychain 사용",
    ),
    (
        re.compile(r"shared_preferences.*token|token.*shared_preferences", re.MULTILINE | re.IGNORECASE),
        "shared_preferences 에 토큰 저장 금지 — flutter_secure_storage 사용",
    ),
]

# mobile 권한 일괄 요청 위반 패턴 (WARN): 한 diff 블록에 3개 이상 권한 추가 라인
_PERMISSION_KEYWORDS = re.compile(
    r"CAMERA|LOCATION|NOTIFICATION|MICROPHONE|CONTACTS|STORAGE|READ_|WRITE_|ACCESS_",
    re.IGNORECASE,
)

# CocoaPods 신규 사용 (WARN, ios-swift only)
_COCOAPODS_NEW_POD_RE = re.compile(r"^\+\s*pod\s+['\"]", re.MULTILINE)

# react-native CLI 직접 사용 (WARN, react-native-expo only)
_RN_CLI_DIRECT_RE = re.compile(
    r"react-native\s+run-(?:android|ios)", re.MULTILINE
)


def _check_mobile_secret_storage(diff: str, profile_id: str) -> list[dict[str, str]]:
    """모바일 시크릿 storage 위반 탐지 (BLOCK). mobile profile 만."""
    if profile_id not in _MOBILE_PROFILE_IDS:
        return []
    findings: list[dict[str, str]] = []
    # diff 에서 추가된 라인(+로 시작)만 검사
    added = "\n".join(
        line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")
    )
    for pat, msg in _MOBILE_SECRET_STORAGE_PATTERNS:
        if pat.search(added):
            findings.append({
                "hook": "mobile-secret-storage",
                "severity": "BLOCK",
                "message": msg,
            })
    return findings


def _check_mobile_permission_burst(diff: str, profile_id: str) -> list[dict[str, str]]:
    """모바일 권한 일괄 요청 위반 탐지 (WARN). mobile profile 만."""
    if profile_id not in _MOBILE_PROFILE_IDS:
        return []
    # 추가된 라인에서 권한 키워드 수 카운트
    added_lines = [
        line[1:]
        for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    permission_lines = [l for l in added_lines if _PERMISSION_KEYWORDS.search(l)]
    if len(permission_lines) >= 3:
        return [{
            "hook": "mobile-permission-burst",
            "severity": "WARN",
            "message": (
                f"권한 {len(permission_lines)}개 일괄 요청 감지 — "
                "사용 시점(just-in-time)에 개별 요청 권장 (UX + 스토어 정책)"
            ),
        }]
    return []


def _check_cocoapods_new(diff: str, profile_id: str) -> list[dict[str, str]]:
    """CocoaPods 신규 pod 추가 탐지 (WARN). ios-swift profile 만."""
    if profile_id != "ios-swift":
        return []
    findings: list[dict[str, str]] = []
    for m in _COCOAPODS_NEW_POD_RE.finditer(diff):
        findings.append({
            "hook": "cocoapods-new",
            "severity": "WARN",
            "message": (
                f"CocoaPods 신규 pod 추가 감지: {m.group(0).strip()} — "
                "Swift Package Manager(SPM) 우선 검토 권장"
            ),
        })
    return findings


def _check_rn_cli(diff: str, profile_id: str) -> list[dict[str, str]]:
    """react-native CLI 직접 사용 탐지 (WARN). react-native-expo profile 만."""
    if profile_id != "react-native-expo":
        return []
    findings: list[dict[str, str]] = []
    for m in _RN_CLI_DIRECT_RE.finditer(diff):
        findings.append({
            "hook": "rn-cli-direct",
            "severity": "WARN",
            "message": (
                f"react-native CLI 직접 사용 감지: '{m.group(0)}' — "
                "Expo 프로젝트는 'expo run:android' / 'expo run:ios' 사용"
            ),
        })
    return findings


# ── 공통 헬퍼 ──────────────────────────────────────────────────────


_TRUNK_NAMES = ("main", "master")

# git 의 빈 트리 해시 — `git diff _EMPTY_TREE HEAD` = 전체 트래킹 소스를 diff 로 합성.
# base 미결정 + 커밋/워킹트리/untracked 모두 빈 경우(예: main 직작업+전부 커밋+원격 없음)
# 보안훅이 빈 입력으로 vacuous pass(false-green APPROVE)하던 결함(issue #8)의 폴백.
_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def _git_capture(project: Path, args: list[str]) -> str | None:
    """git 명령 stdout 반환 (exit 0). 실패/미설치/타임아웃 시 None."""
    try:
        out = subprocess.run(
            ["git", *args], cwd=str(project),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return out.stdout if out.returncode == 0 else None


def _git_ref_exists(project: Path, ref: str) -> bool:
    """ref 가 커밋으로 해석되는지 (rev-parse --verify)."""
    return _git_capture(project, ["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"]) is not None


def _resolve_diff_base(project: Path, explicit_base: str | None) -> str | None:
    """리뷰 diff 의 base ref 결정 (이슈 #18).

    우선순위:
      1. explicit_base (--base) — 사용자/부모가 빌드 시작 커밋 등을 명시
      2. 피처 브랜치면 main/master (분기점) — base...HEAD = 브랜치 변경분
      3. main/master 직작업이면 origin/main (마지막 push≈마지막 ship) 추적
      4. 못 찾으면 None → 호출처가 워킹트리 fallback + scope 로 표면화

    (3) 이 핵심: main 에서 직접 작업하고 태스크를 커밋하면 `main...HEAD` 가
    항상 비어 보안훅이 vacuous pass 하던 결함을 메운다.
    """
    if explicit_base:
        return explicit_base
    branch = (_git_capture(project, ["rev-parse", "--abbrev-ref", "HEAD"]) or "").strip()
    if branch not in _TRUNK_NAMES:
        for trunk in _TRUNK_NAMES:
            if _git_ref_exists(project, trunk):
                return trunk
    for remote_trunk in ("origin/main", "origin/master"):
        if _git_ref_exists(project, remote_trunk):
            return remote_trunk
    return None


def _extract_diff(project: Path, base: str | None = None) -> tuple[str, str]:
    """리뷰 대상 diff + scope 라벨 반환 (이슈 #18).

    base...HEAD (커밋된 빌드 변경분) 우선, base 미결정/빈 결과면 워킹트리(HEAD)
    fallback. untracked 신규 파일은 의사 diff 로 합류. scope 라벨은 호출처가
    출력/경고에 써서 vacuous pass 위험(워킹트리 collapse)을 표면화한다.
    """
    resolved = _resolve_diff_base(project, base)
    diff = ""
    scope = ""
    if resolved is not None:
        committed = _git_capture(project, ["diff", f"{resolved}...HEAD"])
        if committed and committed.strip():
            diff, scope = committed, f"{resolved}...HEAD"

    if not diff:
        worktree = _git_capture(project, ["diff", "HEAD"]) or ""
        diff = worktree
        if resolved is None:
            scope = "working-tree(HEAD) — base 미결정"
        else:
            scope = f"working-tree(HEAD) — base '{resolved}...HEAD' 빈 결과"

    # untracked 신규 파일은 git diff 에 없음 — 의사 diff 로 같은 스캔 입력에 합류
    combined = diff + untracked_pseudo_diff(project)
    if combined.strip():
        return combined, scope

    # base 미결정 + 커밋/워킹트리/untracked 모두 빔 → 빈 입력으로 보안훅이 vacuous
    # pass 하던 false-green(issue #8) 차단: 전체 트래킹 소스를 검토 입력으로 폴백.
    full = _git_capture(project, ["diff", _EMPTY_TREE, "HEAD"]) or ""
    if full.strip():
        return full, "full-source — base 미결정/빈 diff (전체 트래킹 소스 검토)"
    return combined, scope


# 역방향 contract 검증 (architecture review F7-1) — contract-validator 훅은
# "skeleton 에 없는 endpoint 구현" 만 잡는다. 반대 방향 (선언했는데 미구현) 은
# 아래 helper 가 잡는다. skeleton 의 interface.http 표기: **`GET /api/users`**.
_HTTP_METHOD_PATH_RE = re.compile(r"`(GET|POST|PUT|PATCH|DELETE)\s+(/[^\s`]+)`")
_REVERSE_SOURCE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".kt", ".swift", ".dart"}
_REVERSE_SKIP_DIRS = {
    "node_modules", ".venv", "venv", "dist", "build", "__pycache__",
    ".git", "docs", ".orchestra",
}


def _iter_source_texts(project: Path) -> list[str]:
    """프로젝트 소스 파일 내용 목록 (벤더/빌드/문서 디렉토리 제외)."""
    texts: list[str] = []
    stack = [project]
    while stack:
        d = stack.pop()
        try:
            entries = list(d.iterdir())
        except OSError:
            continue
        for e in entries:
            if e.is_dir():
                if e.name not in _REVERSE_SKIP_DIRS:
                    stack.append(e)
            elif e.suffix in _REVERSE_SOURCE_EXTS:
                try:
                    texts.append(e.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    continue
    return texts


def _check_missing_declared_endpoints(
    project: Path, skeleton_text: str
) -> list[dict[str, str]]:
    """skeleton interface.http 에 선언됐지만 소스 어디에도 없는 엔드포인트.

    path 의 정적 prefix ("{param}" 앞부분) 가 소스 전체에서 발견되지 않을 때만
    보고 — router prefix 조합 (`APIRouter(prefix=...)` + `@router.get("/{id}")`)
    로 인한 false positive 를 보수적으로 회피. 발견은 advisory — skipped/Phase 2
    태스크로 설명되는지 리뷰어가 cross-check 후 집계한다 (SKILL.md §2.9).
    """
    section = extract_section_by_id(skeleton_text, "interface.http")
    if not section:
        return []
    declared = sorted(
        {(m.group(1), m.group(2)) for m in _HTTP_METHOD_PATH_RE.finditer(section)}
    )
    if not declared:
        return []
    haystacks = _iter_source_texts(project)
    findings: list[dict[str, str]] = []
    for method, path_str in declared:
        prefix = path_str.split("{")[0].rstrip("/") or path_str
        if not any(prefix in h for h in haystacks):
            findings.append(
                {"method": method, "path": path_str, "static_prefix": prefix}
            )
    return findings


# tsconfig path-alias keys: "@shared/*": [...]. Regex-extract instead of JSON-
# parsing because tsconfig is JSONC (comments + trailing commas) — a parser would
# fail on real configs. Only @-prefixed aliases (scoped form) are collected; bare
# aliases are too risky to whitelist. Advisory + fail-safe: unreadable configs
# yield no prefixes (alias FPs remain) but never a crash.
_TSCONFIG_ALIAS_KEY_RE = re.compile(r'"(@[A-Za-z0-9_./*-]+)"\s*:')


def _collect_tsconfig_prefixes(project: Path) -> tuple[str, ...]:
    """Scan tsconfig*.json files for compilerOptions.paths aliases (FP #19).

    Searches the project root and one directory level down (monorepo sub-apps
    such as desktop/tsconfig.json). Derives import prefixes from @-aliased keys
    via :func:`parse_tsconfig_path_prefixes` (wildcard stripping reused).
    """
    keys: set[str] = set()
    candidates = list(project.glob("tsconfig*.json")) + list(project.glob("*/tsconfig*.json"))
    for cfg in candidates:
        try:
            raw = cfg.read_text(encoding="utf-8")
        except OSError:
            continue
        keys.update(_TSCONFIG_ALIAS_KEY_RE.findall(raw))
    if not keys:
        return ()
    return parse_tsconfig_path_prefixes({k: None for k in keys})


def _collect_findings(
    project: Path,
    profiles: list,  # list[Profile]
    diff: str,
    skeleton_text: str = "",
) -> dict:
    """ai-slop, SecurityHooks, mobile 룰 모두 실행해 결과를 합산.

    반환:
        {
            "ai_slop": [...],
            "security": [...],        # hook/severity/message/snippet 형태
            "block_count": N,
            "warn_count": M,
        }
    """
    ai_slop: list[dict[str, str]] = _ai_slop_scan(diff)

    security: list[dict[str, str]] = []

    # LESSON-030: 문서 diff (.md 산문/인라인 예시) 가 코드 패턴 훅을 오발시키므로
    # 보안 훅 입력은 코드 파일 블록만. 자기 패키지 import 는 외부 의존성이 아님.
    code_diff = strip_doc_files_from_diff(diff)
    local_pkgs = detect_local_packages(project)

    # FP #19: skeleton §3 승인 라이브러리 + tsconfig paths 별칭을 frontend
    # dependency-check whitelist 에 병합해 오탐 제거 (frontend/mobile 모드에만 적용).
    stack_wl = parse_skeleton_stack_whitelist(skeleton_text)
    ts_prefixes = _collect_tsconfig_prefixes(project)

    # 이미 처리한 mode 는 중복 실행 방지
    seen_modes: set[str] = set()

    for profile in profiles:
        pid = profile.id
        if pid in _MOBILE_PROFILE_IDS:
            mode = "mobile"
        elif pid in _FRONTEND_PROFILE_IDS:
            mode = "frontend"
        else:
            mode = "backend"

        if mode not in seen_modes:
            seen_modes.add(mode)
            is_fe_like = mode in ("frontend", "mobile")
            hooks = SecurityHooks.from_profile(
                profile,
                extra_python_allowed=local_pkgs,
                extra_frontend_allowed=stack_wl if is_fe_like else None,
                extra_frontend_prefixes=ts_prefixes if is_fe_like else None,
            )
            result = hooks.run_all(
                code_diff,
                is_frontend=(mode == "frontend"),
                is_mobile=(mode == "mobile"),
            )
            for f in result.findings:
                security.append({
                    "hook": f.hook,
                    "severity": str(f.severity),
                    "message": f.message,
                    "snippet": f.snippet[:100] if f.snippet else "",
                })

        # mobile 룰 (SecurityHooks 와 별개 — diff 기반 패턴, 코드 블록만)
        if pid in _MOBILE_PROFILE_IDS:
            for finding in _check_mobile_secret_storage(code_diff, pid):
                security.append(finding)
            for finding in _check_mobile_permission_burst(code_diff, pid):
                security.append(finding)
            if pid == "ios-swift":
                for finding in _check_cocoapods_new(code_diff, pid):
                    security.append(finding)
            if pid == "react-native-expo":
                for finding in _check_rn_cli(code_diff, pid):
                    security.append(finding)

    block_count = sum(1 for f in security if f.get("severity") == "BLOCK")
    block_count += sum(1 for f in ai_slop if f.get("severity") == "BLOCK")
    warn_count = sum(1 for f in security if f.get("severity") == "WARN")
    warn_count += sum(1 for f in ai_slop if f.get("severity") == "WARN")

    return {
        "ai_slop": ai_slop,
        "security": security,
        "block_count": block_count,
        "warn_count": warn_count,
    }


# ── 명령 ───────────────────────────────────────────────────────────


def _check_git_repo(project: Path) -> None:
    """git 저장소 여부를 확인. git 없거나 repo 아니면 actionable 메시지와 함께 exit 2.

    ha-review 는 git diff 로 변경분을 추출해 보안/슬롭 훅에 입력한다.
    git 없으면 모든 검사가 빈 입력 → silent pass 위험이 있으므로 fail-fast 처리.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=str(project),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        info(
            "[FAIL] /ha-review 사전 조건 위반: git 명령 미설치.\n"
            f"       project: {project}\n"
            "       조치: git 을 설치한 후 재시도.\n"
            "       이유: ha-review 가 git diff 로 변경분을 추출해 보안/슬롭 훅에 입력.\n"
            "             git 없으면 모든 검사가 빈 입력 → silent pass 위험."
        )
        sys.exit(2)

    if result.returncode != 0:
        info(
            "[FAIL] /ha-review 사전 조건 위반: git 저장소 아님.\n"
            f"       project: {project}\n"
            "       조치: `git init && git add -A && git commit -m \"initial\"` 후 재시도.\n"
            "       이유: ha-review 가 git diff 로 변경분을 추출해 보안/슬롭 훅에 입력.\n"
            "             git 없으면 모든 검사가 빈 입력 → silent pass 위험."
        )
        sys.exit(2)


def cmd_prepare(args: argparse.Namespace) -> int:
    plan, plan_path, project = load_plan()
    assert_state(plan, ["verified"], "/ha-review")

    # git repo 사전 조건 — not-git 이면 silent pass 위험으로 fail-fast
    _check_git_repo(project)

    profiles = get_active_profiles(plan, project)
    diff, diff_scope = _extract_diff(project, getattr(args, "base", None))
    if diff_scope.startswith("working-tree"):
        info(
            f"[WARN] 리뷰 diff 가 워킹트리(HEAD)로 collapse 됨 — scope: {diff_scope}.\n"
            "       빌드를 이미 커밋했다면 변경분이 비어 보안/슬롭 훅이 vacuous pass 할 수 있습니다.\n"
            "       빌드 시작 커밋을 base 로 지정: /ha-review prepare --base <ref>"
        )

    changed_files: list[str] = []
    for line in diff.splitlines():
        m = re.match(r"^\+\+\+ b/(.+)$", line)
        if m:
            changed_files.append(m.group(1))

    test_distribution_findings: list[dict[str, str]] = []
    for i, p in enumerate(profiles):
        path = plan.profiles[i].path if i < len(plan.profiles) else "."
        toolchain_test = getattr(getattr(p, "toolchain", None), "test", None)
        test_distribution_findings.extend(
            _check_test_distribution(project, p.id, path, toolchain_test)
        )

    # skeleton hash 비교 — 외부 수정 감지 (advisory only)
    skel_path = plan_path.parent / "skeleton.md"
    hash_check = check_skeleton_hash(plan.skeleton_hash, skel_path)
    if not hash_check.skeleton_missing and not hash_check.is_legacy and not hash_check.is_match:
        info(
            "[WARN] skeleton.md 가 마지막 ha-design/ha-redesign 이후 외부에서 수정된 듯합니다 "
            "(hash mismatch). redesign_history 에 audit trail 누락 가능 — "
            "/ha-redesign 으로 변경 사항 추적 권장."
        )

    # 역방향 contract 검증 — 선언-미구현 엔드포인트 (advisory, §2.9)
    missing_declared_endpoints: list[dict[str, str]] = []
    if skel_path.exists():
        try:
            missing_declared_endpoints = _check_missing_declared_endpoints(
                project, skel_path.read_text(encoding="utf-8")
            )
        except OSError as exc:
            info(f"[WARN] 역방향 contract 검증 건너뜀 — skeleton 읽기 실패: {exc}")
    if missing_declared_endpoints:
        info(
            f"[WARN] 선언-미구현 엔드포인트 {len(missing_declared_endpoints)}건 — "
            "skipped/Phase 2 태스크로 설명되는지 확인 후 집계 (§2.9)"
        )

    # 보안 훅 + ai-slop + mobile 룰 자동 실행 (prepare 는 advisory — exit 0 유지).
    # skeleton_text 는 dependency-check FP #19 (스택 승인 라이브러리 병합) 용.
    try:
        skeleton_text = skel_path.read_text(encoding="utf-8") if skel_path.exists() else ""
    except OSError:
        skeleton_text = ""
    findings = _collect_findings(project, profiles, diff, skeleton_text)

    output = {
        "project": str(project),
        "plan_path": str(plan_path),
        "profiles": [
            {
                "id": p.id,
                "lessons_applied": list(p.lessons_applied),
                "body_path": str(Path.home() / ".claude" / "harness" / "profiles" / f"{p.id}.md"),
                "guideline_paths": [str(g) for g in resolve_guideline_paths(p.id)],
            }
            for p in profiles
        ],
        "lessons_path": str(HARNESS_HOME / "backend" / "docs" / "shared-lessons.md"),
        "diff_size_bytes": len(diff),
        "diff_scope": diff_scope,
        "changed_files": changed_files,
        # backward compat — ai-slop 단독 키 유지
        "ai_slop_findings_in_diff": findings["ai_slop"],
        # 새 통합 키
        "security_findings": findings["security"],
        "security_summary": {
            "block_count": findings["block_count"],
            "warn_count": findings["warn_count"],
        },
        "test_distribution_findings": test_distribution_findings,
        "missing_declared_endpoints": missing_declared_endpoints,
        "skeleton_hash_check": {
            "is_match": hash_check.is_match,
            "is_legacy": hash_check.is_legacy,
            "skeleton_missing": hash_check.skeleton_missing,
        },
        "agent_prompt": str(HARNESS_HOME / "backend" / "agents" / "reviewer" / "CLAUDE.md"),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    plan, plan_path, project = load_plan()
    assert_state(plan, ["verified"], "/ha-review record")

    verdict = args.verdict.lower()
    if verdict not in ("approve", "reject"):
        info("[FAIL] --verdict: approve|reject")
        return 2

    allow_block: bool = getattr(args, "allow_block", False)

    # ── R5/R6: violations 파싱 ────────────────────────────────────────
    violations_raw = args.violations or ""
    violations: list[str] = []
    if violations_raw:
        try:
            parsed = json.loads(violations_raw)
            if isinstance(parsed, list):
                violations = [str(v) for v in parsed]
            else:
                violations = [str(parsed)]
        except json.JSONDecodeError:
            violations = [violations_raw]

    # ── R5: reject + violations 없음 → exit 1 ────────────────────────
    if verdict == "reject" and not violations:
        info(
            "[FAIL] /ha-review record reject 거부 — violations 누락.\n"
            "       SKILL.md 가드레일: REJECT 시 재작업 T-ID 없이 보고 금지.\n"
            '       예시: --violations \'["[auth-guard:BLOCK] src/foo.py:42 — JWT type claim 누락 → T-003"]\''
        )
        return 1

    # ── R6: approve + BLOCK 발견 → exit 1 (--allow-block 없으면) ─────
    if verdict == "approve" and not allow_block:
        profiles = get_active_profiles(plan, project)
        diff, _diff_scope = _extract_diff(project, getattr(args, "base", None))
        # skeleton_text 는 dependency-check FP #19 용 — prepare 와 동일 기준.
        _skel_path = plan_path.parent / "skeleton.md"
        try:
            skeleton_text = _skel_path.read_text(encoding="utf-8") if _skel_path.exists() else ""
        except OSError:
            skeleton_text = ""
        findings = _collect_findings(project, profiles, diff, skeleton_text)
        block_count = findings["block_count"]
        if block_count > 0:
            block_items = [
                f for f in (findings["security"] + findings["ai_slop"])
                if f.get("severity") == "BLOCK"
            ]
            detail_lines = "\n".join(
                f"       [{f['hook']}] {f['message']}"
                + (f" — {f['snippet'][:60]}" if f.get("snippet") else "")
                for f in block_items[:10]  # 최대 10건 출력
            )
            info(
                f"[FAIL] /ha-review record approve 거부 — BLOCK 위반 {block_count}건.\n"
                f"{detail_lines}\n"
                "       조치: REJECT 로 변경 후 violations 명시, 또는 코드 수정 후 prepare 재실행.\n"
                "       의도적 우회: --allow-block 명시."
            )
            return 1

    passed = verdict == "approve"
    summary = args.summary or ("APPROVE" if passed else "REJECT")
    record_verify(plan, step="ha-review", passed=passed, summary=summary)

    if passed:
        if plan.pipeline.current_step == "verified":
            transition(plan, "reviewed", completed_step="ha-review")
    else:
        # reject — building 으로 회귀
        if plan.pipeline.current_step != "building":
            regress(plan, "building")

    save_plan(plan, plan_path)

    output = {
        "verdict": verdict,
        "summary": summary,
        "current_step": plan.pipeline.current_step,
        "violations": violations,
        "next": "(다음 단계 선택) /ship | /retro" if passed else "/ha-build <T-ID>",
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def cmd_extract_lesson(args: argparse.Namespace) -> int:
    """v0.10.0 — 리뷰에서 발견한 패턴을 shared-lessons.md 의 Pending 섹션에 append.

    auto_extracted: true 마커 박힘. 사용자 promotion 으로만 main 섹션 진입.
    """
    from datetime import UTC, datetime

    if args.lessons_path:
        lessons_path = Path(args.lessons_path)
    else:
        lessons_path = HARNESS_HOME / "backend" / "docs" / "shared-lessons.md"

    if not lessons_path.exists():
        info(f"[FAIL] shared-lessons.md 없음: {lessons_path}")
        return 1

    text = lessons_path.read_text(encoding="utf-8")

    # 다음 LESSON ID — 기존 중 max + 1
    existing_ids = re.findall(r"## LESSON-(\d+):", text)
    next_id = (max((int(i) for i in existing_ids), default=0) + 1) if existing_ids else 1
    lesson_id = f"LESSON-{next_id:03d}"

    # 중복 방지 — title 이 기존 LESSON 과 lowercase 비교 시 거부
    title_norm = args.title.strip().lower()
    for existing_title in re.findall(r"## LESSON-\d+: (.+)", text):
        if title_norm == existing_title.strip().lower():
            info(f"[SKIP] 중복 LESSON 제목 — 기존: {existing_title}")
            output = {"lesson_id": None, "skipped": True, "reason": "duplicate_title"}
            print(json.dumps(output, ensure_ascii=False, indent=2))
            return 0

    extracted_at = datetime.now(UTC).strftime("%Y-%m-%d")

    block = (
        f"## {lesson_id}: {args.title.strip()}\n"
        f"<!-- auto_extracted: true / promotion_pending: true / extracted_at: {extracted_at} -->\n\n"
        f"**문제**: {args.problem.strip()}\n\n"
        f"**규칙**: {args.rule.strip()}\n"
    )
    if args.evidence:
        block += f"\n**근거**: {args.evidence.strip()}\n"
    block += "\n---\n"

    pending_header = "## Pending Lessons (자동 추출 — 사용자 promotion 대기)"
    if pending_header in text:
        # 기존 Pending 섹션 끝에 append (다음 ## 헤딩 직전 또는 EOF)
        idx = text.index(pending_header)
        rest = text[idx:]
        next_header_match = re.search(r"\n## (?!Pending Lessons)", rest)
        if next_header_match:
            insert_at = idx + next_header_match.start() + 1
            new_text = text[:insert_at] + "\n" + block + text[insert_at:]
        else:
            new_text = text.rstrip() + "\n\n" + block
    else:
        # Pending 섹션 신규 생성 — 파일 끝에 박음
        pending_intro = (
            "\n\n"
            + pending_header
            + "\n\n"
            + "> 자동 추출된 LESSON. 사용자 검토 후 main 섹션으로 promote"
            + " (auto_extracted 마커 제거) 또는 거부 (블록 삭제).\n\n"
            + block
        )
        new_text = text.rstrip() + pending_intro

    try:
        lessons_path.write_text(new_text, encoding="utf-8")
    except OSError as e:
        info(f"[FAIL] shared-lessons.md 쓰기 실패: {e}")
        return 1

    output = {
        "lesson_id": lesson_id,
        "title": args.title.strip(),
        "extracted_at": extracted_at,
        "section": "Pending Lessons",
        "promotion_pending": True,
        "lessons_path": str(lessons_path),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="ha-review")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument(
        "--base",
        default=None,
        help="리뷰 diff 의 base ref (예: 빌드 시작 커밋). 미지정 시 자동 결정 "
        "(피처브랜치→main, main직작업→origin/main).",
    )
    r = sub.add_parser("record")
    r.add_argument(
        "--base",
        default=None,
        help="approve+BLOCK 재검사 시 diff base ref (prepare 와 동일).",
    )
    r.add_argument("--verdict", required=True)
    r.add_argument("--summary", default="")
    r.add_argument("--violations", default="", help="JSON 배열 string")
    r.add_argument(
        "--allow-block",
        action="store_true",
        default=False,
        help="BLOCK 위반이 있어도 approve 강제 (의도적 우회 시)",
    )
    e = sub.add_parser("extract-lesson", help="자동 LESSON 추출 (v0.10.0 — Pending 섹션에 append)")
    e.add_argument("--title", required=True, help="LESSON 제목 (50자 이하)")
    e.add_argument("--problem", required=True, help="문제 설명")
    e.add_argument("--rule", required=True, help="규칙 / 해결 방법")
    e.add_argument("--evidence", default="", help="발견 위치 / 빈도 (선택)")
    e.add_argument(
        "--lessons-path",
        default="",
        help="shared-lessons.md 경로 (기본: <HARNESS_AI_HOME>/backend/docs/shared-lessons.md)",
    )
    args = parser.parse_args()
    if args.cmd == "prepare":
        return cmd_prepare(args)
    if args.cmd == "extract-lesson":
        return cmd_extract_lesson(args)
    return cmd_record(args)


if __name__ == "__main__":
    sys.exit(main())
