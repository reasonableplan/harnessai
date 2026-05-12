#!/usr/bin/env python3
"""HarnessAI v2 — `/ha-review` 백엔드.

ai-slop 휴리스틱 (7번째 훅) 도 여기에 직접 구현.
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
    assert_state,
    get_active_profiles,
    info,
    load_plan,
    record_verify,
    regress,
    resolve_guideline_paths,
    save_plan,
    transition,
)


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


def _strip_non_code_from_diff(diff: str) -> str:
    """git diff 에서 코드 파일 블록만 남김 (문서/템플릿 placeholder 를 ai-slop 로 오탐 방지).

    제외 대상:
    - `docs/` 경로 (skeleton.md, harness-plan.md, AGENTS.md, README 등)
    - `*.md` 확장자
    - `templates/` 경로의 조각
    - `.harness-backup-*` 백업 파일
    """
    if not diff:
        return diff
    lines = diff.splitlines(keepends=True)
    out: list[str] = []
    skip = False
    for line in lines:
        if line.startswith("diff --git "):
            # 파일 헤더: "diff --git a/<path> b/<path>"
            parts = line.split(" b/", 1)
            path = parts[1].strip() if len(parts) == 2 else ""
            skip = (
                path.endswith(".md")
                or "/docs/" in path
                or "/templates/" in path
                or ".harness-backup-" in path
                or path.startswith("docs/")
                or path.startswith("templates/")
            )
        if not skip:
            out.append(line)
    return "".join(out)


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

    # git diff
    diff = ""
    try:
        out = subprocess.run(
            ["git", "diff", "main...HEAD"], cwd=str(project),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        diff = out.stdout if out.returncode == 0 else ""
    except FileNotFoundError:
        pass

    if not diff:
        # 기본: working tree diff
        try:
            out = subprocess.run(
                ["git", "diff", "HEAD"], cwd=str(project),
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            diff = out.stdout
        except FileNotFoundError:
            pass

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
        "changed_files": changed_files,
        "ai_slop_findings_in_diff": _ai_slop_scan(diff),
        "test_distribution_findings": test_distribution_findings,
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
        "violations": json.loads(args.violations) if args.violations else [],
        "next": "(다음 단계 선택) /ship | /retro" if passed else "/ha-build <T-ID>",
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="ha-review")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prepare")
    r = sub.add_parser("record")
    r.add_argument("--verdict", required=True)
    r.add_argument("--summary", default="")
    r.add_argument("--violations", default="", help="JSON 배열 string")
    args = parser.parse_args()
    if args.cmd == "prepare":
        return cmd_prepare(args)
    return cmd_record(args)


if __name__ == "__main__":
    sys.exit(main())
