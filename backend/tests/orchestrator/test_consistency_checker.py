"""consistency_checker 단위 테스트.

대상: `src/orchestrator/consistency_checker.py`
전략: 인메모리 skeleton/tasks 텍스트 fixture 로 finding 패턴 검증.
"""

from __future__ import annotations

from src.orchestrator.consistency_checker import (
    ConsistencyFinding,
    check_error_ux_codes_defined,
    check_isolated_components,
    check_offline_network_violation,
    check_screen_api_references,
    check_screen_auth_column,
    check_task_skeleton_references,
    run_all_checks,
)

# ── view.components → state.flow/core.logic isolation ───────────────


def test_id_keyed_resolution_with_dynamic_numbers() -> None:
    """섹션 번호는 활성 fragment 셋에 따라 동적 부여 — 제목으로 ID 를 해석해야 한다."""
    skel = (
        "## 4. 컴포넌트 트리\n<GameScreen> <OrphanedWidget>\n\n"
        "## 5. 상태 흐름\nGameScreen flows\n\n"
        "## 6. 도메인 로직\nGameScreen logic\n"
    )
    findings = check_isolated_components(skel)
    assert [f.target for f in findings] == ["OrphanedWidget"]


def test_task_component_reference_with_dynamic_numbers() -> None:
    """컴포넌트 트리가 §13 이 아니어도 known component 로 인정된다."""
    skel = "## 7. 컴포넌트 트리\n<PushToTalkButton>\n"
    tasks = (
        "| ID | Agent | Dep | Desc | Status |\n"
        "|----|-------|-----|------|--------|\n"
        "| T-001 | be | - | PushToTalkButton 컴포넌트 구현 | done |\n"
    )
    assert check_task_skeleton_references(tasks, skel) == []


def test_component_referenced_in_section_14_passes() -> None:
    skel = (
        "## 13. 컴포넌트 트리\n"
        "<GameScreen> uses <PushToTalkButton> and <DetectionAlertSheet>.\n\n"
        "## 14. 상태 흐름\n"
        "GameScreen 의 PushToTalkButton 누르면 ... DetectionAlertSheet 표시.\n\n"
        "## 15. 도메인 로직\n"
        "void onTap() { /* uses PushToTalkButton state */ }\n"
    )
    findings = check_isolated_components(skel)
    assert findings == [], f"unexpected findings: {findings}"


def test_component_only_in_section_13_flagged_isolated() -> None:
    skel = (
        "## 13. 컴포넌트 트리\n"
        "<GameScreen> uses <OrphanedWidget>.\n\n"
        "## 14. 상태 흐름\n"
        "GameScreen 만 등장.\n\n"
        "## 15. 도메인 로직\n"
        "GameScreen 호출.\n"
    )
    findings = check_isolated_components(skel)
    assert len(findings) == 1
    assert findings[0].target == "OrphanedWidget"
    assert findings[0].pattern == "isolated-component"
    assert findings[0].severity == "info"


def test_no_section_13_yields_no_findings() -> None:
    """§13 없으면 검증 대상 없음 — 빈 finding."""
    skel = "## 1. 개요\nfoo bar\n## 14. 상태 흐름\nGameScreen 만\n"
    assert check_isolated_components(skel) == []


def test_short_camelcase_filtered_out() -> None:
    """3글자 이하 JSX 토큰은 컴포넌트로 인정 안 함 (<Id />, <Ok /> 등).

    view.components 정의 추출은 JSX 토큰만 인식한다 (FP #7 수정).
    <GameScreen /> 은 길이 ≥4 이고 JSX 토큰이므로 isolated-component 로 잡혀야 함.
    bare CamelCase 산문(Id, Ok, Game, GameScreen)은 정의로 인정되지 않는다.
    """
    skel = (
        "## 13. 컴포넌트 트리\n"
        "<Id /> <Ok /> <GameScreen />\n"
        "## 14. 상태 흐름\nplain text\n"
        "## 15. 도메인 로직\nplain\n"
    )
    findings = check_isolated_components(skel)
    targets = {f.target for f in findings}
    # <GameScreen /> 만 길이 ≥ 4 이고 JSX 토큰 — isolated 로 잡혀야 함.
    assert "GameScreen" in targets
    assert "Id" not in targets
    assert "Ok" not in targets


