"""ha-redesign run.py 통합 테스트.

대상: `skills/ha-redesign/run.py::cmd_prepare`, `cmd_commit`
전략: tmp_path 에 minimal harness-plan + skeleton + tasks 생성 후 argparse Namespace 로
      cmd_* 직접 호출. monkeypatch 로 cwd / project_root 가 임시 디렉토리 향하게.
"""

from __future__ import annotations

import importlib.util
import sys
from argparse import Namespace
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_ha_redesign() -> ModuleType:
    loader = SourceFileLoader(
        "ha_redesign_run", str(REPO_ROOT / "skills" / "ha-redesign" / "run.py")
    )
    spec = importlib.util.spec_from_loader("ha_redesign_run", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_redesign_run"] = mod
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ha_redesign() -> ModuleType:
    return _load_ha_redesign()


def _seed_project(
    tmp_path: Path,
    *,
    current_step: str = "planned",
    skeleton_body: str | None = None,
    tasks_body: str | None = None,
) -> Path:
    """harness-plan / skeleton / tasks 를 가진 minimal project 디렉토리 생성."""
    docs = tmp_path / "docs"
    docs.mkdir()

    plan_text = (
        "---\n"
        "harness_version: 2\n"
        "schema_version: 1\n"
        "project_name: redesign_test\n"
        "created_at: 2026-05-09T00:00:00+00:00\n"
        "updated_at: 2026-05-09T00:00:00+00:00\n"
        "project_type: cli\n"
        "scale: small\n"
        "scale_axes:\n"
        "  user_scale: small\n"
        "  data_sensitivity: none\n"
        "  team_size: solo\n"
        "  availability: standard\n"
        "  monetization: none\n"
        "  lifecycle: mvp\n"
        "user_description_original: redesign integration test\n"
        "profiles: []\n"
        "skeleton_sections:\n"
        "  required: []\n"
        "  optional: []\n"
        "  included: []\n"
        "pipeline:\n"
        "  steps: [ha-init, ha-design, ha-plan]\n"
        f"  current_step: {current_step}\n"
        "  completed_steps: [ha-init, ha-design, ha-plan]\n"
        "  skipped_steps: []\n"
        "  gstack_mode: manual\n"
        "verify_history: []\n"
        "backups: []\n"
        "last_activity: 2026-05-09T00:00:00+00:00\n"
        "---\nbody\n"
    )
    (docs / "harness-plan.md").write_text(plan_text, encoding="utf-8")

    default_skel = (
        "# skeleton\n\n"
        "## 1. 프로젝트 개요\noverview\n\n"
        "## 2. 기능 요구사항\nfeatures\n\n"
        "## 13. 컴포넌트 트리\ncomponents\n\n"
        "## 15. 도메인 로직\ndomain\n"
    )
    (docs / "skeleton.md").write_text(skeleton_body or default_skel, encoding="utf-8")

    default_tasks = (
        "# Tasks\n\n"
        "| ID | Agent | Depends | Desc | Status |\n"
        "|----|-------|---------|------|--------|\n"
        "| T-001 | backend_coder | - | x | done |\n"
        "| T-002 | frontend_coder | T-001 | y | 대기 |\n"
    )
    (docs / "tasks.md").write_text(tasks_body or default_tasks, encoding="utf-8")
    return tmp_path


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Seeded project + cwd switched to it (project_root() returns this)."""
    proj = _seed_project(tmp_path)
    monkeypatch.chdir(proj)
    return proj


def _ns(**kwargs) -> Namespace:
    """argparse Namespace shorthand."""
    return Namespace(**kwargs)


# ── prepare ──────────────────────────────────────────────────────────


def test_prepare_records_proposed_entry(
    ha_redesign: ModuleType,
    project: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = ha_redesign.cmd_prepare(_ns(decision="CEO pivot test", rationale="unit test source"))
    assert rc == 0

    # plan 갱신 검증
    plan_text = (project / "docs" / "harness-plan.md").read_text(encoding="utf-8")
    assert "CEO pivot test" in plan_text
    assert "proposed" in plan_text

    # JSON 출력 검증
    out = capsys.readouterr().out
    assert '"current_step": "planned"' in out
    assert '"redesign_history_count": 1' in out


def test_prepare_enumerates_skeleton_and_tasks(
    ha_redesign: ModuleType,
    project: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ha_redesign.cmd_prepare(_ns(decision="d", rationale="r"))
    out = capsys.readouterr().out
    # §1, §2, §13, §15 enumerate
    assert '"id": "§1"' in out
    assert '"id": "§13"' in out
    # T-001, T-002 enumerate
    assert '"id": "T-001"' in out
    assert '"id": "T-002"' in out


def test_prepare_blocked_in_init_state(
    ha_redesign: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """init 상태에서는 redesign 차단 (assert_state)."""
    proj = _seed_project(tmp_path, current_step="init")
    monkeypatch.chdir(proj)
    with pytest.raises(SystemExit) as exc_info:
        ha_redesign.cmd_prepare(_ns(decision="d", rationale="r"))
    assert exc_info.value.code == 2  # assert_state 의 exit code


# ── commit — affected_* 검증 ─────────────────────────────────────────


def test_commit_approved_with_valid_affected(
    ha_redesign: ModuleType,
    project: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = ha_redesign.cmd_commit(
        _ns(
            decision="d",
            rationale="r",
            status="approved",
            affected_sections="§1,§13",
            affected_tasks="T-001,T-002",
        )
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert '"status": "approved"' in out
    assert '"redesign_history_count": 1' in out


def test_commit_approved_rejects_phantom_section(
    ha_redesign: ModuleType,
    project: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = ha_redesign.cmd_commit(
        _ns(
            decision="d",
            rationale="r",
            status="approved",
            affected_sections="§1,§99",  # §99 doesn't exist
            affected_tasks="",
        )
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert "§99" in err
    # plan 은 갱신되지 않아야
    plan_text = (project / "docs" / "harness-plan.md").read_text(encoding="utf-8")
    assert "approved" not in plan_text


def test_commit_approved_rejects_phantom_task(
    ha_redesign: ModuleType,
    project: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = ha_redesign.cmd_commit(
        _ns(
            decision="d",
            rationale="r",
            status="approved",
            affected_sections="§1",
            affected_tasks="T-999",  # doesn't exist
        )
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert "T-999" in err


def test_commit_rejected_skips_validation(
    ha_redesign: ModuleType,
    project: Path,
) -> None:
    """rejected 는 propagation duty 가 없으므로 phantom ID 도 통과 (audit-only)."""
    rc = ha_redesign.cmd_commit(
        _ns(
            decision="d",
            rationale="r",
            status="rejected",
            affected_sections="§99",  # phantom OK in rejected
            affected_tasks="T-999",
        )
    )
    assert rc == 0
    plan_text = (project / "docs" / "harness-plan.md").read_text(encoding="utf-8")
    assert "rejected" in plan_text


def test_commit_invalid_status_rejected(
    ha_redesign: ModuleType,
    project: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """proposed 는 prepare 전용 — commit 으로 들어오면 거부."""
    rc = ha_redesign.cmd_commit(
        _ns(
            decision="d",
            rationale="r",
            status="proposed",  # not allowed in commit
            affected_sections="",
            affected_tasks="",
        )
    )
    assert rc == 2


# ── full lifecycle ──────────────────────────────────────────────────


def test_full_lifecycle_proposed_approved_applied(
    ha_redesign: ModuleType,
    project: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """prepare → commit approved → commit applied — 3 entries 누적, 모두 보존."""
    ha_redesign.cmd_prepare(_ns(decision="lifecycle test", rationale="r"))
    capsys.readouterr()  # drain

    ha_redesign.cmd_commit(
        _ns(
            decision="lifecycle test",
            rationale="r",
            status="approved",
            affected_sections="§13",
            affected_tasks="T-002",
        )
    )
    capsys.readouterr()

    ha_redesign.cmd_commit(
        _ns(
            decision="lifecycle test",
            rationale="r",
            status="applied",
            affected_sections="§13",
            affected_tasks="T-002",
        )
    )
    out = capsys.readouterr().out
    assert '"redesign_history_count": 3' in out

    plan_text = (project / "docs" / "harness-plan.md").read_text(encoding="utf-8")
    # 3 statuses 전부 audit trail 에
    for status in ("proposed", "approved", "applied"):
        assert status in plan_text


# ── consistency_findings (Phase 4) ───────────────────────────────────


def test_applied_emits_consistency_findings_field(
    ha_redesign: ModuleType,
    project: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """applied 시점에 consistency_findings 필드가 출력 JSON 에 포함."""
    rc = ha_redesign.cmd_commit(
        _ns(
            decision="d",
            rationale="r",
            status="applied",
            affected_sections="§13",
            affected_tasks="T-001",
        )
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert '"consistency_findings"' in out


def test_approved_does_not_run_consistency(
    ha_redesign: ModuleType,
    project: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """approved 단계는 skeleton 갱신 전 — consistency 검증 안 함 (빈 list)."""
    rc = ha_redesign.cmd_commit(
        _ns(
            decision="d",
            rationale="r",
            status="approved",
            affected_sections="§13",
            affected_tasks="T-001",
        )
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert '"consistency_findings": []' in out


def test_applied_detects_isolated_component(
    ha_redesign: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """§13 에 정의된 컴포넌트가 §14/§15 에 안 등장하면 isolated-component finding."""
    skel = (
        "## 13. 컴포넌트 트리\n"
        "<GameScreen> <OrphanedWidget> ...\n\n"
        "## 14. 상태 흐름\n"
        "GameScreen 만 등장.\n\n"
        "## 15. 도메인 로직\n"
        "GameScreen 만.\n"
    )
    proj = _seed_project(tmp_path, skeleton_body=skel)
    monkeypatch.chdir(proj)

    rc = ha_redesign.cmd_commit(
        _ns(
            decision="d",
            rationale="r",
            status="applied",
            affected_sections="§13",
            affected_tasks="",
        )
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "OrphanedWidget" in out
    assert "isolated-component" in out


# ── F3: 섹션 hash 기반 결정론적 rebuild 파생 ─────────────────────────


def test_tasks_referencing_sections_matches_exact_and_prefix(ha_redesign) -> None:
    """'skeleton 참조' 가 변경 섹션 ID (정확 일치 또는 'id.' prefix) 를 가리키는
    task 만 문서 순으로 반환한다."""
    tasks_text = (
        "### T-001 — users 모델\n"
        "- **skeleton 참조**: persistence.users\n\n"
        "### T-002 — auth API\n"
        "- **skeleton 참조**: interface.http.auth, auth\n\n"
        "### T-003 — 화면\n"
        "- **skeleton 참조**: view.screens\n"
    )
    fn = ha_redesign._tasks_referencing_sections
    assert fn(tasks_text, ["persistence"]) == ["T-001"]
    assert fn(tasks_text, ["auth"]) == ["T-002"]
    # dot 포함 섹션 ID 자체도 매칭 (interface.http → interface.http.auth)
    assert fn(tasks_text, ["interface.http"]) == ["T-002"]
    assert fn(tasks_text, ["core.logic"]) == []


def test_tasks_referencing_sections_ignores_blocks_without_ref(ha_redesign) -> None:
    """'skeleton 참조' 줄이 없는 spec 블록은 파생 대상에서 제외."""
    tasks_text = "### T-001 — 기타 작업\n- 설명만 있음\n"
    assert ha_redesign._tasks_referencing_sections(tasks_text, ["auth"]) == []
