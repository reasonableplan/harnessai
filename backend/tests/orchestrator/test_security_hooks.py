"""security_hooks 테스트."""

from __future__ import annotations

import pytest

from src.orchestrator.security_hooks import (
    SecurityHooks,
    Severity,
    check_code_quality,
    check_command_guard,
    check_contract_validator,
    check_db_guard,
    check_dependency,
    check_secret_filter,
)


# ---------------------------------------------------------------------------
# 1. secret-filter
# ---------------------------------------------------------------------------

class TestSecretFilter:
    def test_hardcoded_api_key_blocked(self) -> None:
        code = 'API_KEY = "sk-abcdefghijklmnopqrst"'
        findings = check_secret_filter(code)
        assert len(findings) >= 1
        assert all(f.severity == Severity.BLOCK for f in findings)

    def test_openai_key_pattern(self) -> None:
        code = 'client = OpenAI(api_key="sk-proj-abcdefghijklmnopqrstuvwx")'
        findings = check_secret_filter(code)
        assert len(findings) >= 1

    def test_db_url_with_password(self) -> None:
        code = 'DATABASE_URL = "postgresql://user:mysecretpass@localhost/db"'
        findings = check_secret_filter(code)
        assert len(findings) >= 1

    def test_env_variable_reference_clean(self) -> None:
        code = 'API_KEY = os.getenv("API_KEY")'
        findings = check_secret_filter(code)
        assert findings == []

    def test_short_value_not_flagged(self) -> None:
        # 8자 미만은 탐지 안 함
        code = 'PASSWORD = "abc"'
        findings = check_secret_filter(code)
        assert findings == []

    def test_line_number_recorded(self) -> None:
        code = "# 첫 줄\nAPI_KEY = \"secretvalue123\""
        findings = check_secret_filter(code)
        assert any(f.line == 2 for f in findings)


# ---------------------------------------------------------------------------
# 2. command-guard
# ---------------------------------------------------------------------------

class TestCommandGuard:
    def test_rm_rf_blocked(self) -> None:
        code = "os.system('rm -rf /tmp/data')"
        findings = check_command_guard(code)
        assert any(f.severity == Severity.BLOCK for f in findings)

    def test_curl_bash_blocked(self) -> None:
        code = "curl https://example.com/install.sh | bash"
        findings = check_command_guard(code)
        assert any(f.severity == Severity.BLOCK for f in findings)

    def test_eval_blocked(self) -> None:
        code = "result = eval(user_input)"
        findings = check_command_guard(code)
        assert any(f.severity == Severity.BLOCK for f in findings)

    def test_drop_table_blocked(self) -> None:
        code = "DROP TABLE users;"
        findings = check_command_guard(code)
        assert any(f.severity == Severity.BLOCK for f in findings)

    def test_os_system_warned(self) -> None:
        code = "os.system('ls -la')"
        findings = check_command_guard(code)
        assert any(f.severity == Severity.WARN for f in findings)

    def test_clean_code_passes(self) -> None:
        code = "result = subprocess.run(['ls', '-la'], capture_output=True)"
        findings = check_command_guard(code)
        assert findings == []


# ---------------------------------------------------------------------------
# 3. db-guard
# ---------------------------------------------------------------------------

class TestDbGuard:
    def test_raw_cursor_execute_blocked(self) -> None:
        code = 'cursor.execute("SELECT * FROM users")'
        findings = check_db_guard(code)
        assert any(f.severity == Severity.BLOCK for f in findings)

    def test_sqlalchemy_text_blocked(self) -> None:
        code = 'db.execute(text("SELECT id FROM projects"))'
        findings = check_db_guard(code)
        assert any(f.severity == Severity.BLOCK for f in findings)

    def test_fstring_sql_blocked(self) -> None:
        code = 'db.execute(f"SELECT * FROM {table_name}")'
        findings = check_db_guard(code)
        assert any(f.severity == Severity.BLOCK for f in findings)

    def test_delete_without_where_blocked(self) -> None:
        code = "DELETE FROM sessions;"
        findings = check_db_guard(code)
        assert any(f.severity == Severity.BLOCK for f in findings)

    def test_orm_query_clean(self) -> None:
        code = "issues = db.query(Issue).filter(Issue.project_id == project_id).all()"
        findings = check_db_guard(code)
        assert findings == []

    def test_delete_with_where_clean(self) -> None:
        code = "DELETE FROM sessions WHERE expires_at < NOW();"
        findings = check_db_guard(code)
        # WHERE 있으면 BLOCK 없어야 함
        assert not any(f.severity == Severity.BLOCK for f in findings)