# ── §16 task → 본문 reference ────────────────────────────────────────


def test_task_with_section_reference_passes() -> None:
    skel = "## 13. 컴포넌트 트리\nGameScreen\n"
    tasks = (
        "| ID | Agent | Dep | Desc | Status |\n"
        "|----|-------|-----|------|--------|\n"
        "| T-001 | be | - | §15 의 onTap 함수 구현 | done |\n"
    )
    assert check_task_skeleton_references(tasks, skel) == []


def test_task_with_component_reference_passes() -> None:
    skel = "## 13. 컴포넌트 트리\n<GameScreen> <PushToTalkButton>\n"
    tasks = (
        "| ID | Agent | Dep | Desc | Status |\n"
        "|----|-------|-----|------|--------|\n"
        "| T-001 | be | - | PushToTalkButton 컴포넌트 구현 | done |\n"
    )
    assert check_task_skeleton_references(tasks, skel) == []


def test_task_with_no_reference_flagged() -> None:
    skel = "## 13. 컴포넌트 트리\n<GameScreen>\n"
    tasks = (
        "| ID | Agent | Dep | Desc | Status |\n"
        "|----|-------|-----|------|--------|\n"
        "| T-001 | be | - | 임의 작업 | done |\n"
    )
    findings = check_task_skeleton_references(tasks, skel)
    assert len(findings) == 1
    assert findings[0].target == "T-001"
    assert findings[0].severity == "warn"
    assert findings[0].pattern == "task-no-reference"


def test_unknown_camelcase_in_task_does_not_satisfy() -> None:
    """§13 에 없는 CamelCase 는 reference 로 인정 안 함."""
    skel = "## 13. 컴포넌트 트리\n<GameScreen>\n"
    tasks = (
        "| ID | Agent | Dep | Desc | Status |\n"
        "|----|-------|-----|------|--------|\n"
        "| T-001 | be | - | RandomWidget 구현 | done |\n"
    )
    findings = check_task_skeleton_references(tasks, skel)
    assert len(findings) == 1
    assert findings[0].target == "T-001"


# ── run_all_checks aggregator ───────────────────────────────────────


def test_run_all_aggregates_findings() -> None:
    skel = (
        "## 13. 컴포넌트 트리\n<GameScreen> <OrphanedWidget>\n"
        "## 14. 상태 흐름\nGameScreen\n"
        "## 15. 도메인 로직\nGameScreen\n"
    )
    tasks = (
        "| ID | Agent | Dep | Desc | Status |\n"
        "|----|-------|-----|------|--------|\n"
        "| T-001 | be | - | 임의 작업 | done |\n"
        "| T-002 | be | - | §15 onTap | done |\n"
    )
    findings = run_all_checks(skeleton_text=skel, tasks_text=tasks)
    targets = {f.target for f in findings}
    assert "OrphanedWidget" in targets  # isolated component
    assert "T-001" in targets  # no reference
    assert "T-002" not in targets  # has §15 ref


def test_run_all_skips_task_check_without_tasks() -> None:
    """tasks.md 없는 단계 (designed 직후) 도 호출 가능."""
    skel = "## 13. 컴포넌트 트리\n<GameScreen> <OrphanedWidget>\n## 14. 상태 흐름\nGameScreen\n## 15. 도메인 로직\nGameScreen\n"
    findings = run_all_checks(skeleton_text=skel)
    targets = {f.target for f in findings}
    assert "OrphanedWidget" in targets
    assert all(not f.target.startswith("T-") for f in findings)


def test_run_all_empty_tasks_text_runs_check() -> None:
    """tasks_text='' (빈 파일) 은 None 과 다름 — task check 실행하되 0 finding."""
    skel = "## 13. 컴포넌트 트리\n<GameScreen>\n## 14. 상태 흐름\nGameScreen\n## 15. 도메인 로직\nGameScreen\n"
    # 빈 tasks_text 도 task check 가 실행되지만 매칭되는 행이 없어 0 finding.
    findings = run_all_checks(skeleton_text=skel, tasks_text="")
    assert all(not f.target.startswith("T-") for f in findings)


