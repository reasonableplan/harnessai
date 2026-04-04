"""보안 훅 — 에이전트 출력 코드에서 보안/품질 위반을 탐지한다."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum


class Severity(StrEnum):
    BLOCK = "BLOCK"  # 즉시 reject — merge 불가
    WARN = "WARN"    # 로그 기록 — 진행은 허용


@dataclass
class Finding:
    """개별 위반 탐지 결과."""

    hook: str
    severity: Severity
    message: str
    line: int = 0
    snippet: str = ""


@dataclass
class SecurityResult:
    """전체 보안 훅 실행 결과."""

    findings: list[Finding] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return any(f.severity == Severity.BLOCK for f in self.findings)

    @property
    def summary(self) -> str:
        blocks = [f for f in self.findings if f.severity == Severity.BLOCK]
        warns = [f for f in self.findings if f.severity == Severity.WARN]
        if not self.findings:
            return "보안 훅 통과"
        parts = []
        if blocks:
            parts.append(f"BLOCK {len(blocks)}건")
        if warns:
            parts.append(f"WARN {len(warns)}건")
        return " / ".join(parts)


# ---------------------------------------------------------------------------
# 화이트리스트 (conventions.md 기준)
# ---------------------------------------------------------------------------

_PYTHON_WHITELIST = {
    "fastapi", "uvicorn", "sqlmodel", "sqlalchemy", "alembic",
    "jose", "passlib", "bcrypt", "pydantic", "pydantic_settings",
    "httpx", "pytest", "pytest_asyncio", "asyncio", "typing",
    "pathlib", "dataclasses", "enum", "re", "json", "os", "sys",
    "datetime", "uuid", "logging", "functools", "itertools",
    "collections", "contextlib", "abc", "io", "time", "math",
    "hashlib", "hmac", "secrets", "base64", "urllib", "http",
    "email", "copy", "weakref", "threading", "multiprocessing",
    # 내부 모듈 허용
    "src", "__future__",
}

_FRONTEND_WHITELIST = {
    "react", "react-dom", "zustand", "axios",
    "tailwindcss", "postcss", "autoprefixer", "react-hook-form",
    "react-router-dom", "class-variance-authority",
    "clsx", "tailwind-merge", "lucide-react", "zod",
    # @radix-ui/* 접두사 처리는 별도
}

_FRONTEND_WHITELIST_PREFIXES = ("@radix-ui/",)


# ---------------------------------------------------------------------------
# 1. secret-filter
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r'(?:API_KEY|SECRET_KEY|PASSWORD|PASSWD|TOKEN|AUTH_TOKEN|ACCESS_KEY|PRIVATE_KEY)'
            r'\s*=\s*["\'][^"\']{8,}["\']',
            re.IGNORECASE,
        ),
        "하드코딩 시크릿 의심",
    ),
    (
        re.compile(r'(?:sk-|pk-|ghp_|gho_|github_pat_)[A-Za-z0-9_]{20,}'),
        "API 키 패턴 (OpenAI/GitHub)",
    ),
    (
        re.compile(r'(?:mysql|postgresql|postgres)://[^:]+:[^@]+@'),
        "DB 연결 문자열에 비밀번호 포함",
    ),
]


def check_secret_filter(text: str) -> list[Finding]:
    findings: list[Finding] = []
    for i, line in enumerate(text.splitlines(), start=1):
        for pattern, message in _SECRET_PATTERNS:
            m = pattern.search(line)
            if m:
                findings.append(Finding(
                    hook="secret-filter",
                    severity=Severity.BLOCK,
                    message=message,
                    line=i,
                    snippet=line.strip()[:120],
                ))
    return findings


# ---------------------------------------------------------------------------
# 2. command-guard
# ---------------------------------------------------------------------------

_COMMAND_PATTERNS: list[tuple[re.Pattern[str], str, Severity]] = [
    (
        re.compile(r'\brm\s+-[rf]{1,2}\s+/', re.IGNORECASE),
        "위험한 rm -rf 명령",
        Severity.BLOCK,
    ),
    (
        re.compile(r'\bcurl\b.+\|\s*(?:bash|sh)\b'),
        "curl | bash 패턴 — 원격 코드 실행 위험",
        Severity.BLOCK,
    ),
    (
        re.compile(r'\bwget\b.+\|\s*(?:bash|sh)\b'),
        "wget | bash 패턴 — 원격 코드 실행 위험",
        Severity.BLOCK,
    ),
    (
        re.compile(r'\beval\s*\('),
        "eval() 사용 — 코드 인젝션 위험",
        Severity.BLOCK,
    ),
    (
        re.compile(r'\bexec\s*\((?!.*#\s*noqa)'),
        "exec() 사용 — 코드 인젝션 위험",
        Severity.BLOCK,
    ),
    (
        re.compile(r'\bos\.system\s*\('),
        "os.system() 사용 — subprocess 사용 권장",
        Severity.WARN,
    ),
    (
        re.compile(r'\bDROP\s+(?:TABLE|DATABASE|SCHEMA)\b', re.IGNORECASE),
        "DROP 명령 — 데이터 파괴 위험",
        Severity.BLOCK,
    ),
    (
        re.compile(r'\bTRUNCATE\s+TABLE\b', re.IGNORECASE),
        "TRUNCATE TABLE — 데이터 파괴 위험",
        Severity.BLOCK,
    ),
]


def check_command_guard(text: str) -> list[Finding]:
    findings: list[Finding] = []
    for i, line in enumerate(text.splitlines(), start=1):
        for pattern, message, severity in _COMMAND_PATTERNS:
            if pattern.search(line):
                findings.append(Finding(
                    hook="command-guard",
                    severity=severity,
                    message=message,
                    line=i,
                    snippet=line.strip()[:120],
                ))
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
        # DELETE FROM table 뒤에 WHERE 없는 경우 (같은 라인 기준)
        re.compile(r'\bDELETE\s+FROM\s+\w+\s*(?:;|$)', re.IGNORECASE),
        "WHERE 없는 DELETE — 전체 행 삭제 위험",
        Severity.BLOCK,
    ),
    (
        re.compile(r'\bUPDATE\s+\w+\s+SET\b(?!.*WHERE)', re.IGNORECASE),
        "WHERE 없는 UPDATE 의심 — 전체 행 수정 위험",
        Severity.WARN,
    ),
]


def check_db_guard(text: str) -> list[Finding]:
    findings: list[Finding] = []
    for i, line in enumerate(text.splitlines(), start=1):
        for pattern, message, severity in _DB_PATTERNS:
            if pattern.search(line):
                findings.append(Finding(
                    hook="db-guard",
                    severity=severity,
                    message=message,
                    line=i,
                    snippet=line.strip()[:120],
                ))
    return findings


# ---------------------------------------------------------------------------
# 4. dependency-check
# ---------------------------------------------------------------------------

_PYTHON_IMPORT = re.compile(r'^(?:import|from)\s+([A-Za-z_][A-Za-z0-9_]*)', re.MULTILINE)
_FRONTEND_IMPORT = re.compile(r"""from\s+(?P<q>['"])(@?[^'"./][^'"]*)(?P=q)""")
_PIP_INSTALL = re.compile(r'\bpip\s+install\s+([A-Za-z0-9_\-]+)', re.IGNORECASE)
_NPM_INSTALL = re.compile(r'\bnpm\s+install\s+([A-Za-z0-9_\-@/]+)', re.IGNORECASE)


def check_dependency(text: str, *, is_frontend: bool = False) -> list[Finding]:
    findings: list[Finding] = []
    lines = text.splitlines()

    if not is_frontend:
        for i, line in enumerate(lines, start=1):
            m = _PYTHON_IMPORT.match(line.strip())
            if m:
                pkg = m.group(1).lower().replace("-", "_")
                if pkg not in _PYTHON_WHITELIST:
                    findings.append(Finding(
                        hook="dependency-check",
                        severity=Severity.WARN,
                        message=f"화이트리스트 외 패키지: {pkg} — Architect 승인 필요",
                        line=i,
                        snippet=line.strip()[:120],
                    ))
        # pip install 명령 탐지
        for i, line in enumerate(lines, start=1):
            for m in _PIP_INSTALL.finditer(line):
                pkg = m.group(1).lower()
                if pkg not in _PYTHON_WHITELIST:
                    findings.append(Finding(
                        hook="dependency-check",
                        severity=Severity.BLOCK,
                        message=f"승인 없는 pip install: {pkg}",
                        line=i,
                        snippet=line.strip()[:120],
                    ))
    else:
        for i, line in enumerate(lines, start=1):
            for m in _FRONTEND_IMPORT.finditer(line):
                pkg = m.group(2)
                allowed = (
                    pkg in _FRONTEND_WHITELIST
                    or any(pkg.startswith(p) for p in _FRONTEND_WHITELIST_PREFIXES)
                )
                if not allowed:
                    findings.append(Finding(
                        hook="dependency-check",
                        severity=Severity.WARN,
                        message=f"화이트리스트 외 패키지: {pkg} — Architect 승인 필요",
                        line=i,
                        snippet=line.strip()[:120],
                    ))
        # npm install 명령 탐지
        for i, line in enumerate(lines, start=1):
            for m in _NPM_INSTALL.finditer(line):
                pkg = m.group(1)
                allowed = (
                    pkg in _FRONTEND_WHITELIST
                    or any(pkg.startswith(p) for p in _FRONTEND_WHITELIST_PREFIXES)
                )
                if not allowed:
                    findings.append(Finding(
                        hook="dependency-check",
                        severity=Severity.BLOCK,
                        message=f"승인 없는 npm install: {pkg}",
                        line=i,
                        snippet=line.strip()[:120],
                    ))

    return findings


# ---------------------------------------------------------------------------
# 5. code-quality
# ---------------------------------------------------------------------------

_QUALITY_PATTERNS: list[tuple[re.Pattern[str], str, Severity]] = [
    (
        re.compile(r':\s*any\b'),
        "TypeScript any 타입 사용 — 타입 정의 필수",
        Severity.BLOCK,
    ),
    (
        re.compile(r'\bexcept\s*:\s*$'),
        "빈 except: — 최소한 logging 필수",
        Severity.BLOCK,
    ),
    (
        re.compile(r'\bconsole\.log\s*\('),
        "console.log 미삭제 — 프로덕션 코드에 부적합",
        Severity.WARN,
    ),
    (
        re.compile(r'style=\{\{'),
        "React inline style — CVA + Tailwind 사용 필수",
        Severity.WARN,
    ),
    (
        re.compile(r'<input[^>]+type=["\']number["\']', re.IGNORECASE),
        "input type=number — CJK IME 충돌. inputMode=numeric 사용",
        Severity.WARN,
    ),
    (
        re.compile(r'print\s*\((?!.*#\s*noqa)'),
        "print() 미삭제 — logger 사용 필수",
        Severity.WARN,
    ),
]

_TYPE_IGNORE_PATTERN = re.compile(r'#\s*type:\s*ignore')


def check_code_quality(text: str) -> list[Finding]:
    findings: list[Finding] = []
    type_ignore_count = 0

    for i, line in enumerate(text.splitlines(), start=1):
        for pattern, message, severity in _QUALITY_PATTERNS:
            if pattern.search(line):
                findings.append(Finding(
                    hook="code-quality",
                    severity=severity,
                    message=message,
                    line=i,
                    snippet=line.strip()[:120],
                ))
        if _TYPE_IGNORE_PATTERN.search(line):
            type_ignore_count += 1

    if type_ignore_count > 3:
        findings.append(Finding(
            hook="code-quality",
            severity=Severity.WARN,
            message=f"# type: ignore {type_ignore_count}회 — 과도한 타입 우회",
        ))

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
    """skeleton에 정의된 엔드포인트 외 추가 여부를 검사한다.

    Args:
        text: 에이전트 출력 텍스트
        allowed_endpoints: 허용된 엔드포인트 목록 (예: ["GET /projects", "POST /issues"])
                           None이면 패턴 탐지만 수행 (WARN)
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
                findings.append(Finding(
                    hook="contract-validator",
                    severity=Severity.BLOCK,
                    message=f"skeleton에 없는 엔드포인트: {key}",
                    line=i,
                    snippet=line.strip()[:120],
                ))

    return findings


# ---------------------------------------------------------------------------
# 통합 실행기
# ---------------------------------------------------------------------------

class SecurityHooks:
    """6개 보안 훅을 순서대로 실행한다."""

    def run_all(
        self,
        text: str,
        *,
        is_frontend: bool = False,
        allowed_endpoints: list[str] | None = None,
    ) -> SecurityResult:
        """모든 보안 훅을 실행하고 통합 결과를 반환한다.

        Args:
            text: 에이전트 출력 텍스트 (코드 포함)
            is_frontend: True이면 프론트엔드 의존성 규칙 적용
            allowed_endpoints: skeleton에 정의된 허용 엔드포인트 목록
        """
        findings: list[Finding] = []
        findings.extend(check_secret_filter(text))
        findings.extend(check_command_guard(text))
        findings.extend(check_db_guard(text))
        findings.extend(check_dependency(text, is_frontend=is_frontend))
        findings.extend(check_code_quality(text))
        findings.extend(check_contract_validator(text, allowed_endpoints))
        return SecurityResult(findings=findings)