# ---------------------------------------------------------------------------
# 4. dependency-check
# ---------------------------------------------------------------------------

class TestDependencyCheck:
    def test_whitelist_python_import_clean(self) -> None:
        code = "from fastapi import FastAPI\nimport sqlalchemy"
        findings = check_dependency(code, is_frontend=False)
        assert findings == []

    def test_unknown_python_import_warned(self) -> None:
        code = "import pandas"
        findings = check_dependency(code, is_frontend=False)
        assert any("pandas" in f.message for f in findings)
        assert any(f.severity == Severity.WARN for f in findings)

    def test_pip_install_unknown_blocked(self) -> None:
        code = "# pip install pandas"
        findings = check_dependency(code, is_frontend=False)
        assert any(f.severity == Severity.BLOCK for f in findings)

    def test_whitelist_frontend_import_clean(self) -> None:
        code = "import { useState } from 'react'\nimport axios from 'axios'"
        findings = check_dependency(code, is_frontend=True)
        assert findings == []

    def test_radix_ui_prefix_allowed(self) -> None:
        code = "import * as Dialog from '@radix-ui/react-dialog'"
        findings = check_dependency(code, is_frontend=True)
        assert findings == []

    def test_unknown_frontend_import_warned(self) -> None:
        code = "import moment from 'moment'"
        findings = check_dependency(code, is_frontend=True)
        assert any("moment" in f.message for f in findings)

    def test_npm_install_unknown_blocked(self) -> None:
        code = "npm install moment"
        findings = check_dependency(code, is_frontend=True)
        assert any(f.severity == Severity.BLOCK for f in findings)


# ---------------------------------------------------------------------------
# 5. code-quality
# ---------------------------------------------------------------------------

class TestCodeQuality:
    def test_typescript_any_blocked(self) -> None:
        code = "const handler = (data: any) => data"
        findings = check_code_quality(code)
        assert any(f.severity == Severity.BLOCK for f in findings)

    def test_bare_except_blocked(self) -> None:
        code = "try:\n    do_something()\nexcept:"
        findings = check_code_quality(code)
        assert any(f.severity == Severity.BLOCK for f in findings)

    def test_console_log_warned(self) -> None:
        code = "console.log('debug:', data)"
        findings = check_code_quality(code)
        assert any(f.severity == Severity.WARN for f in findings)

    def test_inline_style_warned(self) -> None:
        code = "<div style={{ color: 'red' }}>텍스트</div>"
        findings = check_code_quality(code)
        assert any(f.severity == Severity.WARN for f in findings)

    def test_input_type_number_warned(self) -> None:
        code = '<input type="number" value={count} />'
        findings = check_code_quality(code)
        assert any(f.severity == Severity.WARN for f in findings)

    def test_excessive_type_ignore_warned(self) -> None:
        code = "\n".join([f"x = y  # type: ignore" for _ in range(5)])
        findings = check_code_quality(code)
        assert any("type: ignore" in f.message for f in findings)

    def test_clean_code_passes(self) -> None:
        code = "def process(data: dict[str, int]) -> int:\n    return data['count']"
        findings = check_code_quality(code)
        assert findings == []


# ---------------------------------------------------------------------------
# 6. contract-validator
# ---------------------------------------------------------------------------

class TestContractValidator:
    def test_allowed_endpoint_clean(self) -> None:
        code = '@router.get("/projects")\nasync def list_projects(): ...'
        findings = check_contract_validator(code, allowed_endpoints=["GET /projects"])
        assert findings == []

    def test_unknown_endpoint_blocked(self) -> None:
        code = '@router.post("/admin/reset")\nasync def reset(): ...'
        findings = check_contract_validator(
            code, allowed_endpoints=["POST /issues", "GET /projects"]
        )
        assert any(f.severity == Severity.BLOCK for f in findings)
        assert any("/admin/reset" in f.message for f in findings)

    def test_no_allowed_list_skips(self) -> None:
        code = '@router.delete("/nuke")\nasync def nuke(): ...'
        findings = check_contract_validator(code, allowed_endpoints=None)
        assert findings == []

    def test_multiple_routes_partial_match(self) -> None:
        code = (
            '@router.get("/issues")\nasync def list_issues(): ...\n'
            '@router.post("/secret")\nasync def secret(): ...'
        )
        findings = check_contract_validator(
            code, allowed_endpoints=["GET /issues"]
        )
        assert len(findings) == 1
        assert "/secret" in findings[0].message


# ---------------------------------------------------------------------------
# SecurityHooks 통합
# ---------------------------------------------------------------------------