def test_finding_dataclass_fields() -> None:
    """ConsistencyFinding 의 필수 필드 4개 모두 채워짐."""
    skel = (
        "## 13. 컴포넌트 트리\n<GameScreen>\n## 14. 상태 흐름\nplain\n## 15. 도메인 로직\nplain\n"
    )
    findings = check_isolated_components(skel)
    assert len(findings) == 1
    f = findings[0]
    assert isinstance(f, ConsistencyFinding)
    assert f.severity in ("info", "warn")
    assert f.pattern
    assert f.message
    assert f.target


# ── 설계-시점 cross-section 검증 (design backlog A) ──────────────────


def test_error_ux_undefined_code_flagged() -> None:
    """error_ux 매핑에 쓴 코드가 errors 에 정의 안 됨 → warn."""
    skel = (
        "## 5. 에러 핸들링\n| 코드 | 의미 |\n|---|---|\n| AUTH_001 | 인증 실패 |\n\n"
        "## 6. 에러 처리 UX\n| 백엔드 코드 | UI |\n|---|---|\n"
        "| AUTH_001 | redirect |\n| AUTH_005 | modal |\n"
    )
    findings = check_error_ux_codes_defined(skel)
    assert [f.target for f in findings] == ["AUTH_005"]
    assert findings[0].pattern == "error-code-undefined"
    assert findings[0].severity == "warn"


def test_error_ux_all_defined_passes() -> None:
    skel = (
        "## 5. 에러 핸들링\n| AUTH_001 | x |\n| SERVER_001 | y |\n\n"
        "## 6. 에러 처리 UX\n| AUTH_001 | redirect |\n"
    )
    assert check_error_ux_codes_defined(skel) == []


def test_error_ux_check_skips_when_section_missing() -> None:
    skel = "## 6. 에러 처리 UX\n| AUTH_005 | modal |\n"
    assert check_error_ux_codes_defined(skel) == []


def test_screen_api_missing_flagged() -> None:
    """화면이 참조하는 엔드포인트가 interface.http 에 없음 → warn."""
    skel = (
        "## 9. HTTP API\n**`GET /api/habits`**\n\n"
        "## 13. 화면 목록\n"
        "| 경로 | 화면명 | Auth | 주요 API |\n|---|---|---|---|\n"
        "| `/` | 홈 | ✅ | `GET /api/habits` |\n"
        "| `/stats` | 통계 | ✅ | `GET /api/stats` |\n"
    )
    findings = check_screen_api_references(skel)
    assert [f.target for f in findings] == ["GET /api/stats"]
    assert findings[0].pattern == "screen-api-missing"


def test_screen_api_check_skips_without_http_section() -> None:
    skel = "## 13. 화면 목록\n| `/` | 홈 | ✅ | `GET /api/x` |\n"
    assert check_screen_api_references(skel) == []


def test_screen_auth_blank_flagged_when_auth_active() -> None:
    """auth 섹션 활성인데 화면 표의 Auth 칸 공백 → warn."""
    skel = (
        "## 6. 인증 / 권한\nJWT\n\n"
        "## 13. 화면 목록\n"
        "| 경로 | 화면명 | Auth | 비고 |\n|------|------|:---:|----|\n"
        "| `/login` | 로그인 | ❌ | |\n"
        "| `/stats` | 통계 |  | |\n"
    )
    findings = check_screen_auth_column(skel)
    assert [f.target for f in findings] == ["/stats"]
    assert findings[0].pattern == "screen-auth-unspecified"


def test_screen_auth_check_skips_without_auth_section() -> None:
    skel = "## 13. 화면 목록\n| 경로 | 화면명 | Auth |\n|---|---|---|\n| `/x` | x |  |\n"
    assert check_screen_auth_column(skel) == []


