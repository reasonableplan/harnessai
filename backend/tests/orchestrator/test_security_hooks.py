"""security_hooks 테스트."""

from __future__ import annotations

from src.orchestrator.security_hooks import (
    SecurityHooks,
    Severity,
    check_auth_guard,
    check_code_quality,
    check_command_guard,
    check_contract_validator,
    check_db_guard,
    check_dependency,
    check_secret_filter,
    detect_local_packages,
    strip_doc_files_from_diff,
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
        code = '# 첫 줄\nAPI_KEY = "secretvalue123"'
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

    def test_print_warned_by_default(self) -> None:
        code = "print('debug:', data)"
        findings = check_code_quality(code)
        assert any("print()" in f.message for f in findings)

    def test_print_allowed_when_stdout_is_output_channel(self) -> None:
        """CLI/skill 프로파일: print 는 정당한 출력 채널 → WARN 억제 (dogfood #10)."""
        code = "print('result')\nprint('[error] bad', file=sys.stderr)"
        findings = check_code_quality(code, allow_stdout_print=True)
        assert not any("print()" in f.message for f in findings)

    def test_print_allow_does_not_leak_other_rules(self) -> None:
        """allow_stdout_print 는 print 만 억제 — 빈 except 등 다른 룰은 유지."""
        code = "try:\n    x()\nexcept:\n    print('swallow')"
        findings = check_code_quality(code, allow_stdout_print=True)
        assert any(f.severity == Severity.BLOCK for f in findings)  # bare except 유지
        assert not any("print()" in f.message for f in findings)

    def test_excessive_type_ignore_warned(self) -> None:
        code = "\n".join(["x = y  # type: ignore" for _ in range(5)])
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
        findings = check_contract_validator(code, allowed_endpoints=["GET /issues"])
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
        result = SecurityHooks().run_all(code, allowed_endpoints=["GET /projects"])
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
        assert result.summary == "security hooks passed"


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
            id="test",
            name="test",
            status="confirmed",
            version=1,
            extends=None,
            paths=(),
            detect={},
            components=(),
            skeleton_sections=SkeletonSections((), (), ()),
            toolchain=Toolchain(None, None, None, None, None),
            whitelist=Whitelist(
                runtime=("custom_pkg", "another_pkg"),
                dev=("dev_pkg",),
                prefix_allowed=("@my-org/",),
            ),
            file_structure="x",
            gstack_mode="manual",
            gstack_recommended={},
            lessons_applied=(),
            body="",
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


# ---------------------------------------------------------------------------
# is_mobile flag
# ---------------------------------------------------------------------------


class TestIsMobileFlag:
    """is_mobile 플래그. 현재는 frontend 와 동일한 dep 룰 (RN TS imports)."""

    def test_is_mobile_alone_uses_frontend_dep_rules(self) -> None:
        """is_mobile=True 단독 → check_dependency 가 frontend 모드 (Python imports 무시)."""
        hooks = SecurityHooks()
        # Python import 는 frontend 모드에서 검사 안 함 (TS/JS imports 만 검사)
        # 모바일 코드에 가상의 Python 라인이 있어도 dep 위반으로 잡히지 않아야 함
        result = hooks.run_all(
            "import some_unknown_python_pkg\n",
            is_mobile=True,
        )
        # Python pkg 가 dep finding 에 없어야 함 (frontend/mobile 모드 → Python skip)
        assert not any(
            "some_unknown_python_pkg" in f.message
            for f in result.findings
            if f.hook == "dependency-check"
        )

    def test_is_frontend_and_is_mobile_mutually_exclusive(self) -> None:
        """is_frontend + is_mobile 둘 다 True 시 ValueError — 호출자 의도 확인 강제."""
        hooks = SecurityHooks()
        try:
            hooks.run_all("x", is_frontend=True, is_mobile=True)
        except ValueError as exc:
            assert "mutually exclusive" in str(exc)
        else:
            raise AssertionError("ValueError 가 발생해야 함")

    def test_default_no_mobile(self) -> None:
        """is_mobile 미지정 시 기본 False — 기존 backend 동작 유지."""
        hooks = SecurityHooks()
        result = hooks.run_all("print('x')\n")
        # 기본은 backend 모드. ValueError 안 나야 함.
        assert isinstance(result.findings, list)


# ---------------------------------------------------------------------------
# auth-guard (LESSON-022~027)
# ---------------------------------------------------------------------------


class TestAuthGuard:
    def test_frontend_localstorage_access_token_blocked(self) -> None:
        """localStorage에 accessToken 저장 시도 → BLOCK (LESSON-027)."""
        code = "localStorage.setItem('accessToken', token);"
        findings = check_auth_guard(code, is_frontend=True)
        assert any(f.severity == Severity.BLOCK for f in findings)
        assert any("web storage" in f.message for f in findings)

    def test_frontend_localstorage_refreshtoken_blocked(self) -> None:
        """localStorage에 refreshToken 저장도 BLOCK."""
        code = 'localStorage.setItem("refreshToken", data.refresh);'
        findings = check_auth_guard(code, is_frontend=True)
        assert any(f.severity == Severity.BLOCK for f in findings)

    def test_frontend_localstorage_getitem_token_blocked(self) -> None:
        """localStorage.getItem with token keyword → BLOCK."""
        code = "const t = localStorage.getItem('accessToken');"
        findings = check_auth_guard(code, is_frontend=True)
        assert any(f.severity == Severity.BLOCK for f in findings)

    def test_frontend_clean_code_passes(self) -> None:
        """localStorage 없는 프론트엔드 코드 → 통과."""
        code = "const [token, setToken] = useState<string | null>(null);"
        findings = check_auth_guard(code, is_frontend=True)
        assert findings == []

    def test_backend_refresh_body_fallback_blocked(self) -> None:
        """refresh_token body fallback → BLOCK (LESSON-024)."""
        code = "token = refresh_token_cookie or (body.refresh_token if body else None)"
        findings = check_auth_guard(code, is_frontend=False)
        assert any(f.severity == Severity.BLOCK for f in findings)
        assert any("body" in f.message.lower() or "cookie" in f.message.lower() for f in findings)

    def test_backend_refresh_request_schema_warns(self) -> None:
        """RefreshRequest body 스키마에 refresh_token 필드 → WARN (heuristic — LESSON-024)."""
        code = "class RefreshRequest(BaseModel):\n    refresh_token: str\n"
        findings = check_auth_guard(code, is_frontend=False)
        assert any(f.severity == Severity.WARN and "refresh_token" in f.snippet for f in findings)

    def test_backend_logout_noop_blocked(self) -> None:
        """logout() 본문이 pass 뿐인 no-op → BLOCK (LESSON-023)."""
        code = "async def logout(self, *, db: AsyncSession, user: User) -> None:\n    pass\n"
        findings = check_auth_guard(code, is_frontend=False)
        assert any(f.severity == Severity.BLOCK and "logout" in f.message.lower() for f in findings)

    def test_backend_logout_with_implementation_passes(self) -> None:
        """token_version 증가 있는 logout → 통과."""
        code = (
            "async def logout(self, *, db: AsyncSession, user: User) -> None:\n"
            "    user.token_version = (user.token_version or 0) + 1\n"
            "    db.add(user)\n"
            "    await db.commit()\n"
        )
        findings = check_auth_guard(code, is_frontend=False)
        block_findings = [
            f for f in findings if f.severity == Severity.BLOCK and "logout" in f.message.lower()
        ]
        assert block_findings == []

    def test_backend_max_plus_one_without_integrity_error_warns(self) -> None:
        """func.max() + session.add() 조합에서 IntegrityError 처리 없음 → WARN (LESSON-025)."""
        code = (
            "max_result = await db.execute(select(func.max(Scene.scene_number)))\n"
            "scene_number = (max_result.scalar_one_or_none() or 0) + 1\n"
            "db.add(Scene(scene_number=scene_number))\n"
            "await db.commit()\n"
        )
        findings = check_auth_guard(code, is_frontend=False)
        assert any(f.severity == Severity.WARN and "IntegrityError" in f.message for f in findings)

    def test_backend_max_plus_one_readonly_passes(self) -> None:
        """func.max() 단독 조회 (쓰기 없음) → WARN 미발생 (false positive 방지)."""
        code = (
            "result = await db.execute(select(func.max(Order.order_id)))\n"
            "max_id = result.scalar_one_or_none()\n"
        )
        findings = check_auth_guard(code, is_frontend=False)
        warn_findings = [
            f for f in findings if f.severity == Severity.WARN and "IntegrityError" in f.message
        ]
        assert warn_findings == []

    def test_backend_max_plus_one_with_integrity_error_passes(self) -> None:
        """func.max() + session.add() + IntegrityError retry 패턴 → WARN 미발생."""
        code = (
            "from sqlalchemy.exc import IntegrityError\n"
            "max_result = await db.execute(select(func.max(Scene.scene_number)))\n"
            "seq = (max_result.scalar_one_or_none() or 0) + 1\n"
            "session.add(Scene(scene_number=seq))\n"
            "except IntegrityError:\n"
            "    await db.rollback()\n"
        )
        findings = check_auth_guard(code, is_frontend=False)
        warn_findings = [
            f for f in findings if f.severity == Severity.WARN and "IntegrityError" in f.message
        ]
        assert warn_findings == []

    def test_backend_clean_code_passes(self) -> None:
        """인증 패턴 없는 일반 백엔드 코드 → 통과."""
        code = (
            "async def get_user(db: AsyncSession, user_id: int) -> User | None:\n"
            "    result = await db.execute(select(User).where(User.id == user_id))\n"
            "    return result.scalar_one_or_none()\n"
        )
        findings = check_auth_guard(code, is_frontend=False)
        assert findings == []

    # --- frontend: sessionStorage + extended key names ---

    def test_frontend_sessionstorage_jwt_blocked(self) -> None:
        """sessionStorage에 jwt 키로 저장 → BLOCK (LESSON-027)."""
        code = "sessionStorage.setItem('jwt', accessToken);"
        findings = check_auth_guard(code, is_frontend=True)
        assert any(f.severity == Severity.BLOCK for f in findings)

    def test_frontend_localstorage_auth_key_blocked(self) -> None:
        """localStorage에 auth 키로 저장 → BLOCK (LESSON-027)."""
        code = "localStorage.setItem('authHeader', token);"
        findings = check_auth_guard(code, is_frontend=True)
        assert any(f.severity == Severity.BLOCK for f in findings)

    def test_frontend_localstorage_bearer_key_blocked(self) -> None:
        """localStorage에 Bearer 키로 저장 → BLOCK (LESSON-027)."""
        code = "localStorage.setItem('Bearer', value);"
        findings = check_auth_guard(code, is_frontend=True)
        assert any(f.severity == Severity.BLOCK for f in findings)

    # --- mobile patterns ---

    def test_mobile_asyncstorage_token_blocked(self) -> None:
        """AsyncStorage.setItem with token key → BLOCK (LESSON-027)."""
        code = "await AsyncStorage.setItem('accessToken', token);"
        findings = check_auth_guard(code, is_mobile=True)
        assert any(f.severity == Severity.BLOCK for f in findings)

    def test_mobile_asyncstorage_jwt_blocked(self) -> None:
        """AsyncStorage.getItem with JWT key → BLOCK (LESSON-027)."""
        code = "const token = await AsyncStorage.getItem('JWT_TOKEN');"
        findings = check_auth_guard(code, is_mobile=True)
        assert any(f.severity == Severity.BLOCK for f in findings)

    def test_mobile_shared_prefs_token_blocked(self) -> None:
        """SharedPreferences.putString with token key → BLOCK (LESSON-027)."""
        code = 'prefs.putString("accessToken", token);'
        findings = check_auth_guard(code, is_mobile=True)
        assert any(f.severity == Severity.BLOCK for f in findings)

    def test_mobile_userdefaults_token_blocked(self) -> None:
        """UserDefaults.set forKey token → BLOCK (LESSON-027)."""
        code = 'UserDefaults.standard.set(token, forKey: "authToken")'
        findings = check_auth_guard(code, is_mobile=True)
        assert any(f.severity == Severity.BLOCK for f in findings)

    def test_mobile_clean_code_passes(self) -> None:
        """토큰 저장 없는 모바일 코드 → 통과."""
        code = 'let username = UserDefaults.standard.string(forKey: "username")'
        findings = check_auth_guard(code, is_mobile=True)
        assert findings == []

    def test_mobile_backend_patterns_not_applied(self) -> None:
        """is_mobile=True → 백엔드 전용 패턴(logout no-op 등) 미적용."""
        code = "async def logout(request):\n    pass\n"
        findings = check_auth_guard(code, is_mobile=True)
        block_logout = [f for f in findings if "logout" in f.message.lower()]
        assert block_logout == []

    # --- ALL_CAPS key coverage ---

    def test_frontend_localstorage_caps_access_token_blocked(self) -> None:
        """localStorage.setItem with ACCESS_TOKEN (ALL_CAPS) → BLOCK (re.IGNORECASE)."""
        code = "localStorage.setItem('ACCESS_TOKEN', token);"
        findings = check_auth_guard(code, is_frontend=True)
        assert any(f.severity == Severity.BLOCK for f in findings)

    def test_frontend_localstorage_auth_header_caps_blocked(self) -> None:
        """localStorage.setItem with AUTH_HEADER key → BLOCK."""
        code = "localStorage.setItem('AUTH_HEADER', value);"
        findings = check_auth_guard(code, is_frontend=True)
        assert any(f.severity == Severity.BLOCK for f in findings)

    # --- author* false-positive regression ---

    def test_frontend_localstorage_author_key_passes(self) -> None:
        """localStorage.setItem with authorName key → no BLOCK (author* 오탐 방지)."""
        code = "localStorage.setItem('authorName', name);"
        findings = check_auth_guard(code, is_frontend=True)
        assert not any(f.severity == Severity.BLOCK for f in findings)

    def test_mobile_bundle_author_passes(self) -> None:
        """bundle.getString('authorId') → no BLOCK (author* 오탐 방지)."""
        code = 'bundle.getString("authorId")'
        findings = check_auth_guard(code, is_mobile=True)
        assert not any(f.severity == Severity.BLOCK for f in findings)

    # --- Flutter setString coverage ---

    def test_mobile_flutter_set_string_token_blocked(self) -> None:
        """Flutter prefs.setString with token key → BLOCK (LESSON-027)."""
        code = "await prefs.setString('authToken', token);"
        findings = check_auth_guard(code, is_mobile=True)
        assert any(f.severity == Severity.BLOCK for f in findings)

    # --- .getString severity (WARN, not BLOCK) ---

    def test_mobile_getstring_token_warns_not_blocks(self) -> None:
        """prefs.getString('accessToken') → WARN only (receiver-unanchored heuristic)."""
        code = 'prefs.getString("accessToken")'
        findings = check_auth_guard(code, is_mobile=True)
        assert any(f.severity == Severity.WARN for f in findings)
        assert not any(
            f.severity == Severity.BLOCK and "getString" in (f.snippet or "") for f in findings
        )

    # --- UserDefaults multi-line (Swift labeled arg style) ---

    def test_mobile_userdefaults_multiline_blocked(self) -> None:
        """UserDefaults multi-line Swift call → BLOCK (file-level DOTALL scan)."""
        code = 'UserDefaults.standard.set(\n    token,\n    forKey: "authToken"\n)'
        findings = check_auth_guard(code, is_mobile=True)
        assert any(f.severity == Severity.BLOCK for f in findings)

    # --- bulk_save_objects MAX()+1 ---

    def test_backend_max_bulk_save_objects_warns(self) -> None:
        """func.max() + bulk_save_objects 조합 → WARN (LESSON-025)."""
        code = (
            "max_result = await db.execute(select(func.max(Item.id)))\n"
            "next_id = (max_result.scalar_one_or_none() or 0) + 1\n"
            "session.bulk_save_objects([Item(id=next_id)])\n"
        )
        findings = check_auth_guard(code, is_frontend=False)
        assert any(f.severity == Severity.WARN and "IntegrityError" in f.message for f in findings)

    def test_hook_name_is_auth_guard(self) -> None:
        """finding.hook 이름이 'auth-guard'인지 확인."""
        code = "localStorage.setItem('accessToken', t);"
        findings = check_auth_guard(code, is_frontend=True)
        assert all(f.hook == "auth-guard" for f in findings)

    def test_run_all_includes_auth_guard(self) -> None:
        """SecurityHooks.run_all()이 auth-guard를 포함하는지 통합 확인."""
        hooks = SecurityHooks()
        code = "localStorage.setItem('accessToken', token);"
        result = hooks.run_all(code, is_frontend=True)
        auth_findings = [f for f in result.findings if f.hook == "auth-guard"]
        assert len(auth_findings) > 0


# ---------------------------------------------------------------------------
# LESSON-030: doc-diff exclusion + stdlib/self-package dependency FP
# ---------------------------------------------------------------------------


_MD_DIFF_BLOCK = (
    "diff --git a/backend/docs/harness-plan.md b/backend/docs/harness-plan.md\n"
    "--- a/backend/docs/harness-plan.md\n"
    "+++ b/backend/docs/harness-plan.md\n"
    "+  rationale: external eval (matching rate 50%) remains manual\n"
    "+  print('inline SKILL.md example')\n"
)

_PY_DIFF_BLOCK = (
    "diff --git a/backend/src/app.py b/backend/src/app.py\n"
    "--- a/backend/src/app.py\n"
    "+++ b/backend/src/app.py\n"
    "+result = eval(user_input)\n"
)


class TestStripDocFilesFromDiff:
    def test_md_block_removed_py_block_kept(self) -> None:
        stripped = strip_doc_files_from_diff(_MD_DIFF_BLOCK + _PY_DIFF_BLOCK)
        assert "harness-plan.md" not in stripped
        assert "external eval (" not in stripped
        assert "eval(user_input)" in stripped

    def test_rst_and_txt_removed(self) -> None:
        diff = (
            "diff --git a/README.rst b/README.rst\n+eval(x)\n"
            "diff --git a/notes.txt b/notes.txt\n+eval(y)\n"
        )
        assert strip_doc_files_from_diff(diff) == ""

    def test_docs_and_templates_paths_removed(self) -> None:
        diff = (
            "diff --git a/docs/guide.py b/docs/guide.py\n+eval(x)\n"
            "diff --git a/harness/templates/frag.py b/harness/templates/frag.py\n+eval(y)\n"
        )
        assert strip_doc_files_from_diff(diff) == ""

    def test_empty_diff_passthrough(self) -> None:
        assert strip_doc_files_from_diff("") == ""

    def test_command_guard_no_block_after_strip(self) -> None:
        """실전 FP 재현: harness-plan.md rationale 의 'external eval (' → BLOCK 0."""
        stripped = strip_doc_files_from_diff(_MD_DIFF_BLOCK)
        assert check_command_guard(stripped) == []


class TestDetectLocalPackages:
    def test_monorepo_src_layout(self, tmp_path) -> None:
        """code-hijack 실레이아웃: <project>/backend/src/hijack/__init__.py."""
        pkg = tmp_path / "backend" / "src" / "hijack"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        assert "hijack" in detect_local_packages(tmp_path)

    def test_root_and_src_layouts(self, tmp_path) -> None:
        for rel in ("mypkg", "src/otherpkg"):
            d = tmp_path / rel
            d.mkdir(parents=True)
            (d / "__init__.py").write_text("", encoding="utf-8")
        pkgs = detect_local_packages(tmp_path)
        assert {"mypkg", "otherpkg"} <= pkgs

    def test_skip_dirs_and_plain_dirs_excluded(self, tmp_path) -> None:
        noise = tmp_path / "node_modules" / "leftpad"
        noise.mkdir(parents=True)
        (noise / "__init__.py").write_text("", encoding="utf-8")
        (tmp_path / "no_init_dir").mkdir()
        assert detect_local_packages(tmp_path) == frozenset()

    def test_missing_project_dir(self, tmp_path) -> None:
        assert detect_local_packages(tmp_path / "nope") == frozenset()


class TestDependencyStdlibAndExtraAllowed:
    def test_stdlib_imports_not_warned(self) -> None:
        """LESSON-030: tomllib/pathlib 등 stdlib 은 외부 의존성 아님."""
        code = "import tomllib\nfrom pathlib import Path\nimport sqlite3"
        assert check_dependency(code, is_frontend=False) == []

    def test_self_package_allowed_via_extra(self) -> None:
        code = "from hijack import analyzer"
        assert check_dependency(code, extra_allowed={"hijack"}) == []

    def test_self_package_warned_without_extra(self) -> None:
        code = "from hijack import analyzer"
        findings = check_dependency(code)
        assert any("hijack" in f.message for f in findings)

    def test_unknown_package_still_warned_with_extra(self) -> None:
        code = "import pandas"
        findings = check_dependency(code, extra_allowed={"hijack"})
        assert any("pandas" in f.message for f in findings)

    def test_pip_install_self_package_still_blocked(self) -> None:
        """extra_allowed 는 import 스캔만 — pip install 자기 패키지는 여전히 BLOCK."""
        code = "pip install hijack"
        findings = check_dependency(code, extra_allowed={"hijack"})
        assert any(f.severity == Severity.BLOCK for f in findings)

    def test_run_all_passes_extra_python_allowed(self) -> None:
        hooks = SecurityHooks(extra_python_allowed=frozenset({"hijack"}))
        result = hooks.run_all("from hijack import analyzer")
        assert [f for f in result.findings if f.hook == "dependency-check"] == []

    def test_from_profile_passes_extra_python_allowed(self) -> None:
        from types import SimpleNamespace

        profile = SimpleNamespace(
            whitelist=SimpleNamespace(runtime=["fastapi"], dev=[], prefix_allowed=[])
        )
        hooks = SecurityHooks.from_profile(profile, extra_python_allowed=frozenset({"hijack"}))
        result = hooks.run_all("from hijack import analyzer")
        assert [f for f in result.findings if f.hook == "dependency-check"] == []


# ---------------------------------------------------------------------------
# #19 FP 수정: Node 빌트인 / tsconfig 별칭 / 스택 승인 라이브러리
# ---------------------------------------------------------------------------


class TestDependencyFrontendFP:
    """Frontend dependency-check FP #19 regression tests."""

    # --- (1) Node 빌트인 node: prefix ---

    def test_node_builtin_fs_no_warn(self) -> None:
        """node:fs import → dependency WARN 없음 (Node 빌트인)."""
        code = "import { readFileSync } from 'node:fs'"
        findings = check_dependency(code, is_frontend=True)
        dep_findings = [f for f in findings if f.hook == "dependency-check"]
        assert dep_findings == [], f"예상치 못한 findings: {dep_findings}"

    def test_node_builtin_path_no_warn(self) -> None:
        """node:path import → dependency WARN 없음 (Node 빌트인)."""
        code = "import path from 'node:path'"
        findings = check_dependency(code, is_frontend=True)
        dep_findings = [f for f in findings if f.hook == "dependency-check"]
        assert dep_findings == [], f"예상치 못한 findings: {dep_findings}"

    def test_node_builtin_multiple_no_warn(self) -> None:
        """node:fs, node:path, node:crypto 복수 import → 전부 WARN 없음."""
        code = (
            "import { readFileSync } from 'node:fs'\n"
            "import path from 'node:path'\n"
            "import { createHash } from 'node:crypto'\n"
        )
        findings = check_dependency(code, is_frontend=True)
        dep_findings = [f for f in findings if f.hook == "dependency-check"]
        assert dep_findings == [], f"예상치 못한 findings: {dep_findings}"

    def test_non_node_builtin_still_warns(self) -> None:
        """node: prefix 없는 비허용 패키지 → 여전히 WARN (TP 보존)."""
        code = "import lodash from 'lodash'"
        findings = check_dependency(code, is_frontend=True)
        assert any("lodash" in f.message for f in findings)

    # --- (2) tsconfig 별칭 prefix ---

    def test_tsconfig_alias_with_prefix_no_warn(self) -> None:
        """@shared/types/entity import + extra_frontend_prefixes=('@shared/',) → WARN 없음."""
        code = "import type { Entity } from '@shared/types/entity'"
        findings = check_dependency(code, is_frontend=True, extra_frontend_prefixes=("@shared/",))
        dep_findings = [f for f in findings if f.hook == "dependency-check"]
        assert dep_findings == [], f"예상치 못한 findings: {dep_findings}"

    def test_tsconfig_alias_without_prefix_warns(self) -> None:
        """@shared/types/entity import + prefix 없음 → WARN 발생 (대조군)."""
        code = "import type { Entity } from '@shared/types/entity'"
        findings = check_dependency(code, is_frontend=True)
        assert any("@shared/types/entity" in f.message for f in findings)

    def test_multiple_tsconfig_prefixes_no_warn(self) -> None:
        """@shared/ + @app/ 복수 prefix 주입 → 해당 import 전부 통과."""
        code = "import { Entity } from '@shared/types/entity'\nimport { store } from '@app/store'\n"
        findings = check_dependency(
            code,
            is_frontend=True,
            extra_frontend_prefixes=("@shared/", "@app/"),
        )
        dep_findings = [f for f in findings if f.hook == "dependency-check"]
        assert dep_findings == [], f"예상치 못한 findings: {dep_findings}"

    # --- (3) 스택 승인 라이브러리 extra_frontend_allowed ---

    def test_stack_library_dxf_parser_no_warn(self) -> None:
        """dxf-parser import + extra_frontend_allowed → WARN 없음."""
        code = "import DxfParser from 'dxf-parser'"
        findings = check_dependency(
            code,
            is_frontend=True,
            extra_frontend_allowed={"dxf-parser", "three", "@tarikjabiri/dxf"},
        )
        dep_findings = [f for f in findings if f.hook == "dependency-check"]
        assert dep_findings == [], f"예상치 못한 findings: {dep_findings}"

    def test_stack_library_three_no_warn(self) -> None:
        """three import + extra_frontend_allowed → WARN 없음."""
        code = "import * as THREE from 'three'"
        findings = check_dependency(
            code,
            is_frontend=True,
            extra_frontend_allowed={"dxf-parser", "three", "@tarikjabiri/dxf"},
        )
        dep_findings = [f for f in findings if f.hook == "dependency-check"]
        assert dep_findings == [], f"예상치 못한 findings: {dep_findings}"

    def test_stack_library_scoped_no_warn(self) -> None:
        """@tarikjabiri/dxf import + extra_frontend_allowed → WARN 없음."""
        code = "import { DxfWriter } from '@tarikjabiri/dxf'"
        findings = check_dependency(
            code,
            is_frontend=True,
            extra_frontend_allowed={"dxf-parser", "three", "@tarikjabiri/dxf"},
        )
        dep_findings = [f for f in findings if f.hook == "dependency-check"]
        assert dep_findings == [], f"예상치 못한 findings: {dep_findings}"

    def test_unlisted_package_still_warns_with_extra_allowed(self) -> None:
        """extra_frontend_allowed 있어도 목록 외 lodash → 여전히 WARN (TP 보존)."""
        code = "import _ from 'lodash'"
        findings = check_dependency(
            code,
            is_frontend=True,
            extra_frontend_allowed={"dxf-parser", "three"},
        )
        assert any("lodash" in f.message for f in findings)

    # --- (4) SecurityHooks 통합: extra_frontend_allowed + extra_frontend_prefixes ---

    def test_security_hooks_extra_frontend_allowed(self) -> None:
        """SecurityHooks(extra_frontend_allowed=...) → run_all frontend mode 통과."""
        hooks = SecurityHooks(extra_frontend_allowed={"dxf-parser", "three", "@tarikjabiri/dxf"})
        code = (
            "import DxfParser from 'dxf-parser'\n"
            "import * as THREE from 'three'\n"
            "import { DxfWriter } from '@tarikjabiri/dxf'\n"
        )
        result = hooks.run_all(code, is_frontend=True)
        dep_findings = [f for f in result.findings if f.hook == "dependency-check"]
        assert dep_findings == [], f"예상치 못한 findings: {dep_findings}"

    def test_security_hooks_extra_frontend_prefixes(self) -> None:
        """SecurityHooks(extra_frontend_prefixes=...) → run_all frontend mode 통과."""
        hooks = SecurityHooks(extra_frontend_prefixes=("@shared/", "@app/"))
        code = "import { Entity } from '@shared/types/entity'\nimport { store } from '@app/store'\n"
        result = hooks.run_all(code, is_frontend=True)
        dep_findings = [f for f in result.findings if f.hook == "dependency-check"]
        assert dep_findings == [], f"예상치 못한 findings: {dep_findings}"

    def test_security_hooks_node_builtins_via_run_all(self) -> None:
        """run_all frontend mode: node:fs, node:path → WARN 없음."""
        hooks = SecurityHooks()
        code = "import { readFileSync } from 'node:fs'\nimport path from 'node:path'\n"
        result = hooks.run_all(code, is_frontend=True)
        dep_findings = [f for f in result.findings if f.hook == "dependency-check"]
        assert dep_findings == [], f"예상치 못한 findings: {dep_findings}"

    def test_security_hooks_backward_compat_no_extra(self) -> None:
        """SecurityHooks() 기본 생성자 — extra 없이 기존 동작 불변."""
        hooks = SecurityHooks()
        # react 는 기본 whitelist — 통과
        result = hooks.run_all("import { useState } from 'react'", is_frontend=True)
        dep_findings = [f for f in result.findings if f.hook == "dependency-check"]
        assert dep_findings == []
        # moment 는 비허용 — WARN
        result2 = hooks.run_all("import moment from 'moment'", is_frontend=True)
        assert any("moment" in f.message for f in result2.findings)

    def test_from_profile_with_extra_frontend(self) -> None:
        """from_profile + extra_frontend_allowed/prefixes → 프로파일 whitelist 에 합산."""
        from types import SimpleNamespace

        profile = SimpleNamespace(
            whitelist=SimpleNamespace(runtime=["react"], dev=[], prefix_allowed=["@radix-ui/"])
        )
        hooks = SecurityHooks.from_profile(
            profile,
            extra_frontend_allowed=frozenset({"dxf-parser"}),
            extra_frontend_prefixes=("@shared/",),
        )
        code = (
            "import { useState } from 'react'\n"
            "import DxfParser from 'dxf-parser'\n"
            "import { Entity } from '@shared/types/entity'\n"
        )
        result = hooks.run_all(code, is_frontend=True)
        dep_findings = [f for f in result.findings if f.hook == "dependency-check"]
        assert dep_findings == [], f"예상치 못한 findings: {dep_findings}"


# ---------------------------------------------------------------------------
# parse_skeleton_stack_whitelist
# ---------------------------------------------------------------------------

_SKELETON_FIXTURE = """
## §3 기술 스택

### 허용 라이브러리 화이트리스트
> 프로파일의 기본 whitelist 에서 가져온다.
**추가 허용 (프로파일 기본 + 이 목록)**:
- dxf-parser: DXF 파싱
- three: 3D 렌더링
- @tarikjabiri/dxf: DXF 생성

### 다른 섹션
- something: here
"""

_SKELETON_NO_SECTION = """
## §3 기술 스택

### 다른 정보
- item: value
"""

_SKELETON_WITH_PLACEHOLDER = """
### 허용 라이브러리 화이트리스트
- <패키지 이름>: <사유>
- real-pkg: 실제 라이브러리
"""


class TestParseSkeletonStackWhitelist:
    def test_extracts_packages(self) -> None:
        """§3 fixture → {dxf-parser, three, @tarikjabiri/dxf}."""
        from src.orchestrator.security_hooks import parse_skeleton_stack_whitelist

        result = parse_skeleton_stack_whitelist(_SKELETON_FIXTURE)
        assert result == frozenset({"dxf-parser", "three", "@tarikjabiri/dxf"})

    def test_no_section_returns_empty(self) -> None:
        """허용 라이브러리 화이트리스트 헤딩 없음 → frozenset()."""
        from src.orchestrator.security_hooks import parse_skeleton_stack_whitelist

        result = parse_skeleton_stack_whitelist(_SKELETON_NO_SECTION)
        assert result == frozenset()

    def test_placeholder_excluded(self) -> None:
        """<패키지 이름> 플레이스홀더 → 제외."""
        from src.orchestrator.security_hooks import parse_skeleton_stack_whitelist

        result = parse_skeleton_stack_whitelist(_SKELETON_WITH_PLACEHOLDER)
        assert "<패키지 이름>" not in result
        assert "real-pkg" in result

    def test_empty_string(self) -> None:
        """빈 문자열 → frozenset()."""
        from src.orchestrator.security_hooks import parse_skeleton_stack_whitelist

        result = parse_skeleton_stack_whitelist("")
        assert result == frozenset()

    def test_scoped_package_included(self) -> None:
        """@scope/pkg 형태 scoped 패키지 포함 확인."""
        from src.orchestrator.security_hooks import parse_skeleton_stack_whitelist

        result = parse_skeleton_stack_whitelist(_SKELETON_FIXTURE)
        assert "@tarikjabiri/dxf" in result


# ---------------------------------------------------------------------------
# parse_tsconfig_path_prefixes
# ---------------------------------------------------------------------------


class TestParseTsconfigPathPrefixes:
    def test_wildcard_keys_become_prefixes(self) -> None:
        """@shared/* → @shared/, @/* → @/ 변환."""
        from src.orchestrator.security_hooks import parse_tsconfig_path_prefixes

        result = parse_tsconfig_path_prefixes({"@shared/*": ["src/shared/$1"], "@/*": ["src/$1"]})
        assert result == ("@/", "@shared/")  # 정렬

    def test_non_wildcard_key_kept_as_is(self) -> None:
        """와일드카드 없는 @root → @root 그대로."""
        from src.orchestrator.security_hooks import parse_tsconfig_path_prefixes

        result = parse_tsconfig_path_prefixes({"@root": ["src/root/index.ts"]})
        assert result == ("@root",)

    def test_mixed_keys(self) -> None:
        """wildcard + non-wildcard 혼합 → 정렬된 tuple."""
        from src.orchestrator.security_hooks import parse_tsconfig_path_prefixes

        result = parse_tsconfig_path_prefixes({"@shared/*": ["x"], "@/*": ["y"], "@root": ["z"]})
        assert result == ("@/", "@root", "@shared/")

    def test_empty_dict(self) -> None:
        """빈 dict → 빈 tuple."""
        from src.orchestrator.security_hooks import parse_tsconfig_path_prefixes

        result = parse_tsconfig_path_prefixes({})
        assert result == ()

    def test_deduplication(self) -> None:
        """중복 prefix → 단일 항목."""
        from src.orchestrator.security_hooks import parse_tsconfig_path_prefixes

        result = parse_tsconfig_path_prefixes({"@shared/*": ["a"], "@shared/other/*": ["b"]})
        # @shared/* → @shared/, @shared/other/* → @shared/other/ : 중복 없음
        assert "@shared/" in result
        assert "@shared/other/" in result
        # 중복 여부: 같은 prefix 두 번 없어야 함
        assert len(result) == len(set(result))


# ---------------------------------------------------------------------------
# LESSON-041 — command-guard/db-guard SQLite 드라이버 FP + test-strip + subpath
# ---------------------------------------------------------------------------


class TestCommandGuardExecMethodCall:
    """LESSON-041: `.exec(` 메서드 호출은 Python builtin exec() 가 아님."""

    def test_sqlite_driver_exec_constant_clean(self) -> None:
        code = 'raw.exec("PRAGMA foreign_keys = ON;")'
        findings = check_command_guard(code)
        assert findings == []

    def test_sqlite_driver_exec_transaction_clean(self) -> None:
        code = 'this.client.exec("commit");'
        findings = check_command_guard(code)
        assert findings == []

    def test_bare_python_exec_still_blocked(self) -> None:
        code = "exec(user_code)"
        findings = check_command_guard(code)
        assert any(f.severity == Severity.BLOCK for f in findings)

    def test_drop_table_still_blocked_outside_tests(self) -> None:
        # DROP 자체는 여전히 BLOCK — 테스트 파일 제외는 strip_test_files_from_diff 몫.
        code = 'db.exec("DROP TABLE users")'
        findings = check_command_guard(code)
        assert any("DROP" in f.message for f in findings)


class TestDbGuardExecInterpolation:
    """LESSON-041: 보간/concat SQL 을 담은 `.exec(` 는 db-guard 가 차단."""

    def test_template_interpolation_blocked(self) -> None:
        code = "db.exec(`DELETE FROM logs WHERE id = ${userId}`)"
        findings = check_db_guard(code)
        assert any(f.severity == Severity.BLOCK for f in findings)

    def test_exec_async_interpolation_blocked(self) -> None:
        code = "await db.execAsync(`SELECT * FROM ${table}`)"
        findings = check_db_guard(code)
        assert any(f.severity == Severity.BLOCK for f in findings)

    def test_string_concat_blocked(self) -> None:
        code = 'db.exec("DELETE FROM logs WHERE id = " + userId)'
        findings = check_db_guard(code)
        assert any(f.severity == Severity.BLOCK for f in findings)

    def test_constant_template_literal_clean(self) -> None:
        code = "db.exec(`CREATE TABLE items (id INTEGER PRIMARY KEY)`)"
        findings = check_db_guard(code)
        assert findings == []

    def test_constant_variable_arg_clean(self) -> None:
        code = "raw.exec(migrationSql);"
        findings = check_db_guard(code)
        assert findings == []


class TestStripTestFilesFromDiff:
    """LESSON-041: 테스트 픽스처의 파괴적 SQL/가짜 시크릿은 훅 스캔 제외."""

    @staticmethod
    def _diff_block(path: str, added: str) -> str:
        return (
            f"diff --git a/{path} b/{path}\n"
            f"--- a/{path}\n"
            f"+++ b/{path}\n"
            f"+{added}\n"
        )

    def test_dunder_tests_dir_stripped(self) -> None:
        from src.orchestrator.security_hooks import strip_test_files_from_diff

        diff = self._diff_block(
            "src/containers/logs/store/__tests__/logs.store.test.ts",
            'raw.exec("DROP TABLE workout_logs");',
        )
        assert strip_test_files_from_diff(diff) == ""

    def test_test_suffix_stripped(self) -> None:
        from src.orchestrator.security_hooks import strip_test_files_from_diff

        diff = self._diff_block("src/app.spec.tsx", "const x = 1;")
        assert strip_test_files_from_diff(diff) == ""

    def test_pytest_file_stripped(self) -> None:
        from src.orchestrator.security_hooks import strip_test_files_from_diff

        for path in ("tests/test_auth.py", "backend/tests/conftest.py", "pkg/auth_test.py"):
            diff = self._diff_block(path, "DROP TABLE users;")
            assert strip_test_files_from_diff(diff) == "", path

    def test_production_file_kept(self) -> None:
        from src.orchestrator.security_hooks import strip_test_files_from_diff

        # testSqliteDb.ts 는 이름에 test 가 들어가도 테스트 디렉토리/접미사가 아님 — 유지.
        for path in ("src/db/testSqliteDb.ts", "src/core/validation.ts", "src/latest/api.ts"):
            diff = self._diff_block(path, "export const x = 1;")
            assert strip_test_files_from_diff(diff) == diff, path

    def test_mixed_diff_strips_only_test_blocks(self) -> None:
        from src.orchestrator.security_hooks import strip_test_files_from_diff

        prod = self._diff_block("src/db/client.ts", "export const db = open();")
        test = self._diff_block("src/db/__tests__/migration.test.ts", 'raw.exec("DROP TABLE x");')
        assert strip_test_files_from_diff(prod + test) == prod


class TestDependencySubpathNormalization:
    """LESSON-041: subpath import 는 설치 패키지 루트로 정규화해 화이트리스트 대조."""

    def test_subpath_of_whitelisted_root_clean(self) -> None:
        code = 'import { sqliteTable } from "drizzle-orm/sqlite-core";'
        findings = check_dependency(
            code, is_frontend=True, frontend_whitelist={"drizzle-orm"}, frontend_prefixes=()
        )
        assert findings == []

    def test_scoped_subpath_of_whitelisted_root_clean(self) -> None:
        code = 'import { A } from "@scope/pkg/deep/sub";'
        findings = check_dependency(
            code, is_frontend=True, frontend_whitelist={"@scope/pkg"}, frontend_prefixes=()
        )
        assert findings == []

    def test_unknown_root_still_warned(self) -> None:
        code = 'import { x } from "left-pad/core";'
        findings = check_dependency(
            code, is_frontend=True, frontend_whitelist={"drizzle-orm"}, frontend_prefixes=()
        )
        assert any(f.severity == Severity.WARN for f in findings)

    def test_bare_node_builtin_clean(self) -> None:
        code = 'import * as fs from "fs";\nimport * as path from "path";'
        findings = check_dependency(
            code, is_frontend=True, frontend_whitelist=set(), frontend_prefixes=()
        )
        assert findings == []
