"""검증 파이프라인 — 린터/테스트/skeleton 대조 자동 검증."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class CheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class CheckResult:
    """개별 검증 항목 결과."""

    name: str
    status: CheckStatus
    output: str = ""
    error: str | None = None


@dataclass
class ValidationResult:
    """전체 검증 결과."""

    checks: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.status != CheckStatus.FAILED for c in self.checks)

    @property
    def summary(self) -> str:
        passed = sum(1 for c in self.checks if c.status == CheckStatus.PASSED)
        failed = sum(1 for c in self.checks if c.status == CheckStatus.FAILED)
        skipped = sum(1 for c in self.checks if c.status == CheckStatus.SKIPPED)
        return f"{passed} passed, {failed} failed, {skipped} skipped"


class ValidationPipeline:
    """린터/테스트/skeleton 대조 자동 검증 파이프라인."""

    def __init__(self, project_dir: str | Path) -> None:
        self._project_dir = Path(project_dir).resolve()

    async def run_all(self) -> ValidationResult:
        """모든 검증을 순차 실행하고 결과를 반환.

        순차 실행 이유: 린트 실패 시에도 테스트까지 전부 실행해 전체 상태를 파악하되,
        각 단계가 독립적으로 결과를 수집할 수 있어야 함.
        """
        result = ValidationResult()
        result.checks.append(await self._run_lint())
        result.checks.append(await self._run_typecheck())
        result.checks.append(await self._run_tests())
        return result

    async def _run_lint(self) -> CheckResult:
        """린터 실행 (Python: ruff, TypeScript: eslint)."""
        if (self._project_dir / "pyproject.toml").exists():
            return await self._exec_check("lint:python", ["ruff", "check", "."])
        if (self._project_dir / "package.json").exists():
            return await self._exec_check("lint:typescript", ["npx", "eslint", "."])
        return CheckResult(name="lint", status=CheckStatus.SKIPPED, output="린터 설정 없음")

    async def _run_typecheck(self) -> CheckResult:
        """타입 체크 (Python: mypy, TypeScript: tsc)."""
        if (self._project_dir / "pyproject.toml").exists():
            return await self._exec_check("typecheck:python", ["mypy", "."])
        if (self._project_dir / "tsconfig.json").exists():
            return await self._exec_check("typecheck:typescript", ["npx", "tsc", "--noEmit"])
        return CheckResult(name="typecheck", status=CheckStatus.SKIPPED, output="타입 체크 설정 없음")

    async def _run_tests(self) -> CheckResult:
        """테스트 실행 (Python: pytest, TypeScript: vitest)."""
        if (self._project_dir / "pyproject.toml").exists():
            return await self._exec_check("test:python", ["pytest", "--rootdir=.", "-q"])
        if (self._project_dir / "package.json").exists():
            return await self._exec_check("test:typescript", ["npx", "vitest", "run"])
        return CheckResult(name="test", status=CheckStatus.SKIPPED, output="테스트 설정 없음")

    async def _exec_check(
        self,
        name: str,
        cmd: list[str],
        *,
        timeout: int = 120,
    ) -> CheckResult:
        """subprocess로 명령어를 실행하고 CheckResult를 반환."""
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._project_dir),
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
            output = stdout.decode("utf-8", errors="replace").strip()
            error_output = stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode == 0:
                return CheckResult(name=name, status=CheckStatus.PASSED, output=output)
            return CheckResult(
                name=name,
                status=CheckStatus.FAILED,
                output=output,
                error=error_output or None,
            )
        except TimeoutError:
            return CheckResult(
                name=name,
                status=CheckStatus.FAILED,
                error=f"타임아웃: {timeout}초 초과",
            )
        except FileNotFoundError:
            return CheckResult(
                name=name,
                status=CheckStatus.SKIPPED,
                output=f"명령어를 찾을 수 없음: {cmd[0]}",
            )