def test_run_all_includes_design_checks() -> None:
    """run_all_checks 가 설계 검증 3종을 집계에 포함한다."""
    skel = "## 5. 에러 핸들링\n| AUTH_001 | x |\n\n## 6. 에러 처리 UX\n| ORPHAN_001 | toast |\n"
    targets = {f.target for f in run_all_checks(skeleton_text=skel)}
    assert "ORPHAN_001" in targets


# ── FP Fix #7: JSX 토큰 기반 컴포넌트 추출 ────────────────────────────


def test_prose_camelcase_not_flagged_as_isolated_component() -> None:
    """FP #7: view.components prose 에 등장하는 폰트명·표기법·타입명은 isolated-component 로 잡히면 안 됨.

    JetBrains, PascalCase, UnsupportedInfo 는 JSX 토큰이 아니므로 컴포넌트가 아님.
    <HomeContainer /> 는 진짜 컴포넌트이고 state.flow 에서 참조되므로 finding 없어야 함.
    """
    skel = (
        "## 13. 컴포넌트 트리\n"
        "### App 계층\n"
        "```\n"
        "App\n"
        "├─ <HomeContainer />\n"
        "│   └─ <Header />\n"
        "```\n"
        "### 디자인 가이드\n"
        "타이포그래피: JetBrains Mono 사용.\n"
        "CVA 표기법은 PascalCase 를 쓴다.\n"
        "오류 타입: UnsupportedInfo 참조.\n\n"
        "## 14. 상태 흐름\n"
        "<HomeContainer /> 마운트 시 fetch 실행.\n"
        "<Header /> 는 nav 담당.\n\n"
        "## 15. 도메인 로직\n"
        "HomeContainer 초기화 로직.\n"
    )
    findings = check_isolated_components(skel)
    targets = {f.target for f in findings}
    assert "JetBrains" not in targets, f"JetBrains falsely flagged: {targets}"
    assert "PascalCase" not in targets, f"PascalCase falsely flagged: {targets}"
    assert "UnsupportedInfo" not in targets, f"UnsupportedInfo falsely flagged: {targets}"
    assert "HomeContainer" not in targets, f"HomeContainer falsely flagged: {targets}"


def test_genuine_orphan_component_still_flagged() -> None:
    """FP #7 TP 보존: view.components 에만 있고 state.flow/core.logic 에 없는 컴포넌트는 잡혀야 함."""
    skel = (
        "## 13. 컴포넌트 트리\n"
        "<HomeContainer />\n"
        "<OrphanWidget />\n\n"
        "## 14. 상태 흐름\n"
        "<HomeContainer /> 상태 전이.\n\n"
        "## 15. 도메인 로직\n"
        "HomeContainer 초기화.\n"
    )
    findings = check_isolated_components(skel)
    targets = {f.target for f in findings}
    assert "OrphanWidget" in targets, f"OrphanWidget not flagged: {targets}"
    assert "HomeContainer" not in targets, f"HomeContainer falsely flagged: {targets}"


def test_paired_components_both_sides_no_finding() -> None:
    """FP #7: 양쪽에 JSX 토큰으로 등장하는 컴포넌트는 finding 없어야 함."""
    skel = (
        "## 13. 컴포넌트 트리\n"
        "<Button> <Input>\n\n"
        "## 14. 상태 흐름\n"
        "<Button> 클릭 시 submit.\n\n"
        "## 15. 도메인 로직\n"
        "<Input> onChange 핸들러.\n"
    )
    assert check_isolated_components(skel) == []


# ── FP Fix #13: 스펙블록 skeleton 참조 인정 ──────────────────────────


def test_task_specblock_skeleton_ref_suppresses_warn() -> None:
    """FP #13: Phase 행 description 에 §N 없지만 스펙블록에 skeleton 참조 있으면 warn 없어야 함."""
    skel = "## 13. 컴포넌트 트리\n<GameScreen>\n"
    tasks = (
        "| ID | Agent | Dep | Desc | Status |\n"
        "|----|-------|-----|------|--------|\n"
        "| T-001 | be | - | 유저 CRUD 구현 | todo |\n"
        "\n"
        "### T-001 유저 CRUD 구현\n"
        "- **skeleton 참조**: `persistence.users`\n"
        "- 구현 범위: User 모델, Repository, Service\n"
    )
    findings = check_task_skeleton_references(tasks, skel)
    task_targets = [f.target for f in findings if f.pattern == "task-no-reference"]
    assert "T-001" not in task_targets, f"T-001 falsely warned: {task_targets}"


