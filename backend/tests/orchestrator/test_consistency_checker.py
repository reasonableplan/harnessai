"""consistency_checker 단위 테스트.

대상: `src/orchestrator/consistency_checker.py`
전략: 인메모리 skeleton/tasks 텍스트 fixture 로 finding 패턴 검증.
"""

from __future__ import annotations

from src.orchestrator.consistency_checker import (
    ConsistencyFinding,
    check_error_ux_codes_defined,
    check_isolated_components,
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
