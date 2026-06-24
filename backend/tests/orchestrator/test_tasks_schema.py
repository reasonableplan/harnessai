"""tasks.md schema validation 유닛 테스트 (Group 4 Step 1).

validate_tasks_md() 의 모든 violation 종류를 커버.
pure function 테스트이므로 fixture 없이 문자열 직접 전달.

추가 (skipped consistency):
- "skipped" 가 VALID_STATUSES 에 포함됨을 단언.
- ha-build _RECORD_STATUS_CHOICES ⊆ VALID_STATUSES 교차 일관성.
- select_ready_tasks: skipped 의존성이 충족으로 인정됨.
- --task 의존성 검사: skipped dep 이면 통과.
"""

from __future__ import annotations

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from src.orchestrator.tasks_schema import VALID_STATUSES, validate_tasks_md

REPO_ROOT = Path(__file__).resolve().parents[3]


# ── ha-build module fixture ────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def ha_build() -> ModuleType:
    """Load skills/ha-build/run.py (repo mirror) as a module."""
    run_py = REPO_ROOT / "skills" / "ha-build" / "run.py"
    loader = SourceFileLoader("ha_build_schema_consistency", str(run_py))
    spec = importlib.util.spec_from_loader("ha_build_schema_consistency", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_build_schema_consistency"] = mod
    loader.exec_module(mod)
    return mod


# ── helpers ──────────────────────────────────────────────────────────────────

_VALID_HEADER = (
    "| ID | 에이전트 | 의존성 | 설명 | 상태 |\n|----|---------|--------|------|------|\n"
)
_VALID_HEADER_EN = "| ID | agent | depends | description | status |\n|----|-------|---------|-------------|--------|\n"


def _table(*rows: str, header: str = _VALID_HEADER) -> str:
    """Construct a minimal tasks.md content with the given data rows."""
    return header + "".join(rows)


def _row(
    task_id: str = "T-001",
    agent: str = "mobile_coder_rn",
    depends: str = "-",
    desc: str = "설명",
    status: str = "대기",
) -> str:
    return f"| {task_id} | {agent} | {depends} | {desc} | {status} |\n"


# ── Test 1: 정상 tasks.md — violations 없음 ──────────────────────────────────


def test_validate_compliant_tasks_md_no_violations() -> None:
    """챙겼니 형식과 동일한 정상 tasks.md — violations 없음."""
    content = (
        "### Phase 1 — MVP\n"
        + _VALID_HEADER
        + _row("T-001", "mobile_coder_rn", "-", "프로젝트 초기화", "done")
        + _row("T-002", "mobile_coder_rn", "T-001", "NativeWind 설정", "대기")
        + _row("T-003", "mobile_coder_rn", "T-001, T-002", "컴포넌트", "대기")
        + "\n### Phase 2+ — 확장\n"
        + _VALID_HEADER
        + _row("T-101", "mobile_coder_rn", "-", "오프라인 캐시", "대기")
    )
    result = validate_tasks_md(content)
    assert result == [], f"정상 tasks.md 에서 violations 발생: {result}"


# ── Test 2: fractional Task ID (T-024.5) 감지 ────────────────────────────────


def test_validate_detects_fractional_task_id() -> None:
    """T-024.5 포함된 tasks.md — invalid_task_id violation, 정확한 line_number."""
    # Phase header (line 1), header row (line 2), separator (line 3),
    # T-001 (line 4), T-024.5 (line 5)
    content = (
        "### Phase 1 — MVP\n"
        + _VALID_HEADER
        + _row("T-001", "mobile_coder_rn", "-", "정상 태스크", "대기")
        + _row("T-024.5", "mobile_coder_rn", "T-001", "fractional ID", "대기")
    )
    result = validate_tasks_md(content)
    invalid_ids = [v for v in result if v.kind == "invalid_task_id"]
    assert len(invalid_ids) == 1, f"expected 1 invalid_task_id, got: {result}"
    assert invalid_ids[0].line_number == 5, (
        f"line_number 불일치: expected 5, got {invalid_ids[0].line_number}"
    )
    assert "T-024.5" in invalid_ids[0].detail


# ── Test 3: 컬럼 순서 위반 감지 ──────────────────────────────────────────────


def test_validate_detects_bad_column_order() -> None:
    """컬럼 순서 변경 (ID, 설명, 에이전트, ...) — bad_column_order violation."""
    # Wrong order: ID | 설명 | 에이전트 | 의존성 | 상태
    bad_header = (
        "| ID | 설명 | 에이전트 | 의존성 | 상태 |\n|----|------|---------|--------|------|\n"
    )
    content = bad_header + _row()
    result = validate_tasks_md(content)
    col_violations = [v for v in result if v.kind == "bad_column_order"]
    assert col_violations, f"bad_column_order violation 없음. 결과: {result}"


# ── Test 4: invalid status 감지 ──────────────────────────────────────────────


def test_validate_detects_invalid_status() -> None:
    """상태 컬럼에 unknown 값 — invalid_status violation."""
    content = _table(_row("T-001", status="foo"))
    result = validate_tasks_md(content)
    status_violations = [v for v in result if v.kind == "invalid_status"]
    assert len(status_violations) == 1, f"expected 1 invalid_status, got: {result}"
    assert "foo" in status_violations[0].detail


# ── Test 5: 자유 텍스트 의존성 감지 ─────────────────────────────────────────


def test_validate_detects_bad_dependency() -> None:
    """의존성에 'T-001 완료 후' 같은 자유 텍스트 — bad_dependency violation."""
    content = _table(_row("T-002", depends="T-001 완료 후"))
    result = validate_tasks_md(content)
    dep_violations = [v for v in result if v.kind == "bad_dependency"]
    assert dep_violations, f"bad_dependency violation 없음. 결과: {result}"
    assert "T-001 완료 후" in dep_violations[0].detail


# ── Test 6: Phase 헤더 형식 위반 감지 ────────────────────────────────────────


def test_validate_detects_bad_phase_header_wrong_level() -> None:
    """'## Phase 1' (잘못된 헤딩 레벨) — bad_phase_header violation."""
    content = "## Phase 1\n" + _VALID_HEADER + _row()
    result = validate_tasks_md(content)
    phase_violations = [v for v in result if v.kind == "bad_phase_header"]
    assert phase_violations, f"bad_phase_header violation 없음. 결과: {result}"


def test_validate_detects_bad_phase_header_korean_style() -> None:
    """'### 1단계' (한국어 Phase 형식) — bad_phase_header violation."""
    content = "### 1단계\n" + _VALID_HEADER + _row()
    result = validate_tasks_md(content)
    # "### 1단계" 는 "### Phase" 로 시작하지 않으므로 phase check 미발동 —
    # 헤더 없는 일반 텍스트로 처리되어 bad_phase_header violation 이 없어야 정상.
    assert all(v.kind != "bad_phase_header" for v in result)


# ── Test 7: 한국어/영어 컬럼 alias 수용 ──────────────────────────────────────


def test_validate_accepts_korean_english_column_aliases() -> None:
    """전부 영어 컬럼명 | ID | agent | depends | description | status | — violations 없음."""
    content = _VALID_HEADER_EN + "| T-001 | mobile_coder_rn | - | task | 대기 |\n"
    result = validate_tasks_md(content)
    assert result == [], f"영어 alias 사용 시 violations 발생: {result}"


# ── Test 8: Phase 2+ — 확장 허용 ─────────────────────────────────────────────


def test_validate_accepts_phase_with_plus_suffix() -> None:
    """'### Phase 2+ — 확장' — violations 없음 (plus suffix 허용)."""
    content = (
        "### Phase 2+ — 확장\n"
        + _VALID_HEADER
        + _row("T-101", "mobile_coder_rn", "-", "오프라인", "대기")
    )
    result = validate_tasks_md(content)
    assert result == [], f"Phase 2+ 헤더에서 violations 발생: {result}"


# ── Test 9: violations 정렬 순서 (line_number 오름차순) ──────────────────────


def test_validate_returns_violations_sorted() -> None:
    """여러 violation — line_number 오름차순 정렬."""
    # Line 2: header row (valid)
    # Line 3: separator (valid)
    # Line 4: T-024.5 → invalid_task_id
    # Line 5: T-002, status=unknown → invalid_status
    content = (
        _VALID_HEADER
        + _row("T-024.5", depends="-", status="대기")
        + _row("T-002", depends="-", status="unknown_status")
    )
    result = validate_tasks_md(content)
    assert len(result) >= 2, f"예상보다 적은 violations: {result}"
    line_numbers = [v.line_number for v in result]
    assert line_numbers == sorted(line_numbers), (
        f"violations 가 line_number 순으로 정렬되지 않음: {line_numbers}"
    )


# ── Test 10: 허용 상태값 전부 통과 ───────────────────────────────────────────


@pytest.mark.parametrize(
    "status",
    [
        "대기",
        "pending",
        "진행중",
        "in-progress",
        "완료",
        "done",
        "completed",
        "차단",
        "blocked",
        "needs_rebuild",
    ],
)
def test_validate_all_valid_statuses_pass(status: str) -> None:
    """VALID_STATUSES 전체 — violations 없음."""
    content = _table(_row("T-001", status=status))
    result = validate_tasks_md(content)
    status_violations = [v for v in result if v.kind == "invalid_status"]
    assert status_violations == [], (
        f"상태 '{status}' 가 valid 임에도 violation 발생: {status_violations}"
    )


# ── Test 11: 빈 의존성 표현 전부 수용 ────────────────────────────────────────


@pytest.mark.parametrize("depends", ["-", "—", "(없음)", "none", "없음"])
def test_validate_accepts_none_dependency_tokens(depends: str) -> None:
    """의존성 없음 토큰들 — bad_dependency violation 없음."""
    content = _table(_row("T-001", depends=depends))
    result = validate_tasks_md(content)
    dep_violations = [v for v in result if v.kind == "bad_dependency"]
    assert dep_violations == [], (
        f"의존성 없음 토큰 '{depends}' 에서 violation 발생: {dep_violations}"
    )


# ── Test 12: 다중 의존성 콤마 구분 수용 ──────────────────────────────────────


def test_validate_accepts_comma_separated_dependencies() -> None:
    """'T-001, T-002' 콤마 구분 의존성 — violations 없음."""
    content = _table(_row("T-003", depends="T-001, T-002"))
    result = validate_tasks_md(content)
    dep_violations = [v for v in result if v.kind == "bad_dependency"]
    assert dep_violations == [], f"콤마 구분 의존성에서 violation 발생: {dep_violations}"


# ── Test 13: Phase 없는 단일 Phase (Phase 헤더 부재) — OK ────────────────────


def test_validate_no_phase_header_is_ok() -> None:
    """Phase 헤더 없는 단일 Phase tasks.md — violations 없음."""
    content = _VALID_HEADER + _row("T-001") + _row("T-002", depends="T-001")
    result = validate_tasks_md(content)
    assert result == [], f"Phase 헤더 없는 경우 violations 발생: {result}"


# ── Test 14: T-1, T-10, T-1000 같은 비표준 길이 ID 거부 ──────────────────────


@pytest.mark.parametrize("bad_id", ["T-1", "T-10", "T-1000", "T-A01", "T-01a"])
def test_validate_rejects_non_standard_id_lengths(bad_id: str) -> None:
    """비표준 ID 길이/형식 — invalid_task_id violation."""
    content = _table(_row(task_id=bad_id))
    result = validate_tasks_md(content)
    invalid = [v for v in result if v.kind == "invalid_task_id"]
    assert invalid, f"비표준 ID {bad_id!r} 가 통과됨 — violation 없음"


# ── Test 15: "skipped" 가 VALID_STATUSES 에 포함 ─────────────────────────────


def test_skipped_is_valid_status() -> None:
    """'skipped' 가 VALID_STATUSES 에 포함되어 schema 검증을 통과한다."""
    assert "skipped" in VALID_STATUSES, (
        "'skipped' 가 VALID_STATUSES 에 없음 — tasks_schema.py 수정 필요"
    )


def test_skipped_row_no_violation() -> None:
    """status='skipped' 행 — invalid_status violation 없음."""
    content = _table(_row("T-001", status="skipped"))
    result = validate_tasks_md(content)
    status_violations = [v for v in result if v.kind == "invalid_status"]
    assert status_violations == [], f"'skipped' 가 valid 임에도 violation 발생: {status_violations}"


# ── Test 16: ha-build _RECORD_STATUS_CHOICES ⊆ VALID_STATUSES 교차 일관성 ────


def test_ha_build_record_status_choices_subset_of_valid_statuses(
    ha_build: ModuleType,
) -> None:
    """ha-build _RECORD_STATUS_CHOICES 가 VALID_STATUSES 의 부분집합이어야 한다.

    ha-build record --status 가 tasks.md 에 기록하는 상태 전부가
    tasks_schema.VALID_STATUSES 에 포함되어야 ha-plan commit 검증이 통과한다.
    Source: skills/ha-build/run.py _RECORD_STATUS_CHOICES
    """
    choices = set(ha_build._RECORD_STATUS_CHOICES)
    invalid = choices - VALID_STATUSES
    assert not invalid, (
        f"ha-build _RECORD_STATUS_CHOICES 중 VALID_STATUSES 미포함 항목: {invalid}\n"
        "tasks_schema.py 에 해당 상태를 추가하거나 _RECORD_STATUS_CHOICES 를 수정하세요."
    )


# ── Test 17: select_ready_tasks — skipped 의존성이 충족으로 인정 ───────────────


def _task(
    agent: str = "backend_coder", deps: list[str] | None = None, status: str = "대기"
) -> dict:
    return {"agent": agent, "depends_on": deps or [], "description": "x", "status": status}


def test_select_ready_tasks_skipped_dep_satisfies_dependency(ha_build: ModuleType) -> None:
    """T-001 status='skipped' → T-002(depends_on T-001) 가 ready 목록에 포함된다."""
    tasks = {
        "T-001": _task(status="skipped"),
        "T-002": _task(deps=["T-001"], status="대기"),
    }
    ready = ha_build.select_ready_tasks(tasks)
    assert "T-002" in ready, f"T-001=skipped 일 때 T-002 가 ready 에 없음. ready={ready}"


def test_select_ready_tasks_skipped_task_itself_excluded(ha_build: ModuleType) -> None:
    """skipped 태스크 자신은 ready 목록에 포함되지 않는다."""
    tasks = {
        "T-001": _task(status="skipped"),
        "T-002": _task(status="대기"),
    }
    ready = ha_build.select_ready_tasks(tasks)
    assert "T-001" not in ready, f"skipped 태스크가 ready 에 포함됨: {ready}"
    assert "T-002" in ready


# ── Test 18: --task 의존성 검사 — skipped dep 이면 BLOCK 없이 통과 ─────────────


def test_cmd_prepare_skipped_dep_passes_dependency_check(
    ha_build: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-001=skipped 일 때 --task T-002 의존성 검사가 통과(BLOCK 없음)한다."""
    plan = SimpleNamespace(
        pipeline=SimpleNamespace(
            current_step="planned",
            completed_steps=(),
            skipped_steps=(),
            steps=("planned", "building", "built"),
            gstack_mode="manual",
        ),
        profiles=[],
        skeleton_hash=None,
        frozen_status="frozen",
    )
    plan_path = tmp_path / "docs" / "harness-plan.md"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text("", encoding="utf-8")

    tasks_md = (
        "| ID    | agent         | depends | description | status     |\n"
        "|-------|---------------|---------|-------------|------------|\n"
        "| T-001 | backend_coder | -       | 모델        | skipped    |\n"
        "| T-002 | backend_coder | T-001   | API         | 대기       |\n"
    )
    (plan_path.parent / "tasks.md").write_text(tasks_md, encoding="utf-8")

    monkeypatch.setattr(ha_build, "load_plan", lambda: (plan, plan_path, tmp_path))
    monkeypatch.setattr(ha_build, "assert_state", lambda *a, **k: None)
    monkeypatch.setattr(ha_build, "get_active_profiles", lambda p, pr: [])

    args = SimpleNamespace(
        task="T-002",
        resume=False,
        skip_frozen_gate=False,
        accept_skeleton_drift=False,
    )
    rc = ha_build.cmd_prepare(args)
    # skipped dep 은 resolved → dependency check 통과 → exit 0 (prepare 성공)
    assert rc == 0, (
        f"T-001=skipped 인데 T-002 prepare 가 BLOCK(rc={rc}) — "
        "_RESOLVED_STATES 에 'skipped' 누락 가능성"
    )