def test_task_no_specblock_no_section_ref_still_warned() -> None:
    """FP #13 TP 보존: 스펙블록도 없고 description 에 §N/컴포넌트도 없으면 여전히 warn."""
    skel = "## 13. 컴포넌트 트리\n<GameScreen>\n"
    tasks = (
        "| ID | Agent | Dep | Desc | Status |\n"
        "|----|-------|-----|------|--------|\n"
        "| T-099 | be | - | 임의 작업 | todo |\n"
    )
    findings = check_task_skeleton_references(tasks, skel)
    task_targets = [f.target for f in findings if f.pattern == "task-no-reference"]
    assert "T-099" in task_targets, f"T-099 not warned: {task_targets}"


def test_task_section_ref_in_description_still_passes() -> None:
    """FP #13 기존 동작 보존: description 에 §13 있으면 warn 없어야 함."""
    skel = "## 13. 컴포넌트 트리\n<GameScreen>\n"
    tasks = (
        "| ID | Agent | Dep | Desc | Status |\n"
        "|----|-------|-----|------|--------|\n"
        "| T-042 | be | - | §13 GameScreen 구현 | todo |\n"
    )
    assert check_task_skeleton_references(tasks, skel) == []


def test_task_specblock_multiple_refs_suppresses_warn() -> None:
    """스펙블록에 skeleton 참조가 여러 개여도 한 번만 suppress."""
    skel = "## 13. 컴포넌트 트리\n<GameScreen>\n"
    tasks = (
        "| ID | Agent | Dep | Desc | Status |\n"
        "|----|-------|-----|------|--------|\n"
        "| T-002 | fe | - | 도메인 레이어 | todo |\n"
        "\n"
        "### T-002 도메인 레이어\n"
        "- **skeleton 참조**: `core.logic`, `persistence.users`\n"
    )
    findings = check_task_skeleton_references(tasks, skel)
    task_targets = [f.target for f in findings if f.pattern == "task-no-reference"]
    assert "T-002" not in task_targets


# ── 오프라인/네트워크 제약 위반 검사 (NFR #10) ───────────────────────


def test_offline_constraint_external_url_flagged() -> None:
    """오프라인 선언 + 비-루프백 실제 호스트 URL → critical finding."""
    skel = (
        "## 1. NFR\n오프라인 전용 앱 — 외부 인터넷 호출 없음.\n\n"
        "## 9. HTTP API\n런타임에 https://api.example.com/data 를 호출한다.\n"
    )
    findings = check_offline_network_violation(skel)
    assert len(findings) >= 1
    assert all(f.severity == "critical" for f in findings)
    assert all(f.pattern == "offline-constraint-violation" for f in findings)
    targets = [f.target for f in findings]
    assert any("api.example.com" in t for t in targets)


def test_offline_constraint_loopback_url_excluded() -> None:
    """오프라인 선언 + localhost:3002 만 → finding 0 (루프백 제외)."""
    skel = (
        "## 1. NFR\n네트워크 호출 없음. 로컬 루프백만 허용.\n\n"
        "## 9. HTTP API\nGET http://localhost:3002/api/status\n"
        "또는 http://127.0.0.1:8080/health 로 헬스체크.\n"
    )
    findings = check_offline_network_violation(skel)
    assert findings == []


def test_offline_constraint_download_verb_flagged() -> None:
    """오프라인 선언 + 다운로드 동사 → warn finding (키워드 단독 = 약한 신호, dogfood #21 강등)."""
    skel = (
        "## 1. NFR\noffline only — no network.\n\n"
        "## 7. 초기화\n런타임에 그래마 파일을 다운로드해서 파서를 초기화한다.\n"
    )
    findings = check_offline_network_violation(skel)
    assert len(findings) >= 1
    assert all(f.severity == "warn" for f in findings)
    assert any("다운로드" in f.target for f in findings)


