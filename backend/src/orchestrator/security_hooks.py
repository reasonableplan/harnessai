"""Security hooks — detect security and quality violations in agent output."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum


class Severity(StrEnum):
    BLOCK = "BLOCK"  # Reject immediately — merge forbidden
    WARN = "WARN"  # Log only — execution continues


@dataclass
class Finding:
    """A single violation detected by a hook."""

    hook: str
    severity: Severity
    message: str
    line: int = 0
    snippet: str = ""


@dataclass
class SecurityResult:
    """Aggregate result of all security hooks."""

    findings: list[Finding] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return any(f.severity == Severity.BLOCK for f in self.findings)

    @property
    def summary(self) -> str:
        blocks = [f for f in self.findings if f.severity == Severity.BLOCK]
        warns = [f for f in self.findings if f.severity == Severity.WARN]
        if not self.findings:
            return "security hooks passed"
        parts = []
        if blocks:
            parts.append(f"BLOCK x{len(blocks)}")
        if warns:
            parts.append(f"WARN x{len(warns)}")
        return " / ".join(parts)


# Whitelists (based on conventions.md)

_PYTHON_WHITELIST = {
    "fastapi",
    "uvicorn",
    "sqlmodel",
    "sqlalchemy",
    "alembic",
    "jose",
    "passlib",
    "bcrypt",
    "pydantic",
    "pydantic_settings",
    "httpx",
    "pytest",
    "pytest_asyncio",
    "asyncio",
    "typing",
    "pathlib",
    "dataclasses",
    "enum",
    "re",
    "json",
    "os",
    "sys",
    "datetime",
    "uuid",
    "logging",
    "functools",
    "itertools",
    "collections",
    "contextlib",
    "abc",
    "io",
    "time",
    "math",
    "hashlib",
    "hmac",
    "secrets",
    "base64",
    "urllib",
    "http",
    "email",
    "copy",
    "weakref",
    "threading",
    "multiprocessing",
    # Internal modules allowed
    "src",
    "__future__",
}

_FRONTEND_WHITELIST = {
    "react",
    "react-dom",
    "zustand",
    "axios",
    "tailwindcss",
    "postcss",
    "autoprefixer",
    "react-hook-form",
    "react-router-dom",
    "class-variance-authority",
    "clsx",
    "tailwind-merge",
    "lucide-react",
    "zod",
    # @radix-ui/* prefix handled separately
}

_FRONTEND_WHITELIST_PREFIXES = ("@radix-ui/",)


# ---------------------------------------------------------------------------
# 1. secret-filter
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"(?:API_KEY|SECRET_KEY|PASSWORD|PASSWD|TOKEN|AUTH_TOKEN|ACCESS_KEY|PRIVATE_KEY)"
            r'\s*=\s*["\'][^"\']{8,}["\']',
            re.IGNORECASE,
        ),
        "하드코딩 시크릿 의심",
    ),
    (
        re.compile(r"(?:sk-|pk-|ghp_|gho_|github_pat_)[A-Za-z0-9_]{20,}"),
        "API 키 패턴 (OpenAI/GitHub)",
    ),
    (
        re.compile(r"(?:mysql|postgresql|postgres)://[^:]+:[^@]+@"),
        "DB 연결 문자열에 비밀번호 포함",
    ),
]


def check_secret_filter(text: str) -> list[Finding]:
    findings: list[Finding] = []
    for i, line in enumerate(text.splitlines(), start=1):
        for pattern, message in _SECRET_PATTERNS:
            m = pattern.search(line)
            if m:
                findings.append(
                    Finding(
                        hook="secret-filter",
                        severity=Severity.BLOCK,
                        message=message,
                        line=i,
                        snippet=line.strip()[:120],
                    )
                )
    return findings


# ---------------------------------------------------------------------------
# 2. command-guard
# ---------------------------------------------------------------------------

_COMMAND_PATTERNS: list[tuple[re.Pattern[str], str, Severity]] = [
    (
        re.compile(r"\brm\s+-[rf]{1,2}\s+/", re.IGNORECASE),
        "위험한 rm -rf 명령",
        Severity.BLOCK,
    ),
    (
        re.compile(r"\bcurl\b.+\|\s*(?:bash|sh)\b"),
        "curl | bash 패턴 — 원격 코드 실행 위험",
        Severity.BLOCK,
    ),
    (
        re.compile(r"\bwget\b.+\|\s*(?:bash|sh)\b"),
        "wget | bash 패턴 — 원격 코드 실행 위험",
        Severity.BLOCK,
    ),
    (
        re.compile(r"\beval\s*\("),
        "eval() 사용 — 코드 인젝션 위험",
        Severity.BLOCK,
    ),
    (
        re.compile(r"\bexec\s*\((?!.*#\s*noqa)"),
        "exec() 사용 — 코드 인젝션 위험",
        Severity.BLOCK,
    ),
    (
        re.compile(r"\bos\.system\s*\("),
        "os.system() 사용 — subprocess 사용 권장",
        Severity.WARN,
    ),
    (
        re.compile(r"\bDROP\s+(?:TABLE|DATABASE|SCHEMA)\b", re.IGNORECASE),
        "DROP 명령 — 데이터 파괴 위험",
        Severity.BLOCK,
    ),
    (
        re.compile(r"\bTRUNCATE\s+TABLE\b", re.IGNORECASE),
        "TRUNCATE TABLE — 데이터 파괴 위험",
        Severity.BLOCK,
    ),
]


def check_command_guard(text: str) -> list[Finding]:
    findings: list[Finding] = []
    for i, line in enumerate(text.splitlines(), start=1):
        for pattern, message, severity in _COMMAND_PATTERNS:
            if pattern.search(line):
                findings.append(
                    Finding(
                        hook="command-guard",
                        severity=severity,
                        message=message,
                        line=i,
                        snippet=line.strip()[:120],
                    )
                )
    return findings


# ---------------------------------------------------------------------------
# 3. db-guard
# ---------------------------------------------------------------------------

_DB_PATTERNS: list[tuple[re.Pattern[str], str, Severity]] = [
    (
        re.compile(r'cursor\.execute\s*\(\s*["\']', re.IGNORECASE),
        "raw SQL (cursor.execute) — ORM 사용 필수",
        Severity.BLOCK,
    ),
    (
        re.compile(r'\btext\s*\(\s*["\'](?:SELECT|INSERT|UPDATE|DELETE)', re.IGNORECASE),
        "SQLAlchemy text() raw SQL — ORM 사용 필수",
        Severity.BLOCK,
    ),
    (
        re.compile(r'\.execute\s*\(\s*f["\']', re.IGNORECASE),
        "f-string SQL — SQL 인젝션 위험",
        Severity.BLOCK,
    ),
    (
        # DELETE FROM <table> without a WHERE clause on the same line
        re.compile(r"\bDELETE\s+FROM\s+\w+\s*(?:;|$)", re.IGNORECASE),
        "WHERE 없는 DELETE — 전체 행 삭제 위험",
        Severity.BLOCK,
    ),
    (
        re.compile(r"\bUPDATE\s+\w+\s+SET\b(?!.*WHERE)", re.IGNORECASE),
        "WHERE 없는 UPDATE 의심 — 전체 행 수정 위험",
        Severity.WARN,
    ),
]


def check_db_guard(text: str) -> list[Finding]:
    findings: list[Finding] = []
    for i, line in enumerate(text.splitlines(), start=1):
        for pattern, message, severity in _DB_PATTERNS:
            if pattern.search(line):
                findings.append(
                    Finding(
                        hook="db-guard",
                        severity=severity,
                        message=message,
                        line=i,
                        snippet=line.strip()[:120],
                    )
                )
    return findings


# ---------------------------------------------------------------------------
# 4. dependency-check
# ---------------------------------------------------------------------------

_PYTHON_IMPORT = re.compile(r"^(?:import|from)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)
_FRONTEND_IMPORT = re.compile(r"""from\s+(?P<q>['"])(@?[^'"./][^'"]*)(?P=q)""")
_PIP_INSTALL = re.compile(r"\bpip\s+install\s+([A-Za-z0-9_\-]+)", re.IGNORECASE)
_NPM_INSTALL = re.compile(r"\bnpm\s+install\s+([A-Za-z0-9_\-@/]+)", re.IGNORECASE)


def check_dependency(
    text: str,
    *,
    is_frontend: bool = False,
    python_whitelist: set[str] | None = None,
    frontend_whitelist: set[str] | None = None,
    frontend_prefixes: tuple[str, ...] | None = None,
) -> list[Finding]:
    """Dependency whitelist check.

    Harness v2: pass ``python_whitelist`` / ``frontend_whitelist`` /
    ``frontend_prefixes`` to inject profile-derived whitelists. ``None`` uses
    the built-in defaults.
    """
    py_wl = python_whitelist if python_whitelist is not None else _PYTHON_WHITELIST
    fe_wl = frontend_whitelist if frontend_whitelist is not None else _FRONTEND_WHITELIST
    fe_prefixes = (
        frontend_prefixes if frontend_prefixes is not None else _FRONTEND_WHITELIST_PREFIXES
    )

    findings: list[Finding] = []
    lines = text.splitlines()

    if not is_frontend:
        for i, line in enumerate(lines, start=1):
            m = _PYTHON_IMPORT.match(line.strip())
            if m:
                pkg = m.group(1).lower().replace("-", "_")
                if pkg not in py_wl:
                    findings.append(
                        Finding(
                            hook="dependency-check",
                            severity=Severity.WARN,
                            message=f"화이트리스트 외 패키지: {pkg} — Architect 승인 필요",
                            line=i,
                            snippet=line.strip()[:120],
                        )
                    )
        # Detect pip install commands
        for i, line in enumerate(lines, start=1):
            for m in _PIP_INSTALL.finditer(line):
                pkg = m.group(1).lower()
                if pkg not in py_wl:
                    findings.append(
                        Finding(
                            hook="dependency-check",
                            severity=Severity.BLOCK,
                            message=f"승인 없는 pip install: {pkg}",
                            line=i,
                            snippet=line.strip()[:120],
                        )
                    )
    else:
        for i, line in enumerate(lines, start=1):
            for m in _FRONTEND_IMPORT.finditer(line):
                pkg = m.group(2)
                allowed = pkg in fe_wl or any(pkg.startswith(p) for p in fe_prefixes)
                if not allowed:
                    findings.append(
                        Finding(
                            hook="dependency-check",
                            severity=Severity.WARN,
                            message=f"화이트리스트 외 패키지: {pkg} — Architect 승인 필요",
                            line=i,
                            snippet=line.strip()[:120],
                        )
                    )
        # Detect npm install commands
        for i, line in enumerate(lines, start=1):
            for m in _NPM_INSTALL.finditer(line):
                pkg = m.group(1)
                allowed = pkg in fe_wl or any(pkg.startswith(p) for p in fe_prefixes)
                if not allowed:
                    findings.append(
                        Finding(
                            hook="dependency-check",
                            severity=Severity.BLOCK,
                            message=f"승인 없는 npm install: {pkg}",
                            line=i,
                            snippet=line.strip()[:120],
                        )
                    )

    return findings


# ---------------------------------------------------------------------------
# 5. code-quality
# ---------------------------------------------------------------------------

_QUALITY_PATTERNS: list[tuple[re.Pattern[str], str, Severity]] = [
    (
        re.compile(r":\s*any\b"),
        "TypeScript any 타입 사용 — 타입 정의 필수",
        Severity.BLOCK,
    ),
    (
        re.compile(r"\bexcept\s*:\s*$"),
        "빈 except: — 최소한 logging 필수",
        Severity.BLOCK,
    ),
    (
        re.compile(r"\bconsole\.log\s*\("),
        "console.log 미삭제 — 프로덕션 코드에 부적합",
        Severity.WARN,
    ),
    (
        re.compile(r"style=\{\{"),
        "React inline style — CVA + Tailwind 사용 필수",
        Severity.WARN,
    ),
    (
        re.compile(r'<input[^>]+type=["\']number["\']', re.IGNORECASE),
        "input type=number — CJK IME 충돌. inputMode=numeric 사용",
        Severity.WARN,
    ),
    (
        re.compile(r"print\s*\((?!.*#\s*noqa)"),
        "print() 미삭제 — logger 사용 필수",
        Severity.WARN,
    ),
]

_TYPE_IGNORE_PATTERN = re.compile(r"#\s*type:\s*ignore")


def check_code_quality(text: str) -> list[Finding]:
    findings: list[Finding] = []
    type_ignore_count = 0

    for i, line in enumerate(text.splitlines(), start=1):
        for pattern, message, severity in _QUALITY_PATTERNS:
            if pattern.search(line):
                findings.append(
                    Finding(
                        hook="code-quality",
                        severity=severity,
                        message=message,
                        line=i,
                        snippet=line.strip()[:120],
                    )
                )
        if _TYPE_IGNORE_PATTERN.search(line):
            type_ignore_count += 1

    if type_ignore_count > 3:
        findings.append(
            Finding(
                hook="code-quality",
                severity=Severity.WARN,
                message=f"# type: ignore {type_ignore_count}회 — 과도한 타입 우회",
            )
        )

    return findings


# ---------------------------------------------------------------------------
# 7. auth-guard
# ---------------------------------------------------------------------------

# Credential key substring — case-insensitive (all patterns compiled with re.IGNORECASE).
# `auth` is anchored to prevent false positives on author*/authority* identifiers:
#   authToken, auth_key, auth-header, Authorization → match
#   authorName, authorId, authority → no match
_AUTH_STORAGE_KEY_RE = r"(?:token|jwt|auth(?:[_-]?(?:token|key|header)|orization\b)|bearer)"

_AUTH_FRONTEND_PATTERNS: list[tuple[re.Pattern[str], str, Severity]] = [
    (
        re.compile(
            rf"(?:localStorage|sessionStorage)\.setItem\s*\(\s*['\"][^'\"]*{_AUTH_STORAGE_KEY_RE}",
            re.IGNORECASE,
        ),
        "토큰 web storage 저장 — XSS 노출 위험. 메모리 변수 또는 httponly 쿠키 사용 필수 (LESSON-027)",
        Severity.BLOCK,
    ),
    (
        re.compile(
            rf"(?:localStorage|sessionStorage)\.getItem\s*\(\s*['\"][^'\"]*{_AUTH_STORAGE_KEY_RE}",
            re.IGNORECASE,
        ),
        "web storage에서 토큰 읽기 — localStorage/sessionStorage에 토큰 저장하지 말 것 (LESSON-027)",
        Severity.BLOCK,
    ),
]

# UserDefaults is scanned file-level (re.DOTALL) in check_auth_guard because Swift's
# labeled-argument convention often places `forKey:` on a separate line.
_USERDEFAULTS_TOKEN_RE = re.compile(
    rf"UserDefaults\b.*?forKey:\s*['\"][^'\"]*{_AUTH_STORAGE_KEY_RE}",
    re.IGNORECASE | re.DOTALL,
)

_AUTH_MOBILE_PATTERNS: list[tuple[re.Pattern[str], str, Severity]] = [
    (
        re.compile(
            rf"AsyncStorage\.setItem\s*\(\s*['\"][^'\"]*{_AUTH_STORAGE_KEY_RE}",
            re.IGNORECASE,
        ),
        "토큰 AsyncStorage 저장 — 평문 저장 위험. react-native-keychain 사용 필수 (LESSON-027)",
        Severity.BLOCK,
    ),
    (
        re.compile(
            rf"AsyncStorage\.getItem\s*\(\s*['\"][^'\"]*{_AUTH_STORAGE_KEY_RE}",
            re.IGNORECASE,
        ),
        "AsyncStorage에서 토큰 읽기 — AsyncStorage에 토큰 저장하지 말 것 (LESSON-027)",
        Severity.BLOCK,
    ),
    # Covers Android putString (SharedPreferences.Editor) and Flutter setString (shared_preferences pkg)
    (
        re.compile(
            rf"\.(?:set|put)String\s*\(\s*['\"][^'\"]*{_AUTH_STORAGE_KEY_RE}",
            re.IGNORECASE,
        ),
        "토큰 SharedPreferences/Prefs 저장 — EncryptedSharedPreferences 또는 Android Keystore 사용 필수 (LESSON-027)",
        Severity.BLOCK,
    ),
    # WARN only: .getString has no receiver anchor — Bundle/JSONObject/ResourceBundle all use it.
    (
        re.compile(
            rf"\.getString\s*\(\s*['\"][^'\"]*{_AUTH_STORAGE_KEY_RE}",
            re.IGNORECASE,
        ),
        "SharedPreferences에서 토큰 읽기 의심 — EncryptedSharedPreferences 사용 검토 (LESSON-027)",
        Severity.WARN,
    ),
]

_AUTH_BACKEND_PATTERNS: list[tuple[re.Pattern[str], str, Severity]] = [
    (
        re.compile(r"\bbody\.refresh_token\b"),
        "refresh_token body fallback — httponly 쿠키만 허용, body 수락 제거 필수 (LESSON-024)",
        Severity.BLOCK,
    ),
]

_REFRESH_BODY_SCHEMA_PATTERN = re.compile(
    r"class\s+\w*[Rr]efresh\w*\s*\([^)]*(?:Base)?[Mm]odel[^)]*\)[^:]*:\s*\n(?:\s+[^\n]+\n)*\s+refresh_token\s*:\s*str",
    re.MULTILINE,
)


def check_auth_guard(
    text: str, *, is_frontend: bool = False, is_mobile: bool = False
) -> list[Finding]:
    """Detect auth security anti-patterns: token storage, refresh fallback, logout no-op, race condition."""
    findings: list[Finding] = []
    lines = text.splitlines()

    if is_mobile:
        patterns = _AUTH_MOBILE_PATTERNS
    elif is_frontend:
        patterns = _AUTH_FRONTEND_PATTERNS
    else:
        patterns = _AUTH_BACKEND_PATTERNS
    for i, line in enumerate(lines, start=1):
        for pattern, message, severity in patterns:
            if pattern.search(line):
                findings.append(
                    Finding(
                        hook="auth-guard",
                        severity=severity,
                        message=message,
                        line=i,
                        snippet=line.strip()[:120],
                    )
                )

    # File-level: UserDefaults — Swift labeled args often split `forKey:` onto its own line,
    # so per-line scan misses canonical SwiftFormat style. DOTALL handles multi-line.
    if is_mobile and _USERDEFAULTS_TOKEN_RE.search(text):
        findings.append(
            Finding(
                hook="auth-guard",
                severity=Severity.BLOCK,
                message="토큰 UserDefaults 저장/읽기 — iOS Keychain Services 사용 필수 (LESSON-027)",
                snippet='UserDefaults … forKey: "*token/jwt/auth*"',
            )
        )

    if not is_frontend and not is_mobile:
        # File-level: RefreshRequest body schema with refresh_token field
        if _REFRESH_BODY_SCHEMA_PATTERN.search(text):
            findings.append(
                Finding(
                    hook="auth-guard",
                    severity=Severity.WARN,
                    message="RefreshRequest body schema에 refresh_token 포함 의심 — httponly 쿠키 전용 검토 (LESSON-024)",
                    snippet="class Refresh*(Model): refresh_token: str",
                )
            )

        # File-level: logout no-op — async def logout(...): \n    pass
        if re.search(
            r"async def logout\s*\([^)]*\)\s*(?:->\s*\w+\s*)?:\s*\n\s+pass\s*$",
            text,
            re.MULTILINE,
        ):
            findings.append(
                Finding(
                    hook="auth-guard",
                    severity=Severity.BLOCK,
                    message="logout() no-op (pass) — 서버에서 token_version 증가 또는 revocation table로 무효화 필수 (LESSON-023)",
                    snippet="async def logout(...): pass",
                )
            )

        # File-level: MAX()+1 without IntegrityError handling — only fires when a write
        # operation is present to avoid false positives on read-only aggregations.
        _has_write = re.search(
            r"\b(?:session|db)\.(?:add|add_all|merge|bulk_save_objects|bulk_insert_mappings)|INSERT\s+INTO",
            text,
        )
        if (
            _has_write
            and re.search(r"func\.max\s*\(", text)
            and not re.search(r"\bIntegrityError\b", text)
        ):
            findings.append(
                Finding(
                    hook="auth-guard",
                    severity=Severity.WARN,
                    message="MAX()+1 시퀀스 패턴 — IntegrityError 재시도 없음. unique constraint + retry 필수 (LESSON-025)",
                )
            )

    return findings


# ---------------------------------------------------------------------------
# 6. contract-validator
# ---------------------------------------------------------------------------

_ROUTE_PATTERN = re.compile(
    r'@(?:router|app)\.(get|post|put|patch|delete)\s*\(\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)


def check_contract_validator(
    text: str,
    allowed_endpoints: list[str] | None = None,
) -> list[Finding]:
    """Check for endpoints not declared in the skeleton.

    Args:
        text: agent output text.
        allowed_endpoints: whitelist of allowed endpoints (e.g. ``["GET /projects", "POST /issues"]``).
                           ``None`` performs pattern detection only (WARN).
    """
    findings: list[Finding] = []

    if allowed_endpoints is None:
        return findings

    allowed_set = {e.strip().upper() for e in allowed_endpoints}

    for i, line in enumerate(text.splitlines(), start=1):
        m = _ROUTE_PATTERN.search(line)
        if m:
            method = m.group(1).upper()
            path = m.group(2)
            key = f"{method} {path}"
            if key.upper() not in allowed_set:
                findings.append(
                    Finding(
                        hook="contract-validator",
                        severity=Severity.BLOCK,
                        message=f"skeleton에 없는 엔드포인트: {key}",
                        line=i,
                        snippet=line.strip()[:120],
                    )
                )

    return findings


# Aggregate runner


class SecurityHooks:
    """Run all seven security hooks in order.

    Harness v2: pass profile-derived whitelists at construction. Without
    arguments the module defaults are used (legacy compat).
    """

    def __init__(
        self,
        *,
        python_whitelist: set[str] | None = None,
        frontend_whitelist: set[str] | None = None,
        frontend_prefixes: tuple[str, ...] | None = None,
    ) -> None:
        self.python_whitelist = python_whitelist
        self.frontend_whitelist = frontend_whitelist
        self.frontend_prefixes = frontend_prefixes

    @classmethod
    def from_profile(cls, profile: object) -> SecurityHooks:
        """Build SecurityHooks from a ``profile_loader.Profile`` instance.

        Uses the union of ``whitelist.runtime`` + ``whitelist.dev``. The
        ``is_frontend`` branch is selected by the caller via ``run_all``.

        Note: do not reuse the same SecurityHooks instance for both backend
        and frontend — prefer one instance per profile.
        """
        wl_runtime = getattr(getattr(profile, "whitelist", None), "runtime", ())
        wl_dev = getattr(getattr(profile, "whitelist", None), "dev", ())
        wl_prefixes = getattr(getattr(profile, "whitelist", None), "prefix_allowed", ())
        combined: set[str] = set(wl_runtime) | set(wl_dev)
        return cls(
            python_whitelist=combined,
            frontend_whitelist=combined,
            frontend_prefixes=tuple(wl_prefixes),
        )

    def run_all(
        self,
        text: str,
        *,
        is_frontend: bool = False,
        is_mobile: bool = False,
        allowed_endpoints: list[str] | None = None,
    ) -> SecurityResult:
        """Run every security hook and return the aggregated result.

        Args:
            text: agent output text (code included).
            is_frontend: if True, use frontend dependency rules (web React/TS).
            is_mobile: if True, mobile context (RN/Flutter/native). 현재는 frontend
                와 동일 처리 (RN 의 TS imports 케이스). framework별 dep 룰 분기
                (Flutter Dart, Kotlin, Swift) 는 별도 확장 시 추가. is_frontend
                과 상호 배타 — 둘 중 하나만 True.
            allowed_endpoints: endpoints declared in the skeleton.
        """
        if is_frontend and is_mobile:
            raise ValueError("is_frontend and is_mobile are mutually exclusive")
        findings: list[Finding] = []
        findings.extend(check_secret_filter(text))
        findings.extend(check_command_guard(text))
        findings.extend(check_db_guard(text))
        findings.extend(
            check_dependency(
                text,
                # mobile 은 frontend dep 룰 사용 (TS/JS imports — RN 기준).
                # Flutter Dart / Kotlin / Swift 분기는 별도 확장 시 추가.
                is_frontend=is_frontend or is_mobile,
                python_whitelist=self.python_whitelist,
                frontend_whitelist=self.frontend_whitelist,
                frontend_prefixes=self.frontend_prefixes,
            )
        )
        findings.extend(check_code_quality(text))
        findings.extend(check_contract_validator(text, allowed_endpoints))
        findings.extend(check_auth_guard(text, is_frontend=is_frontend, is_mobile=is_mobile))
        return SecurityResult(findings=findings)
