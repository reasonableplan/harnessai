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
    """4글자 미만 또는 단순 단어는 컴포넌트로 인정 안 함 (Id, Ok 등)."""
    skel = (
        "## 13. 컴포넌트 트리\n"
        "Id Ok foo Game GameScreen\n"
        "## 14. 상태 흐름\nplain text\n"
        "## 15. 도메인 로직\nplain\n"
    )
    findings = check_isolated_components(skel)
    targets = {f.target for f in findings}
    # GameScreen 만 길이 ≥ 4 이고 CamelCase. Id/Ok/Game 은 너무 짧거나 단일 단어
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
    skel = "## 13. 컴포넌트 트리\n<GameScreen>\n## 14. 상태 흐름\nplain\n## 15. 도메인 로직\nplain\n"
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
    skel = (
        "## 13. 화면 목록\n| 경로 | 화면명 | Auth |\n|---|---|---|\n| `/x` | x |  |\n"
    )
    assert check_screen_auth_column(skel) == []


def test_run_all_includes_design_checks() -> None:
    """run_all_checks 가 설계 검증 3종을 집계에 포함한다."""
    skel = (
        "## 5. 에러 핸들링\n| AUTH_001 | x |\n\n"
        "## 6. 에러 처리 UX\n| ORPHAN_001 | toast |\n"
    )
    targets = {f.target for f in run_all_checks(skeleton_text=skel)}
    assert "ORPHAN_001" in targets