def test_no_offline_constraint_external_url_ignored() -> None:
    """오프라인 선언 없음 + 외부 URL 많음 → finding 0 (제약 없으면 미적용)."""
    skel = (
        "## 1. 개요\n일반 웹 앱.\n\n"
        "## 9. HTTP API\nhttps://api.openai.com/v1/chat 호출.\n"
        "https://cdn.jsdelivr.net/npm/foo.js 로드.\n"
    )
    findings = check_offline_network_violation(skel)
    assert findings == []


def test_offline_constraint_url_in_codefence_ignored() -> None:
    """오프라인 선언 + 코드펜스 안 URL → 무시 (FP 방지)."""
    skel = (
        "## 1. NFR\n외부 인터넷 호출 없음 — air-gapped 환경.\n\n"
        "## 9. 예시\n아래는 *사용하지 않는* 예시:\n"
        "```\n"
        "curl https://api.external.com/data\n"
        "```\n"
        "실제로는 로컬 DB 에서만 읽는다.\n"
    )
    findings = check_offline_network_violation(skel)
    assert findings == []


def test_offline_constraint_empty_skeleton_no_crash() -> None:
    """빈 skeleton → [] (크래시 없음)."""
    assert check_offline_network_violation("") == []


def test_offline_constraint_dedup_same_marker() -> None:
    """동일 마커가 여러 번 등장해도 dedup — finding 1개만."""
    skel = (
        "## 1. NFR\nno network — offline only.\n\n"
        "## 9. API\nhttps://remote.server.io/a 사용.\nhttps://remote.server.io/a 재사용.\n"
    )
    findings = check_offline_network_violation(skel)
    targets = [f.target for f in findings]
    assert len(targets) == len(set(targets)), "중복 target 이 dedup 되지 않음"


def test_offline_constraint_design_reference_url_excluded() -> None:
    """dogfood #21: 디자인 레퍼런스/문서 URL 은 런타임 네트워크가 아님 → 제외."""
    skel = (
        "## 1. NFR\n오프라인 전용 앱 — 외부 인터넷 호출 없음.\n\n"
        "## 5. 화면 정의\n"
        "### 디자인 레퍼런스 (필수 — 사용자 입력)\n"
        "| 항목 | 출처 (URL) | 비고 |\n"
        "|---|---|---|\n"
        "| 메인 톤 | NativeWind 기본 (https://www.nativewind.dev) | 기능 우선 |\n"
        "| 팔레트 | https://tailwindcss.com/docs/customizing-colors | slate 중심 |\n"
    )
    findings = check_offline_network_violation(skel)
    assert findings == []


def test_offline_constraint_store_upload_deploy_context_excluded() -> None:
    """dogfood #21: '스토어 업로드'(배포 절차) 는 앱 런타임 위반이 아님 → 제외."""
    skel = (
        "## 1. NFR\n오프라인 전용 — 네트워크 호출 없음.\n\n"
        "## 12. 배포 파이프라인\n"
        "스토어 업로드 (수동)\n"
        "롤백: 이전 버전 재빌드/재업로드 또는 EAS Update 로 되돌림.\n"
    )
    findings = check_offline_network_violation(skel)
    assert findings == []


def test_offline_constraint_runtime_url_under_doc_heading_only_excluded() -> None:
    """문서 문맥이 아닌 섹션의 런타임 URL 은 여전히 critical (TP 보존)."""
    skel = (
        "## 1. NFR\n오프라인 전용 앱 — 외부 인터넷 호출 없음.\n\n"
        "## 9. HTTP API\n런타임에 https://api.remote.io/v1 을 호출한다.\n"
    )
    findings = check_offline_network_violation(skel)
    assert len(findings) == 1
    assert findings[0].severity == "critical"


def test_run_all_includes_offline_check() -> None:
    """run_all_checks 가 offline 검사를 집계에 포함한다."""
    skel = "## 1. NFR\n외부 인터넷 호출 없음.\n\n## 9. API\nhttps://api.remote.io/v1 호출.\n"
    findings = run_all_checks(skeleton_text=skel)
    patterns = {f.pattern for f in findings}
    assert "offline-constraint-violation" in patterns
