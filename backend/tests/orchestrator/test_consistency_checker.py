"""consistency_checker 단위 테스트.

대상: `src/orchestrator/consistency_checker.py`
전략: 인메모리 skeleton/tasks 텍스트 fixture 로 finding 패턴 검증.
"""

from __future__ import annotations

from src.orchestrator.consistency_checker import (
    ConsistencyFinding,
    check_isolated_components,
    check_task_skeleton_references,
    run_all_checks,
)

# ── §13 → §14/§15 isolation ─────────────────────────────────────────


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
    skel = "## 1. 개요\nfoo bar\n## 14. 상태\nGameScreen 만\n"
    assert check_isolated_components(skel) == []


def test_short_camelcase_filtered_out() -> None:
    """4글자 미만 또는 단순 단어는 컴포넌트로 인정 안 함 (Id, Ok 등)."""
    skel = (
        "## 13. 컴포넌트 트리\n"
        "Id Ok foo Game GameScreen\n"
        "## 14. 상태\nplain text\n"
        "## 15. 로직\nplain\n"
    )
    findings = check_isolated_components(skel)
    targets = {f.target for f in findings}
    # GameScreen 만 길이 ≥ 4 이고 CamelCase. Id/Ok/Game 은 너무 짧거나 단일 단어
    assert "GameScreen" in targets
    assert "Id" not in targets
    assert "Ok" not in targets


# ── §16 task → 본문 reference ────────────────────────────────────────


def test_task_with_section_reference_passes() -> None:
    skel = "## 13. 컴포넌트\nGameScreen\n"
    tasks = (
        "| ID | Agent | Dep | Desc | Status |\n"
        "|----|-------|-----|------|--------|\n"
        "| T-001 | be | - | §15 의 onTap 함수 구현 | done |\n"
    )
    assert check_task_skeleton_references(tasks, skel) == []


def test_task_with_component_reference_passes() -> None:
    skel = "## 13. 컴포넌트\n<GameScreen> <PushToTalkButton>\n"
    tasks = (
        "| ID | Agent | Dep | Desc | Status |\n"
        "|----|-------|-----|------|--------|\n"
        "| T-001 | be | - | PushToTalkButton 컴포넌트 구현 | done |\n"
    )
    assert check_task_skeleton_references(tasks, skel) == []


def test_task_with_no_reference_flagged() -> None:
    skel = "## 13. 컴포넌트\n<GameScreen>\n"
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
    skel = "## 13. 컴포넌트\n<GameScreen>\n"
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
        "## 13. 컴포넌트\n<GameScreen> <OrphanedWidget>\n"
        "## 14. 상태\nGameScreen\n"
        "## 15. 로직\nGameScreen\n"
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
    skel = "## 13. 컴포넌트\n<GameScreen> <OrphanedWidget>\n## 14. 상태\nGameScreen\n## 15. 로직\nGameScreen\n"
    findings = run_all_checks(skeleton_text=skel)
    targets = {f.target for f in findings}
    assert "OrphanedWidget" in targets
    assert all(not f.target.startswith("T-") for f in findings)


def test_run_all_empty_tasks_text_runs_check() -> None:
    """tasks_text='' (빈 파일) 은 None 과 다름 — task check 실행하되 0 finding."""
    skel = "## 13. 컴포넌트\n<GameScreen>\n## 14. 상태\nGameScreen\n## 15. 로직\nGameScreen\n"
    # 빈 tasks_text 도 task check 가 실행되지만 매칭되는 행이 없어 0 finding.
    findings = run_all_checks(skeleton_text=skel, tasks_text="")
    assert all(not f.target.startswith("T-") for f in findings)


def test_finding_dataclass_fields() -> None:
    """ConsistencyFinding 의 필수 필드 4개 모두 채워짐."""
    skel = "## 13. 컴포넌트\n<GameScreen>\n## 14. 상태\nplain\n## 15. 로직\nplain\n"
    findings = check_isolated_components(skel)
    assert len(findings) == 1
    f = findings[0]
    assert isinstance(f, ConsistencyFinding)
    assert f.severity in ("info", "warn")
    assert f.pattern
    assert f.message
    assert f.target
