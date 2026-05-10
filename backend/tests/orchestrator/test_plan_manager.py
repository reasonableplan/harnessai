"""plan_manager 단위 테스트.

모든 픽스처는 tmp_path 기반.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.orchestrator.plan_manager import (
    STATE_ORDER,
    HarnessPlan,
    InvalidStateTransitionError,
    PlanManager,
    PlanNotFoundError,
    PlanSchemaError,
    ProfileRef,
    RedesignEntry,
    ScaleAxes,
    SkeletonSpec,
)


def _sample_plan() -> HarnessPlan:
    """테스트용 기본 plan 생성."""
    pm = PlanManager()
    return pm.create(
        project_name="Sample",
        project_type="CLI 개인 도구",
        scale="small",
        user_description_original="간단한 CLI 만들 거야",
        profiles=[ProfileRef(id="python-cli", path="backend/")],
        skeleton_sections=SkeletonSpec(
            required=("overview", "stack", "interface.cli"),
            optional=("persistence",),
            included=("overview", "stack", "interface.cli"),
        ),
        pipeline_steps=["ha-init", "ha-design", "ha-plan", "ha-build", "ha-verify"],
    )


# ── 생성 ─────────────────────────────────────────────────────────────


def test_create_initial_state(tmp_path: Path) -> None:
    plan = _sample_plan()
    assert plan.pipeline.current_step == "init"
    assert plan.pipeline.completed_steps == ()
    assert plan.pipeline.gstack_mode == "manual"
    assert plan.created_at  # 비어있지 않아야


def test_create_invalid_scale_raises() -> None:
    pm = PlanManager()
    with pytest.raises(PlanSchemaError, match="scale"):
        pm.create(
            project_name="X",
            project_type="x",
            scale="huge",  # 잘못된 값
            user_description_original="",
            profiles=[],
            skeleton_sections=SkeletonSpec((), (), ()),
            pipeline_steps=[],
        )


def test_create_invalid_gstack_mode_raises() -> None:
    pm = PlanManager()
    with pytest.raises(PlanSchemaError, match="gstack_mode"):
        pm.create(
            project_name="X",
            project_type="x",
            scale="small",
            user_description_original="",
            profiles=[],
            skeleton_sections=SkeletonSpec((), (), ()),
            pipeline_steps=[],
            gstack_mode="invalid",
        )


# ── 저장/로드 라운드트립 ──────────────────────────────────────────────


def test_save_load_roundtrip(tmp_path: Path) -> None:
    pm = PlanManager()
    original = _sample_plan()
    original.body = "# Sample\n\n## Notes\nhello\n"
    path = tmp_path / "harness-plan.md"
    pm.save(original, path)

    loaded = pm.load(path)
    assert loaded.project_name == original.project_name
    assert loaded.project_type == original.project_type
    assert loaded.scale == original.scale
    assert loaded.user_description_original == original.user_description_original
    assert loaded.profiles == original.profiles
    assert loaded.skeleton_sections == original.skeleton_sections
    assert loaded.pipeline.current_step == original.pipeline.current_step
    assert loaded.pipeline.steps == original.pipeline.steps
    assert "## Notes" in loaded.body


def test_load_missing_raises(tmp_path: Path) -> None:
    pm = PlanManager()
    with pytest.raises(PlanNotFoundError):
        pm.load(tmp_path / "ghost.md")


def test_load_no_frontmatter_raises(tmp_path: Path) -> None:
    pm = PlanManager()
    p = tmp_path / "x.md"
    p.write_text("# Just a heading", encoding="utf-8")
    with pytest.raises(PlanSchemaError, match="frontmatter"):
        pm.load(p)


def test_load_invalid_yaml_raises(tmp_path: Path) -> None:
    pm = PlanManager()
    p = tmp_path / "x.md"
    p.write_text("---\nkey: value: bad\n---\nbody", encoding="utf-8")
    with pytest.raises(PlanSchemaError, match="YAML"):
        pm.load(p)


def test_save_updates_timestamps(tmp_path: Path) -> None:
    pm = PlanManager()
    plan = _sample_plan()
    # save가 updated_at 을 새로 갱신하는지 확인 — 강제 옛 값 주입
    plan.updated_at = "2020-01-01T00:00:00+00:00"
    pm.save(plan, tmp_path / "harness-plan.md")
    assert plan.updated_at != "2020-01-01T00:00:00+00:00"
    assert plan.last_activity == plan.updated_at


# ── 상태 전이 ─────────────────────────────────────────────────────────


def test_transition_one_step_forward() -> None:
    pm = PlanManager()
    plan = _sample_plan()
    assert plan.pipeline.current_step == "init"
    pm.transition(plan, "designed", completed_step="ha-design")
    assert plan.pipeline.current_step == "designed"
    assert "ha-design" in plan.pipeline.completed_steps


def test_transition_full_chain() -> None:
    pm = PlanManager()
    plan = _sample_plan()
    sequence = ["designed", "planned", "building", "built", "verified", "reviewed", "shipped"]
    for state in sequence:
        pm.transition(plan, state, completed_step=f"step-{state}")
    assert plan.pipeline.current_step == "shipped"
    assert len(plan.pipeline.completed_steps) == len(sequence)


def test_transition_skipping_raises() -> None:
    """init → planned 같은 건너뛰기는 불가."""
    pm = PlanManager()
    plan = _sample_plan()
    with pytest.raises(InvalidStateTransitionError, match="skip"):
        pm.transition(plan, "planned")


def test_transition_backward_raises() -> None:
    pm = PlanManager()
    plan = _sample_plan()
    pm.transition(plan, "designed")
    with pytest.raises(InvalidStateTransitionError, match="backward"):
        pm.transition(plan, "init")


def test_transition_unknown_state_raises() -> None:
    pm = PlanManager()
    plan = _sample_plan()
    with pytest.raises(InvalidStateTransitionError, match="unknown"):
        pm.transition(plan, "totally-fake")


def test_transition_idempotent_same_state() -> None:
    """같은 상태로 다시 전이 — 에러 없이 step만 추가."""
    pm = PlanManager()
    plan = _sample_plan()
    pm.transition(plan, "designed", completed_step="ha-design")
    pm.transition(plan, "designed", completed_step="plan-eng-review")
    assert plan.pipeline.current_step == "designed"
    assert "ha-design" in plan.pipeline.completed_steps
    assert "plan-eng-review" in plan.pipeline.completed_steps


def test_transition_no_duplicate_completed_step() -> None:
    pm = PlanManager()
    plan = _sample_plan()
    pm.transition(plan, "designed", completed_step="ha-design")
    pm.transition(plan, "designed", completed_step="ha-design")
    # 같은 step 두 번 — completed_steps에 한 번만
    assert plan.pipeline.completed_steps.count("ha-design") == 1


# ── 검증 이력 ─────────────────────────────────────────────────────────


def test_record_verify_appends_history() -> None:
    pm = PlanManager()
    plan = _sample_plan()
    pm.record_verify(plan, step="ha-verify", passed=True, summary="247 tests")
    assert len(plan.verify_history) == 1
    assert plan.verify_history[0].step == "ha-verify"
    assert plan.verify_history[0].passed is True


def test_record_verify_multiple() -> None:
    pm = PlanManager()
    plan = _sample_plan()
    pm.record_verify(plan, step="ha-verify", passed=False, summary="3 failures")
    pm.record_verify(plan, step="ha-verify", passed=True, summary="all green")
    assert len(plan.verify_history) == 2
    assert plan.verify_history[0].passed is False
    assert plan.verify_history[1].passed is True


# ── 스킵 / 백업 ───────────────────────────────────────────────────────


def test_mark_skipped_adds_step() -> None:
    pm = PlanManager()
    plan = _sample_plan()
    pm.mark_skipped(plan, "office-hours")
    assert "office-hours" in plan.pipeline.skipped_steps


def test_mark_skipped_idempotent() -> None:
    pm = PlanManager()
    plan = _sample_plan()
    pm.mark_skipped(plan, "office-hours")
    pm.mark_skipped(plan, "office-hours")
    assert plan.pipeline.skipped_steps.count("office-hours") == 1


def test_add_backup_records_entry() -> None:
    pm = PlanManager()
    plan = _sample_plan()
    pm.add_backup(plan, path=".backup/skeleton-2026.md", reason="ha-design --reset")
    assert len(plan.backups) == 1
    assert plan.backups[0]["path"] == ".backup/skeleton-2026.md"
    assert plan.backups[0]["reason"] == "ha-design --reset"


# ── 라운드트립 + 상태 전이 통합 ────────────────────────────────────────


def test_save_load_preserves_completed_steps_and_history(tmp_path: Path) -> None:
    pm = PlanManager()
    plan = _sample_plan()
    pm.transition(plan, "designed", completed_step="ha-design")
    pm.transition(plan, "planned", completed_step="ha-plan")
    pm.record_verify(plan, step="ha-verify", passed=True, summary="ok")
    pm.mark_skipped(plan, "office-hours")

    path = tmp_path / "harness-plan.md"
    pm.save(plan, path)
    loaded = pm.load(path)

    assert loaded.pipeline.current_step == "planned"
    assert "ha-design" in loaded.pipeline.completed_steps
    assert "ha-plan" in loaded.pipeline.completed_steps
    assert "office-hours" in loaded.pipeline.skipped_steps
    assert len(loaded.verify_history) == 1
    assert loaded.verify_history[0].summary == "ok"


def test_state_order_constant() -> None:
    """STATE_ORDER 가 변경되면 명시적으로 검토되도록."""
    assert STATE_ORDER == (
        "init",
        "designed",
        "planned",
        "building",
        "built",
        "verified",
        "reviewed",
        "shipped",
    )


# ── ScaleAxes (6축) ──────────────────────────────────────────────────


def test_scale_axes_default_values_on_create() -> None:
    """scale_axes 미지정 시 기본값으로 채워져야."""
    plan = _sample_plan()
    assert plan.scale_axes.user_scale == "small"
    assert plan.scale_axes.data_sensitivity == "none"
    assert plan.scale_axes.team_size == "solo"
    assert plan.scale_axes.availability == "standard"
    assert plan.scale_axes.monetization == "none"
    assert plan.scale_axes.lifecycle == "mvp"


def test_scale_axes_explicit_values_preserved() -> None:
    pm = PlanManager()
    axes = ScaleAxes(
        user_scale="large",
        data_sensitivity="payment",
        team_size="multi",
        availability="high",
        monetization="subscription",
        lifecycle="ga",
    )
    plan = pm.create(
        project_name="X",
        project_type="x",
        scale="medium",
        user_description_original="",
        profiles=[],
        skeleton_sections=SkeletonSpec((), (), ()),
        pipeline_steps=[],
        scale_axes=axes,
    )
    assert plan.scale_axes == axes


def test_scale_axes_round_trip(tmp_path: Path) -> None:
    """save/load 후 6축 값이 보존되어야."""
    pm = PlanManager()
    axes = ScaleAxes(
        user_scale="medium",
        data_sensitivity="pii",
        team_size="small",
        availability="high",
        monetization="ads",
        lifecycle="poc",
    )
    plan = pm.create(
        project_name="RoundTrip",
        project_type="webapp",
        scale="medium",
        user_description_original="",
        profiles=[],
        skeleton_sections=SkeletonSpec((), (), ()),
        pipeline_steps=[],
        scale_axes=axes,
    )
    path = tmp_path / "harness-plan.md"
    pm.save(plan, path)
    loaded = pm.load(path)
    assert loaded.scale_axes == axes


def test_scale_axes_backward_compat_load_without_field(tmp_path: Path) -> None:
    """scale_axes 가 없는 기존 frontmatter 도 로드 가능 — 모두 default."""
    path = tmp_path / "harness-plan.md"
    path.write_text(
        "---\n"
        "harness_version: 2\n"
        "schema_version: 1\n"
        "project_name: Legacy\n"
        "project_type: cli\n"
        "scale: small\n"
        "profiles: []\n"
        "skeleton_sections:\n"
        "  required: []\n"
        "  optional: []\n"
        "  included: []\n"
        "pipeline:\n"
        "  steps: []\n"
        "  current_step: init\n"
        "  completed_steps: []\n"
        "  skipped_steps: []\n"
        "  gstack_mode: manual\n"
        "---\n"
        "body\n",
        encoding="utf-8",
    )
    pm = PlanManager()
    loaded = pm.load(path)
    assert loaded.scale_axes.user_scale == "small"
    assert loaded.scale_axes.data_sensitivity == "none"
    assert loaded.scale_axes.team_size == "solo"
    assert loaded.scale_axes.availability == "standard"
    assert loaded.scale_axes.monetization == "none"
    assert loaded.scale_axes.lifecycle == "mvp"


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("user_scale", "huge"),
        ("data_sensitivity", "secret"),
        ("team_size", "army"),
        ("availability", "always"),
        ("monetization", "donation"),
        ("lifecycle", "alpha"),
    ],
)
def test_scale_axes_invalid_values_raise(field: str, bad_value: str) -> None:
    """6축 각각의 잘못된 값에 PlanSchemaError."""
    kwargs = {
        "user_scale": "small",
        "data_sensitivity": "none",
        "team_size": "solo",
        "availability": "standard",
        "monetization": "none",
        "lifecycle": "mvp",
    }
    kwargs[field] = bad_value
    with pytest.raises(PlanSchemaError, match=field):
        ScaleAxes(**kwargs)


def test_scale_axes_load_with_partial_fields_uses_defaults(tmp_path: Path) -> None:
    """frontmatter 의 scale_axes 가 일부 축만 가지고 있어도 누락분은 default 로 채움."""
    path = tmp_path / "harness-plan.md"
    path.write_text(
        "---\n"
        "harness_version: 2\n"
        "schema_version: 1\n"
        "project_name: Partial\n"
        "scale: small\n"
        "scale_axes:\n"
        "  user_scale: large\n"
        "  monetization: payment\n"
        "profiles: []\n"
        "skeleton_sections:\n"
        "  required: []\n"
        "  optional: []\n"
        "  included: []\n"
        "pipeline:\n"
        "  steps: []\n"
        "  current_step: init\n"
        "  completed_steps: []\n"
        "  skipped_steps: []\n"
        "  gstack_mode: manual\n"
        "---\n"
        "body\n",
        encoding="utf-8",
    )
    pm = PlanManager()
    loaded = pm.load(path)
    # 명시된 두 축은 그대로
    assert loaded.scale_axes.user_scale == "large"
    assert loaded.scale_axes.monetization == "payment"
    # 누락된 네 축은 default
    assert loaded.scale_axes.data_sensitivity == "none"
    assert loaded.scale_axes.team_size == "solo"
    assert loaded.scale_axes.availability == "standard"
    assert loaded.scale_axes.lifecycle == "mvp"


def test_scale_axes_load_with_invalid_value_raises(tmp_path: Path) -> None:
    """frontmatter 에 invalid scale_axes 값이 저장돼 있으면 load 시 PlanSchemaError.

    수동 편집된 YAML 이 잘못된 값을 가진 채 침묵 통과하면 위험 — strict 거부.
    """
    path = tmp_path / "harness-plan.md"
    path.write_text(
        "---\n"
        "harness_version: 2\n"
        "schema_version: 1\n"
        "project_name: BadAxis\n"
        "scale: small\n"
        "scale_axes:\n"
        "  user_scale: huge\n"  # invalid
        "profiles: []\n"
        "skeleton_sections:\n"
        "  required: []\n"
        "  optional: []\n"
        "  included: []\n"
        "pipeline:\n"
        "  steps: []\n"
        "  current_step: init\n"
        "  completed_steps: []\n"
        "  skipped_steps: []\n"
        "  gstack_mode: manual\n"
        "---\n"
        "body\n",
        encoding="utf-8",
    )
    pm = PlanManager()
    with pytest.raises(PlanSchemaError, match="user_scale"):
        pm.load(path)


# ── /ha-redesign — mutation propagation 기록 ──────────────────────────


def test_record_redesign_appends_entry() -> None:
    """첫 redesign proposal 이 빈 history 에 entry 1개 추가."""
    pm = PlanManager()
    plan = _sample_plan()
    assert plan.redesign_history == []

    pm.record_redesign(
        plan,
        decision="CEO pivot: PTT only",
        rationale="/plan-ceo-review — D7 retention 우선",
        affected_sections=("§1", "§13", "§15"),
        affected_tasks=("T-200", "T-201"),
        status="proposed",
    )

    assert len(plan.redesign_history) == 1
    entry = plan.redesign_history[0]
    assert entry.decision == "CEO pivot: PTT only"
    assert entry.affected_sections == ("§1", "§13", "§15")
    assert entry.affected_tasks == ("T-200", "T-201")
    assert entry.status == "proposed"
    assert entry.at  # ISO timestamp 채워짐


def test_record_redesign_full_lifecycle_preserves_audit_trail() -> None:
    """proposed → approved → applied 3 entry 모두 보존 (audit trail).

    Mutation propagation 이력은 압축하지 않음 — rejected 도 남겨야 "왜 안 했는지" 추적 가능.
    """
    pm = PlanManager()
    plan = _sample_plan()

    pm.record_redesign(plan, decision="d1", rationale="r1", status="proposed")
    pm.record_redesign(plan, decision="d1", rationale="r1", status="approved")
    pm.record_redesign(plan, decision="d1", rationale="r1", status="applied")

    assert [e.status for e in plan.redesign_history] == [
        "proposed",
        "approved",
        "applied",
    ]


def test_redesign_invalid_status_raises() -> None:
    """ALLOWED_REDESIGN_STATUS 외 값으로 RedesignEntry 직접 생성 시 PlanSchemaError."""
    with pytest.raises(PlanSchemaError, match="redesign status"):
        RedesignEntry(
            at="2026-05-09T00:00:00+00:00",
            decision="x",
            rationale="x",
            affected_sections=(),
            affected_tasks=(),
            status="completed",  # invalid
        )


def test_redesign_history_save_load_roundtrip(tmp_path: Path) -> None:
    """save → load 후 redesign_history 가 정확히 복원."""
    pm = PlanManager()
    plan = _sample_plan()
    pm.record_redesign(
        plan,
        decision="auth method change",
        rationale="security review",
        affected_sections=("§6", "§19"),
        affected_tasks=("T-005",),
        status="applied",
    )
    path = tmp_path / "harness-plan.md"
    pm.save(plan, path)

    loaded = pm.load(path)
    assert len(loaded.redesign_history) == 1
    e = loaded.redesign_history[0]
    assert e.decision == "auth method change"
    assert e.rationale == "security review"
    assert e.affected_sections == ("§6", "§19")
    assert e.affected_tasks == ("T-005",)
    assert e.status == "applied"


def test_load_invalid_current_step_raises(tmp_path: Path) -> None:
    """frontmatter 의 current_step 이 STATE_ORDER 외 값이면 load 시 PlanSchemaError.

    수동 편집 또는 손상된 YAML 이 침묵 통과하면 transition() 호출 시점에
    혼란스러운 ValueError 로 터짐 — 입구에서 차단.
    """
    path = tmp_path / "harness-plan.md"
    path.write_text(
        "---\n"
        "harness_version: 2\n"
        "schema_version: 1\n"
        "project_name: BadStep\n"
        "scale: small\n"
        "profiles: []\n"
        "skeleton_sections:\n"
        "  required: []\n"
        "  optional: []\n"
        "  included: []\n"
        "pipeline:\n"
        "  steps: []\n"
        "  current_step: bogus\n"  # invalid
        "  completed_steps: []\n"
        "  skipped_steps: []\n"
        "  gstack_mode: manual\n"
        "---\nbody\n",
        encoding="utf-8",
    )
    with pytest.raises(PlanSchemaError, match="current_step"):
        PlanManager().load(path)


def test_load_invalid_gstack_mode_raises(tmp_path: Path) -> None:
    """frontmatter 의 gstack_mode 가 ALLOWED_GSTACK_MODES 외 값이면 PlanSchemaError."""
    path = tmp_path / "harness-plan.md"
    path.write_text(
        "---\n"
        "harness_version: 2\n"
        "schema_version: 1\n"
        "project_name: BadMode\n"
        "scale: small\n"
        "profiles: []\n"
        "skeleton_sections:\n"
        "  required: []\n"
        "  optional: []\n"
        "  included: []\n"
        "pipeline:\n"
        "  steps: []\n"
        "  current_step: init\n"
        "  completed_steps: []\n"
        "  skipped_steps: []\n"
        "  gstack_mode: bogus\n"  # invalid
        "---\nbody\n",
        encoding="utf-8",
    )
    with pytest.raises(PlanSchemaError, match="gstack_mode"):
        PlanManager().load(path)


def test_load_redesign_history_malformed_entry_raises(tmp_path: Path) -> None:
    """redesign_history 의 entry 가 dict 가 아니거나 'decision' 누락 시 PlanSchemaError.

    audit trail 무결성이 본 스킬의 존재 이유 — silently 드롭하면 의미 없음.
    """
    path = tmp_path / "harness-plan.md"
    path.write_text(
        "---\n"
        "harness_version: 2\n"
        "schema_version: 1\n"
        "project_name: BadRedesign\n"
        "scale: small\n"
        "profiles: []\n"
        "skeleton_sections:\n"
        "  required: []\n"
        "  optional: []\n"
        "  included: []\n"
        "pipeline:\n"
        "  steps: []\n"
        "  current_step: init\n"
        "  completed_steps: []\n"
        "  skipped_steps: []\n"
        "  gstack_mode: manual\n"
        "redesign_history:\n"
        "  - status: applied\n"  # missing 'decision' field
        "    rationale: x\n"
        "---\nbody\n",
        encoding="utf-8",
    )
    with pytest.raises(PlanSchemaError, match="decision"):
        PlanManager().load(path)


def test_save_oserror_rolls_back_timestamps(tmp_path: Path) -> None:
    """write 실패 시 plan.updated_at / last_activity 가 pre-save 값으로 롤백.

    실패한 disk write 가 in-memory plan 의 timestamp 만 silently 갱신하면
    다음 save 시 디스크 - 메모리 불일치가 영구 잠복.
    """
    pm = PlanManager()
    plan = _sample_plan()
    plan.updated_at = "2026-05-09T00:00:00+00:00"
    plan.last_activity = "2026-05-09T00:00:00+00:00"
    bad_path = tmp_path / "missing_dir" / "subdir" / "plan.md"

    # bad_path 의 부모 mkdir 은 OK 지만, 파일 경로 자체가 디렉토리로 막혀있는
    # 케이스를 모사하기 위해 부모를 디렉토리로 미리 만들고 그 자리에 file 쓰려 시도.
    bad_path.parent.mkdir(parents=True)
    bad_path.mkdir()  # path 자체가 디렉토리 — write_text 실패 유도
    with pytest.raises(OSError):
        pm.save(plan, bad_path)
    # 롤백 검증
    assert plan.updated_at == "2026-05-09T00:00:00+00:00"
    assert plan.last_activity == "2026-05-09T00:00:00+00:00"


def test_proposed_accumulation_survives_save_load(tmp_path: Path) -> None:
    """prepare 여러 번 호출로 proposed 가 누적된 후에도 정상 직렬화/역직렬화.

    SKILL.md 가드레일: '검토 중인 변경 여러 개일 수 있음 — 누적 의도적'.
    """
    pm = PlanManager()
    plan = _sample_plan()
    for i in range(3):
        pm.record_redesign(
            plan,
            decision=f"proposal-{i}",
            rationale=f"r-{i}",
            status="proposed",
        )
    path = tmp_path / "harness-plan.md"
    pm.save(plan, path)
    loaded = pm.load(path)
    assert len(loaded.redesign_history) == 3
    assert [e.decision for e in loaded.redesign_history] == [
        "proposal-0",
        "proposal-1",
        "proposal-2",
    ]
    assert all(e.status == "proposed" for e in loaded.redesign_history)


def test_redesign_history_backward_compat_missing_field(tmp_path: Path) -> None:
    """redesign_history 키 없는 기존 plan 도 load 가능 — 빈 list 로 복원."""
    path = tmp_path / "harness-plan.md"
    path.write_text(
        "---\n"
        "harness_version: 2\n"
        "schema_version: 1\n"
        "project_name: Legacy\n"
        "scale: small\n"
        "profiles: []\n"
        "skeleton_sections:\n"
        "  required: []\n"
        "  optional: []\n"
        "  included: []\n"
        "pipeline:\n"
        "  steps: []\n"
        "  current_step: init\n"
        "  completed_steps: []\n"
        "  skipped_steps: []\n"
        "  gstack_mode: manual\n"
        "---\n"
        "body\n",
        encoding="utf-8",
    )
    pm = PlanManager()
    loaded = pm.load(path)
    assert loaded.redesign_history == []


# ── regress ──────────────────────────────────────────────────────────


def test_regress_one_step_back() -> None:
    """built → building 한 단계 역행."""
    pm = PlanManager()
    plan = _sample_plan()
    for state in ("designed", "planned", "building", "built"):
        pm.transition(plan, state)

    pm.regress(plan, "building")
    assert plan.pipeline.current_step == "building"


def test_regress_multi_step_back() -> None:
    """verified → building 여러 단계 역행 허용."""
    pm = PlanManager()
    plan = _sample_plan()
    for state in ("designed", "planned", "building", "built", "verified"):
        pm.transition(plan, state)

    pm.regress(plan, "building")
    assert plan.pipeline.current_step == "building"


def test_regress_preserves_completed_steps() -> None:
    """역행 후 completed_steps 는 변경되지 않는다."""
    pm = PlanManager()
    plan = _sample_plan()
    pm.transition(plan, "designed", completed_step="ha-design")
    pm.transition(plan, "planned", completed_step="ha-plan")
    pm.transition(plan, "building", completed_step="ha-build:T-001")
    pm.transition(plan, "built", completed_step="ha-build:all-done")

    before = plan.pipeline.completed_steps
    pm.regress(plan, "building")

    assert plan.pipeline.completed_steps == before


def test_regress_preserves_gstack_mode() -> None:
    """역행 후 gstack_mode 는 유지된다."""
    pm = PlanManager()
    plan = pm.create(
        project_name="X",
        project_type="cli",
        scale="small",
        user_description_original="test",
        profiles=[],
        skeleton_sections=SkeletonSpec((), (), ()),
        pipeline_steps=[],
        gstack_mode="auto",
    )
    pm.transition(plan, "designed")
    pm.transition(plan, "planned")
    pm.transition(plan, "building")
    pm.transition(plan, "built")

    pm.regress(plan, "building")
    assert plan.pipeline.gstack_mode == "auto"


def test_regress_unknown_state_raises() -> None:
    """알 수 없는 상태로 역행 시 InvalidStateTransitionError."""
    pm = PlanManager()
    plan = _sample_plan()
    pm.transition(plan, "designed")

    with pytest.raises(InvalidStateTransitionError, match="unknown state"):
        pm.regress(plan, "bogus")


def test_regress_forward_raises() -> None:
    """현재보다 앞선(또는 같은) 상태로 regress 하면 에러."""
    pm = PlanManager()
    plan = _sample_plan()
    pm.transition(plan, "designed")
    pm.transition(plan, "planned")

    with pytest.raises(InvalidStateTransitionError, match="not backward"):
        pm.regress(plan, "built")


def test_regress_same_state_raises() -> None:
    """같은 상태로 regress 하면 에러 (역행이 아님)."""
    pm = PlanManager()
    plan = _sample_plan()
    pm.transition(plan, "designed")

    with pytest.raises(InvalidStateTransitionError, match="not backward"):
        pm.regress(plan, "designed")


def test_regress_updates_last_activity() -> None:
    """regress 호출 후 last_activity 가 갱신된다."""
    pm = PlanManager()
    plan = _sample_plan()
    pm.transition(plan, "designed")
    pm.transition(plan, "planned")
    pm.transition(plan, "building")
    pm.transition(plan, "built")

    before = plan.last_activity
    pm.regress(plan, "building")
    assert plan.last_activity >= before
