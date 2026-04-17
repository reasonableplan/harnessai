"""검증 파이프라인 테스트."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

from src.orchestrator.pipeline import (
    CheckResult,
    CheckStatus,
    ValidationPipeline,
    ValidationResult,
)

# ---------------------------------------------------------------------------
# ValidationResult 단위 테스트
# ---------------------------------------------------------------------------


class TestValidationResultPassed:
    def test_all_passed_returns_true(self) -> None:
        result = ValidationResult(checks=[
            CheckResult(name="lint", status=CheckStatus.PASSED),
            CheckResult(name="typecheck", status=CheckStatus.PASSED),
            CheckResult(name="test", status=CheckStatus.PASSED),
        ])
        assert result.passed is True

    def test_one_failed_returns_false(self) -> None:
        result = ValidationResult(checks=[
            CheckResult(name="lint", status=CheckStatus.PASSED),
            CheckResult(name="typecheck", status=CheckStatus.FAILED, error="에러"),
            CheckResult(name="test", status=CheckStatus.PASSED),
        ])
        assert result.passed is False

    def test_skipped_only_returns_true(self) -> None:
        """SKIPPED는 실패가 아니므로 passed=True."""
        result = ValidationResult(checks=[
            CheckResult(name="lint", status=CheckStatus.SKIPPED),
            CheckResult(name="typecheck", status=CheckStatus.SKIPPED),
            CheckResult(name="test", status=CheckStatus.SKIPPED),
        ])
        assert result.passed is True

    def test_empty_checks_returns_true(self) -> None:
        assert ValidationResult().passed is True


class TestValidationResultSummary:
    def test_summary_format(self) -> None:
        result = ValidationResult(checks=[
            CheckResult(name="lint", status=CheckStatus.PASSED),
            CheckResult(name="typecheck", status=CheckStatus.FAILED, error="오류"),
            CheckResult(name="test", status=CheckStatus.SKIPPED),
        ])
        assert result.summary == "1 passed, 1 failed, 1 skipped"

    def test_summary_all_passed(self) -> None:
        result = ValidationResult(checks=[
            CheckResult(name="lint", status=CheckStatus.PASSED),
            CheckResult(name="test", status=CheckStatus.PASSED),
        ])
        assert result.summary == "2 passed, 0 failed, 0 skipped"

    def test_summary_empty(self) -> None:
        assert ValidationResult().summary == "0 passed, 0 failed, 0 skipped"


# ---------------------------------------------------------------------------
# ValidationPipeline._exec_check 테스트
# ---------------------------------------------------------------------------


class TestExecCheck:
    async def test_success(self, tmp_path: Path) -> None:
        """returncode=0이면 PASSED."""
        pipeline = ValidationPipeline(tmp_path)

        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"all good", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await pipeline._exec_check("lint:python", ["ruff", "check", "."])

        assert result.status == CheckStatus.PASSED
        assert result.output == "all good"
        assert result.error is None

    async def test_failure(self, tmp_path: Path) -> None:
        """returncode!=0이면 FAILED, stderr를 error에 담는다."""
        pipeline = ValidationPipeline(tmp_path)

        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"stdout msg", b"error detail"))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await pipeline._exec_check("lint:python", ["ruff", "check", "."])

        assert result.status == CheckStatus.FAILED
        assert result.output == "stdout msg"
        assert result.error == "error detail"

    async def test_timeout(self, tmp_path: Path) -> None:
        """communicate가 타임아웃 나면 FAILED + 타임아웃 메시지."""
        pipeline = ValidationPipeline(tmp_path)

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await pipeline._exec_check(
                "test:python", ["pytest", "-q"], timeout=5
            )

        assert result.status == CheckStatus.FAILED
        assert result.error is not None
        assert "5초" in result.error

    async def test_command_not_found(self, tmp_path: Path) -> None:
        """명령어가 없으면 SKIPPED."""
        pipeline = ValidationPipeline(tmp_path)

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("no such file"),
        ):
            result = await pipeline._exec_check("lint:python", ["ruff", "check", "."])

        assert result.status == CheckStatus.SKIPPED
        assert "ruff" in result.output

    async def test_failure_empty_stderr_gives_none_error(self, tmp_path: Path) -> None:
        """returncode!=0이지만 stderr가 비어있으면 error=None."""
        pipeline = ValidationPipeline(tmp_path)

        mock_proc = AsyncMock()
        mock_proc.returncode = 2
        mock_proc.communicate = AsyncMock(return_value=(b"output only", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await pipeline._exec_check("lint:python", ["ruff", "check", "."])

        assert result.status == CheckStatus.FAILED
        assert result.error is None


# ---------------------------------------------------------------------------
# ValidationPipeline._run_lint SKIPPED 조건 테스트
# ---------------------------------------------------------------------------


class TestRunLint:
    async def test_skipped_when_no_config_files(self, tmp_path: Path) -> None:
        """pyproject.toml / package.json 둘 다 없으면 SKIPPED."""
        pipeline = ValidationPipeline(tmp_path)
        result = await pipeline._run_lint()

        assert result.status == CheckStatus.SKIPPED
        assert result.name == "lint"

    async def test_python_lint_called_when_pyproject_exists(
        self, tmp_path: Path
    ) -> None:
        """pyproject.toml이 있으면 ruff 명령어로 _exec_check 호출."""
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n", encoding="utf-8")
        pipeline = ValidationPipeline(tmp_path)

        with patch.object(
            pipeline,
            "_exec_check",
            new_callable=AsyncMock,
            return_value=CheckResult(name="lint:python", status=CheckStatus.PASSED),
        ) as mock_exec:
            result = await pipeline._run_lint()

        mock_exec.assert_awaited_once_with("lint:python", ["ruff", "check", "."])
        assert result.status == CheckStatus.PASSED

    async def test_typescript_lint_called_when_package_json_exists(
        self, tmp_path: Path
    ) -> None:
        """package.json이 있으면 eslint 명령어로 _exec_check 호출."""
        (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
        pipeline = ValidationPipeline(tmp_path)

        with patch.object(
            pipeline,
            "_exec_check",
            new_callable=AsyncMock,
            return_value=CheckResult(
                name="lint:typescript", status=CheckStatus.PASSED
            ),
        ) as mock_exec:
            result = await pipeline._run_lint()

        mock_exec.assert_awaited_once_with(
            "lint:typescript", ["npx", "eslint", "."]
        )
        assert result.status == CheckStatus.PASSED


# ---------------------------------------------------------------------------
# ValidationPipeline.run_all 통합 테스트
# ---------------------------------------------------------------------------


class TestRunAll:
    async def test_run_all_collects_three_checks(self, tmp_path: Path) -> None:
        """run_all은 lint/typecheck/test 세 결과를 순서대로 반환."""
        pipeline = ValidationPipeline(tmp_path)

        lint_r = CheckResult(name="lint", status=CheckStatus.PASSED)
        type_r = CheckResult(name="typecheck", status=CheckStatus.SKIPPED)
        test_r = CheckResult(name="test", status=CheckStatus.PASSED)

        with (
            patch.object(
                pipeline, "_run_lint", new_callable=AsyncMock, return_value=lint_r
            ),
            patch.object(
                pipeline,
                "_run_typecheck",
                new_callable=AsyncMock,
                return_value=type_r,
            ),
            patch.object(
                pipeline, "_run_tests", new_callable=AsyncMock, return_value=test_r
            ),
        ):
            result = await pipeline.run_all()

        assert len(result.checks) == 3
        assert result.checks[0] is lint_r
        assert result.checks[1] is type_r
        assert result.checks[2] is test_r
        assert result.passed is True

    async def test_run_all_passed_false_when_one_fails(
        self, tmp_path: Path
    ) -> None:
        """하나라도 FAILED면 ValidationResult.passed=False."""
        pipeline = ValidationPipeline(tmp_path)

        with (
            patch.object(
                pipeline,
                "_run_lint",
                new_callable=AsyncMock,
                return_value=CheckResult(name="lint", status=CheckStatus.FAILED, error="x"),
            ),
            patch.object(
                pipeline,
                "_run_typecheck",
                new_callable=AsyncMock,
                return_value=CheckResult(name="typecheck", status=CheckStatus.PASSED),
            ),
            patch.object(
                pipeline,
                "_run_tests",
                new_callable=AsyncMock,
                return_value=CheckResult(name="test", status=CheckStatus.PASSED),
            ),
        ):
            result = await pipeline.run_all()

        assert result.passed is False
        assert result.summary == "2 passed, 1 failed, 0 skipped"
