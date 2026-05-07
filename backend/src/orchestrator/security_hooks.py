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
    """Run all six security hooks in order.

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
        return SecurityResult(findings=findings)