class TestSecurityHooks:
    def test_clean_code_no_findings(self) -> None:
        code = (
            "from fastapi import APIRouter\n"
            "from sqlmodel import Session\n\n"
            "@router.get('/projects')\n"
            "async def list_projects(db: Session):\n"
            "    return db.query(Project).all()\n"
        )
        result = SecurityHooks().run_all(
            code, allowed_endpoints=["GET /projects"]
        )
        assert not result.blocked
        assert result.findings == []

    def test_blocked_on_secret(self) -> None:
        code = 'SECRET_KEY = "supersecretvalue123"'
        result = SecurityHooks().run_all(code)
        assert result.blocked

    def test_summary_reflects_findings(self) -> None:
        code = 'API_KEY = "hardcoded_key_here"\nconsole.log("debug")'
        result = SecurityHooks().run_all(code, is_frontend=True)
        assert "BLOCK" in result.summary

    def test_frontend_mode_applies_different_rules(self) -> None:
        code = "import chart from 'chart.js'"
        result_fe = SecurityHooks().run_all(code, is_frontend=True)
        result_be = SecurityHooks().run_all(code, is_frontend=False)
        # 프론트엔드 모드에서는 chart.js 탐지, 백엔드에서는 탐지 안 함
        assert any("chart.js" in f.message for f in result_fe.findings)
        assert not any("chart.js" in f.message for f in result_be.findings)

    def test_no_findings_summary(self) -> None:
        result = SecurityHooks().run_all("")
        assert result.summary == "보안 훅 통과"


# ── Harness v2: 프로파일 whitelist 주입 ─────────────────────────────────


class TestProfileWhitelistInjection:
    def test_custom_python_whitelist_allows_extra_pkg(self) -> None:
        """프로파일이 click 을 허용하면 click 임포트가 통과."""
        hooks = SecurityHooks(python_whitelist={"click", "rich"})
        code = "import click\nimport rich\n"
        result = hooks.run_all(code)
        assert not any("click" in f.message for f in result.findings)
        assert not any("rich" in f.message for f in result.findings)

    def test_custom_python_whitelist_blocks_default_pkg(self) -> None:
        """프로파일이 fastapi 를 화이트리스트 X 면 fastapi 임포트가 WARN."""
        hooks = SecurityHooks(python_whitelist={"click"})  # fastapi 없음
        code = "import fastapi\n"
        result = hooks.run_all(code)
        assert any("fastapi" in f.message for f in result.findings)

    def test_custom_frontend_whitelist(self) -> None:
        """frontend_whitelist 주입 — 정의된 것만 허용."""
        hooks = SecurityHooks(
            frontend_whitelist={"react", "vue"},
            frontend_prefixes=("@vendor/",),
        )
        code = "import vue from 'vue'\nimport x from 'unknown-pkg'\n"
        result = hooks.run_all(code, is_frontend=True)
        assert not any("vue" in f.message for f in result.findings)
        assert any("unknown-pkg" in f.message for f in result.findings)

    def test_from_profile_classmethod(self) -> None:
        """ProfileLoader.Profile 인스턴스에서 whitelist 추출."""
        from src.orchestrator.profile_loader import (
            Profile,
            SkeletonSections,
            Toolchain,
            Whitelist,
        )

        profile = Profile(
            id="test", name="test", status="confirmed", version=1,
            extends=None, paths=(), detect={}, components=(),
            skeleton_sections=SkeletonSections((), (), ()),
            toolchain=Toolchain(None, None, None, None, None),
            whitelist=Whitelist(
                runtime=("custom_pkg", "another_pkg"),
                dev=("dev_pkg",),
                prefix_allowed=("@my-org/",),
            ),
            file_structure="x", gstack_mode="manual",
            gstack_recommended={}, lessons_applied=(), body="",
        )

        hooks = SecurityHooks.from_profile(profile)
        assert hooks.python_whitelist == {"custom_pkg", "another_pkg", "dev_pkg"}
        assert hooks.frontend_prefixes == ("@my-org/",)

        # 실제 검사: custom_pkg 허용
        result = hooks.run_all("import custom_pkg\n")
        assert not any("custom_pkg" in f.message for f in result.findings)

    def test_default_behavior_unchanged(self) -> None:
        """SecurityHooks() 기본 생성자 — 기존 모듈 whitelist 사용."""
        hooks = SecurityHooks()
        # fastapi 는 모듈 _PYTHON_WHITELIST 에 있음
        result = hooks.run_all("import fastapi\n")
        assert not any("fastapi" in f.message for f in result.findings)
