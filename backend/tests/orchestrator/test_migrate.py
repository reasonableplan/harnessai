"""migrate-plan 기능 단위 테스트.

cmd_migrate_plan 의 핵심 로직 (plan 로드 → compute_active_sections → diff → 저장)
을 backend 모듈을 직접 사용해 검증.

모든 픽스처는 tmp_path 기반 — 사용자 환경 비의존.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent

import pytest
import yaml

from src.orchestrator.plan_manager import (
    PlanManager,
    ProfileRef,
    ScaleAxes,
    SkeletonSpec,
)
from src.orchestrator.profile_loader import (
    ProfileLoader,
    find_consistency_violations,
)
from src.orchestrator.skeleton_stale import (
    mark_skeleton_stale as do_mark_skeleton_stale,
    preview_skeleton_stale as do_preview_skeleton_stale,
)


# ── 픽스처 헬퍼 ──────────────────────────────────────────────────────────


def _write_base(profiles_dir: Path) -> None:
    profiles_dir.mkdir(parents=True, exist_ok=True)
    (profiles_dir / "_base.md").write_text(
        dedent(
            """\
            ---
            id: _base
            name: Base
            whitelist:
              runtime: []
              dev: []
              prefix_allowed: []
            ---
            """
        ),
        encoding="utf-8",
    )


def _write_profile(
    profiles_dir: Path,
    profile_id: str,
    *,
    required_sections: list[str] | None = None,
    optional_sections: list[str] | None = None,
    provides_capabilities: list[str] | None = None,
) -> None:
    profiles_dir.mkdir(parents=True, exist_ok=True)
    required = required_sections or []
    optional = optional_sections or []
    fm: dict = {
        "id": profile_id,
        "name": profile_id.title(),
        "status": "confirmed",
        "version": 1,
        "skeleton_sections": {
            "required": required,
            "optional": optional,
            "order": required + optional,
        },
        "toolchain": {
            "install": None,
            "test": None,
            "lint": None,
            "type": None,
            "format": None,
        },
        "whitelist": {"runtime": [], "dev": [], "prefix_allowed": []},
        "components": [],
        "file_structure": "x",
        "gstack_mode": "manual",
        "provides_capabilities": provides_capabilities or [],
    }
    text = "---\n" + yaml.safe_dump(fm, allow_unicode=True) + "---\n"
    (profiles_dir / f"{profile_id}.md").write_text(text, encoding="utf-8")


def _write_registry(profiles_dir: Path) -> None:
    (profiles_dir / "_registry.yaml").write_text(
        yaml.safe_dump({"version": 1, "rules": []}),
        encoding="utf-8",
    )


def _write_fragment(
    fragments_dir: Path,
    frag_id: str,
    *,
    required_when: str,
) -> None:
    fragments_dir.mkdir(parents=True, exist_ok=True)
    fm: dict = {
        "id": frag_id,
        "name": frag_id,
        "required_when": required_when,
        "description": f"Fragment {frag_id}",
    }
    body = f"\n## {{{{section_number}}}}. {frag_id}\n\nContent.\n"
    text = "---\n" + yaml.safe_dump(fm, allow_unicode=True) + "---\n" + body
    (fragments_dir / f"{frag_id}.md").write_text(text, encoding="utf-8")


def _write_plan(
    docs_dir: Path,
    *,
    profile_ids: list[str],
    included: list[str],
    activation_trace: dict[str, str] | None = None,
    scale_axes: ScaleAxes | None = None,
    project_name: str = "테스트 프로젝트",
) -> Path:
    """harness-plan.md 를 tmp_path 에 작성하고 경로 반환."""
    docs_dir.mkdir(parents=True, exist_ok=True)
    pm = PlanManager()
    plan = pm.create(
        project_name=project_name,
        project_type="테스트",
        scale="small",
        user_description_original="테스트용",
        profiles=[ProfileRef(id=pid, path=".") for pid in profile_ids],
        skeleton_sections=SkeletonSpec(
            required=tuple(included),
            optional=(),
            included=tuple(included),
        ),
        pipeline_steps=["ha-init", "ha-design", "ha-plan"],
        scale_axes=scale_axes or ScaleAxes(),
        activation_trace=activation_trace,
    )
    plan_path = docs_dir / "harness-plan.md"
    pm.save(plan, plan_path)
    return plan_path


def _make_harness_dir(
    tmp_path: Path,
    *,
    profile_id: str,
    required_sections: list[str] | None = None,
    optional_sections: list[str] | None = None,
    fragments: dict[str, str] | None = None,  # frag_id → required_when
) -> Path:
    """최소 harness 디렉토리 구조 생성. 반환: harness_dir."""
    harness_dir = tmp_path / "harness"
    profiles_dir = harness_dir / "profiles"
    _write_base(profiles_dir)
    _write_registry(profiles_dir)
    _write_profile(
        profiles_dir,
        profile_id,
        required_sections=required_sections,
        optional_sections=optional_sections,
    )
    frags_dir = harness_dir / "templates" / "skeleton"
    for fid, rw in (fragments or {}).items():
        _write_fragment(frags_dir, fid, required_when=rw)
    return harness_dir


# ── migrate 로직 직접 구현 (cmd_migrate_plan 과 동일한 흐름) ─────────────
# harness CLI 의 cmd_migrate_plan() 과 동일한 로직을 여기서 직접 실행.
# CLI 스크립트를 import 하는 대신 동일한 backend 모듈을 직접 호출.


def run_migrate_logic(
    plan_path: Path,
    harness_dir: Path,
    fragments_dir: Path,
    *,
    apply: bool = False,
    no_backup: bool = False,
    mark_skeleton_stale: bool = False,
) -> dict:
    """cmd_migrate_plan 핵심 로직 직접 실행.

    Returns:
        JSON-serializable dict (harness CLI 의 stdout JSON 과 동일한 스키마).
    """
    pm = PlanManager()
    plan = pm.load(plan_path)

    loader = ProfileLoader(
        harness_dir=harness_dir,
        project_dir=plan_path.parent.parent,  # docs/의 부모 = 프로젝트 루트
    )

    profiles = []
    for prof_ref in plan.profiles:
        try:
            profiles.append(loader.load(prof_ref.id))
        except Exception:
            pass

    new_active, new_trace = loader.compute_active_sections(
        plan.scale_axes, profiles, fragments_dir
    )

    current_included = set(plan.skeleton_sections.included)
    new_active_set = set(new_active)
    removed_sections = sorted(current_included - new_active_set)
    added_sections = sorted(new_active_set - current_included)
    trace_was_missing = not bool(plan.activation_trace)

    violations = find_consistency_violations(new_trace, profiles)
    violations_serialized = [
        {
            "section_id": v.section_id,
            "trigger_expression": v.trigger_expression,
            "missing_atom": v.missing_atom,
            "expected_providers": list(v.expected_providers),
        }
        for v in violations
    ]

    result: dict = {
        "plan_path": str(plan_path),
        "current_step": plan.pipeline.current_step,
        "diff": {
            "removed_sections": removed_sections,
            "added_sections": added_sections,
            "trace_was_missing": trace_was_missing,
        },
        "new_active_sections": new_active,
        "new_activation_trace": new_trace,
        "consistency_violations": violations_serialized,
        "applied": False,
        "backup_path": None,
        "skeleton_marked_sections": [],
        "skeleton_backup_path": None,
    }

    if not apply:
        # dry-run: skeleton_will_mark preview
        if mark_skeleton_stale and removed_sections:
            skeleton_path = plan_path.parent / "skeleton.md"
            if skeleton_path.exists():
                result["skeleton_will_mark"] = do_preview_skeleton_stale(
                    skeleton_path,
                    removed_sections,
                    list(plan.skeleton_sections.included),
                    fragments_dir,
                )
            else:
                result["skeleton_will_mark"] = []
        return result

    # --apply: 백업 → plan 갱신 → 저장
    backup_path: str | None = None
    if not no_backup:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup_name = f".backup-pre-migrate-{ts}.md"
        backup_file = plan_path.parent / backup_name
        backup_file.write_text(plan_path.read_text(encoding="utf-8"), encoding="utf-8")
        backup_path = str(backup_file)

    included_order_before = list(plan.skeleton_sections.included)
    plan.skeleton_sections = SkeletonSpec(
        required=plan.skeleton_sections.required,
        optional=plan.skeleton_sections.optional,
        included=tuple(new_active),
    )
    plan.activation_trace = new_trace
    pm.save(plan, plan_path)

    result["applied"] = True
    result["backup_path"] = backup_path

    if mark_skeleton_stale and removed_sections:
        skeleton_path = plan_path.parent / "skeleton.md"
        if skeleton_path.exists():
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            marked_ids, skel_backup = do_mark_skeleton_stale(
                skeleton_path,
                removed_sections,
                included_order_before,
                fragments_dir,
                no_backup=no_backup,
                quiet=True,
                today=today,
            )
            result["skeleton_marked_sections"] = marked_ids
            result["skeleton_backup_path"] = skel_backup

    return result


# ── 테스트 1: dry-run 은 파일을 변경하지 않는다 ─────────────────────────────


def test_migrate_dry_run_no_file_change(tmp_path: Path) -> None:
    """--apply 없이 실행하면 plan 파일이 변경되지 않아야 한다."""
    harness_dir = _make_harness_dir(
        tmp_path,
        profile_id="mobile",
        required_sections=["overview", "stack"],
        optional_sections=["interface.http"],
        fragments={
            "overview": "always",
            "stack": "always",
            # interface.http 는 has.http_server 기반 — mobile profile 은 미제공
            "interface.http": "has.http_server",
        },
    )
    docs_dir = tmp_path / "project" / "docs"
    # legacy: interface.http 가 잘못 포함된 상태
    plan_path = _write_plan(
        docs_dir,
        profile_ids=["mobile"],
        included=["overview", "stack", "interface.http"],
        activation_trace=None,  # legacy — trace 없음
    )

    content_before = plan_path.read_text(encoding="utf-8")

    result = run_migrate_logic(
        plan_path,
        harness_dir,
        harness_dir / "templates" / "skeleton",
        apply=False,
    )

    assert result["applied"] is False
    assert result["backup_path"] is None
    # 파일이 변경되지 않아야 함
    assert plan_path.read_text(encoding="utf-8") == content_before


def test_migrate_dry_run_detects_removed_sections(tmp_path: Path) -> None:
    """dry-run 시 diff.removed_sections 에 잘못 포함된 섹션이 나타나야 한다."""
    harness_dir = _make_harness_dir(
        tmp_path,
        profile_id="mobile",
        required_sections=["overview", "stack"],
        optional_sections=["interface.http"],
        fragments={
            "overview": "always",
            "stack": "always",
            "interface.http": "has.http_server",
        },
    )
    docs_dir = tmp_path / "project" / "docs"
    plan_path = _write_plan(
        docs_dir,
        profile_ids=["mobile"],
        included=["overview", "stack", "interface.http"],
    )

    result = run_migrate_logic(
        plan_path,
        harness_dir,
        harness_dir / "templates" / "skeleton",
    )

    assert "interface.http" in result["diff"]["removed_sections"]
    assert result["diff"]["trace_was_missing"] is True


# ── 테스트 2: --apply 는 plan 을 갱신한다 ─────────────────────────────────


def test_migrate_apply_updates_plan(tmp_path: Path) -> None:
    """--apply 후 plan.included 가 새 활성 섹션으로 갱신되고 activation_trace 가 채워진다."""
    harness_dir = _make_harness_dir(
        tmp_path,
        profile_id="mobile",
        required_sections=["overview", "stack"],
        optional_sections=["interface.http"],
        fragments={
            "overview": "always",
            "stack": "always",
            "interface.http": "has.http_server",
        },
    )
    docs_dir = tmp_path / "project" / "docs"
    plan_path = _write_plan(
        docs_dir,
        profile_ids=["mobile"],
        included=["overview", "stack", "interface.http"],
    )

    result = run_migrate_logic(
        plan_path,
        harness_dir,
        harness_dir / "templates" / "skeleton",
        apply=True,
    )

    assert result["applied"] is True

    # plan 다시 로드해서 확인
    pm = PlanManager()
    updated = pm.load(plan_path)
    assert "interface.http" not in updated.skeleton_sections.included
    assert "overview" in updated.skeleton_sections.included
    assert "stack" in updated.skeleton_sections.included
    # activation_trace 가 채워져야 함
    assert "overview" in updated.activation_trace
    assert "stack" in updated.activation_trace
    assert "interface.http" not in updated.activation_trace


# ── 테스트 3: --apply 는 백업을 생성한다 ─────────────────────────────────


def test_migrate_apply_creates_backup(tmp_path: Path) -> None:
    """--apply 후 .backup-pre-migrate-*.md 파일이 생성되어야 한다."""
    harness_dir = _make_harness_dir(
        tmp_path,
        profile_id="mobile",
        required_sections=["overview"],
        fragments={"overview": "always"},
    )
    docs_dir = tmp_path / "project" / "docs"
    plan_path = _write_plan(
        docs_dir,
        profile_ids=["mobile"],
        included=["overview"],
    )
    content_before = plan_path.read_text(encoding="utf-8")

    result = run_migrate_logic(
        plan_path,
        harness_dir,
        harness_dir / "templates" / "skeleton",
        apply=True,
    )

    assert result["applied"] is True
    backup_path_str = result["backup_path"]
    assert backup_path_str is not None
    backup_file = Path(backup_path_str)
    assert backup_file.exists(), f"백업 파일 없음: {backup_path_str}"
    # 백업 내용 = 마이그레이션 전 plan 내용
    assert backup_file.read_text(encoding="utf-8") == content_before
    # 백업 파일명 형식
    assert backup_file.name.startswith(".backup-pre-migrate-")
    assert backup_file.name.endswith(".md")


# ── 테스트 4: 이미 fix 된 plan 은 변화 없음 ────────────────────────────────


def test_migrate_no_changes_required(tmp_path: Path) -> None:
    """새 로직으로 이미 생성된 plan 은 removed/added 가 빈 리스트여야 한다."""
    harness_dir = _make_harness_dir(
        tmp_path,
        profile_id="mobile",
        required_sections=["overview", "stack"],
        fragments={
            "overview": "always",
            "stack": "always",
        },
    )
    docs_dir = tmp_path / "project" / "docs"
    # 이미 올바른 상태 (interface.http 없음)
    plan_path = _write_plan(
        docs_dir,
        profile_ids=["mobile"],
        included=["overview", "stack"],
        activation_trace={"overview": "always", "stack": "always"},
    )

    result = run_migrate_logic(
        plan_path,
        harness_dir,
        harness_dir / "templates" / "skeleton",
    )

    assert result["diff"]["removed_sections"] == []
    assert result["diff"]["added_sections"] == []
    assert result["diff"]["trace_was_missing"] is False


# ── 테스트 5: legacy plan 에 activation_trace 가 채워진다 ─────────────────


def test_migrate_legacy_plan_fills_trace(tmp_path: Path) -> None:
    """activation_trace 없는 legacy plan 에 apply 후 trace 가 채워진다."""
    harness_dir = _make_harness_dir(
        tmp_path,
        profile_id="mobile",
        required_sections=["overview"],
        fragments={"overview": "always"},
    )
    docs_dir = tmp_path / "project" / "docs"
    # activation_trace 없이 생성
    plan_path = _write_plan(
        docs_dir,
        profile_ids=["mobile"],
        included=["overview"],
        activation_trace=None,
    )

    # 파일에서 activation_trace 가 없는지 확인 (legacy 상태)
    raw_text = plan_path.read_text(encoding="utf-8")
    assert "activation_trace" not in raw_text

    result = run_migrate_logic(
        plan_path,
        harness_dir,
        harness_dir / "templates" / "skeleton",
        apply=True,
    )

    assert result["applied"] is True
    pm = PlanManager()
    updated = pm.load(plan_path)
    assert bool(updated.activation_trace), "activation_trace 가 비어있음"
    assert "overview" in updated.activation_trace


# ── 테스트 6: consistency_violations 보고 ────────────────────────────────


def test_migrate_reports_consistency_violations(tmp_path: Path) -> None:
    """interface.http required 선언 + fastapi/nestjs 없으면 violation 발생."""
    harness_dir = _make_harness_dir(
        tmp_path,
        profile_id="mobile",
        required_sections=["overview"],
        fragments={
            "overview": "always",
            "interface.http": "has.http_server",
        },
    )
    # interface.http 를 provides_capabilities 로 선언한 별도 profile 작성
    # → compute_has_keys 에서 http_server=True → interface.http fragment 활성
    # → find_consistency_violations: "mobile-with-http" 는 fastapi/nestjs/nextjs 아님 → violation
    profiles_dir = harness_dir / "profiles"
    _write_profile(
        profiles_dir,
        "mobile-with-http",
        required_sections=["overview", "interface.http"],
        provides_capabilities=["http_server"],
    )

    docs_dir = tmp_path / "project" / "docs"
    plan_path = _write_plan(
        docs_dir,
        profile_ids=["mobile-with-http"],
        included=["overview"],
    )

    result = run_migrate_logic(
        plan_path,
        harness_dir,
        harness_dir / "templates" / "skeleton",
    )

    # mobile-with-http 는 fastapi/nestjs 아님 → http_server violation
    assert len(result["consistency_violations"]) > 0
    violation_atoms = [v["missing_atom"] for v in result["consistency_violations"]]
    assert "http_server" in violation_atoms


# ── 테스트 7: dry-run 은 백업을 생성하지 않는다 ──────────────────────────


def test_migrate_no_apply_no_backup(tmp_path: Path) -> None:
    """dry-run 시 backup 파일이 생성되지 않아야 한다."""
    harness_dir = _make_harness_dir(
        tmp_path,
        profile_id="mobile",
        required_sections=["overview"],
        fragments={"overview": "always"},
    )
    docs_dir = tmp_path / "project" / "docs"
    plan_path = _write_plan(
        docs_dir,
        profile_ids=["mobile"],
        included=["overview"],
    )

    result = run_migrate_logic(
        plan_path,
        harness_dir,
        harness_dir / "templates" / "skeleton",
        apply=False,
    )

    assert result["backup_path"] is None
    # docs 디렉토리에 backup 파일 없어야 함
    backup_files = list(docs_dir.glob(".backup-pre-migrate-*.md"))
    assert backup_files == [], f"예상치 못한 백업 파일: {backup_files}"


# ── skeleton stale 마킹 헬퍼 ─────────────────────────────────────────────


def _write_fragment_with_title(
    fragments_dir: Path,
    frag_id: str,
    *,
    required_when: str,
    title: str,
) -> None:
    """지정 title 로 fragment *.md 를 생성."""
    fragments_dir.mkdir(parents=True, exist_ok=True)
    fm: dict = {
        "id": frag_id,
        "name": frag_id,
        "required_when": required_when,
        "description": f"Fragment {frag_id}",
    }
    body = f"\n## {{{{section_number}}}}. {title}\n\nContent.\n"
    text = "---\n" + yaml.safe_dump(fm, allow_unicode=True) + "---\n" + body
    (fragments_dir / f"{frag_id}.md").write_text(text, encoding="utf-8")


def _write_skeleton(docs_dir: Path, sections: list[tuple[int, str]]) -> Path:
    """최소 skeleton.md 생성. sections = [(number, title), ...]."""
    docs_dir.mkdir(parents=True, exist_ok=True)
    lines = ["# Test Skeleton\n"]
    for num, title in sections:
        lines.append(f"\n## {num}. {title}\n\nSection body.\n")
    skeleton_path = docs_dir / "skeleton.md"
    skeleton_path.write_text("".join(lines), encoding="utf-8")
    return skeleton_path


def _make_harness_dir_with_stale(
    tmp_path: Path,
    *,
    profile_id: str,
    required_sections: list[str],
    fragment_titles: dict[str, str],  # frag_id → heading title
    fragment_required_when: dict[str, str] | None = None,  # frag_id → required_when
) -> Path:
    """skeleton stale 테스트용 harness 디렉토리. fragment 는 title 포함.

    fragment_required_when 미지정 시 required_sections 에 있는 것은 "always",
    나머지는 "has.http_server" (compute_active_sections 에서 제외되도록).
    """
    harness_dir = tmp_path / "harness"
    profiles_dir = harness_dir / "profiles"
    _write_base(profiles_dir)
    _write_registry(profiles_dir)
    _write_profile(
        profiles_dir,
        profile_id,
        required_sections=required_sections,
    )
    frags_dir = harness_dir / "templates" / "skeleton"
    rw_map = fragment_required_when or {}
    for fid, title in fragment_titles.items():
        if fid in rw_map:
            rw = rw_map[fid]
        elif fid in required_sections:
            rw = "always"
        else:
            # not in profile required → should be excluded by compute_active_sections
            rw = "has.http_server"
        _write_fragment_with_title(frags_dir, fid, required_when=rw, title=title)
    return harness_dir


# ── 테스트 9: --apply --mark-skeleton-stale → STALE 마커 삽입 ────────────


def test_migrate_apply_with_mark_skeleton_stale_inserts_markers(
    tmp_path: Path,
) -> None:
    """--apply --mark-skeleton-stale 시 removed_sections 헤딩 아래 STALE 마커 삽입."""
    # interface.http 는 plan 에 포함(old) 되었으나 profile 에는 없음 → removed
    harness_dir = _make_harness_dir_with_stale(
        tmp_path,
        profile_id="web",
        required_sections=["overview"],
        fragment_titles={
            "overview": "프로젝트 개요",
            "interface.http": "HTTP API",
        },
    )
    docs_dir = tmp_path / "project" / "docs"
    # included 에 interface.http 포함 → compute 후 제거됨
    plan_path = _write_plan(
        docs_dir,
        profile_ids=["web"],
        included=["overview", "interface.http"],
    )
    # skeleton.md: §1 overview, §2 HTTP API (interface.http)
    skeleton_path = _write_skeleton(
        docs_dir,
        [(1, "프로젝트 개요"), (2, "HTTP API")],
    )
    original_content = skeleton_path.read_text(encoding="utf-8")

    result = run_migrate_logic(
        plan_path,
        harness_dir,
        harness_dir / "templates" / "skeleton",
        apply=True,
        no_backup=True,
        mark_skeleton_stale=True,
    )

    assert result["applied"] is True
    assert "interface.http" in result["skeleton_marked_sections"]

    new_content = skeleton_path.read_text(encoding="utf-8")
    assert new_content != original_content, "skeleton.md 가 수정되어야 함"
    assert "<!-- STALE:" in new_content, "STALE 마커가 삽입되어야 함"

    # §2 HTTP API 헤딩 바로 다음 줄에 STALE 마커가 있어야 함
    lines = new_content.splitlines()
    http_heading_idx = next(
        i for i, ln in enumerate(lines) if re.match(r"^## 2\. HTTP API", ln)
    )
    assert lines[http_heading_idx + 1].startswith("<!-- STALE:"), (
        f"STALE 마커가 헤딩 바로 다음 줄에 있어야 함. 실제: {lines[http_heading_idx + 1]!r}"
    )


# ── 테스트 10: dry-run --mark-skeleton-stale → skeleton_will_mark preview ─


def test_migrate_dry_run_with_mark_skeleton_stale_preview_only(
    tmp_path: Path,
) -> None:
    """dry-run 시 skeleton.md 미수정, skeleton_will_mark 필드에 preview ID 반환."""
    harness_dir = _make_harness_dir_with_stale(
        tmp_path,
        profile_id="web",
        required_sections=["overview"],
        fragment_titles={
            "overview": "프로젝트 개요",
            "interface.http": "HTTP API",
        },
    )
    docs_dir = tmp_path / "project" / "docs"
    plan_path = _write_plan(
        docs_dir,
        profile_ids=["web"],
        included=["overview", "interface.http"],
    )
    skeleton_path = _write_skeleton(
        docs_dir,
        [(1, "프로젝트 개요"), (2, "HTTP API")],
    )
    original_content = skeleton_path.read_text(encoding="utf-8")

    result = run_migrate_logic(
        plan_path,
        harness_dir,
        harness_dir / "templates" / "skeleton",
        apply=False,
        mark_skeleton_stale=True,
    )

    assert result["applied"] is False
    assert "skeleton_will_mark" in result
    assert "interface.http" in result["skeleton_will_mark"]
    # skeleton.md 는 변경되지 않아야 함
    assert skeleton_path.read_text(encoding="utf-8") == original_content


# ── 테스트 11: 멱등성 — STALE 마커 중복 삽입 안 됨 ─────────────────────────


def test_migrate_mark_skeleton_stale_idempotent(tmp_path: Path) -> None:
    """같은 명령 2번 실행해도 STALE 마커가 중복으로 추가되지 않는다."""
    harness_dir = _make_harness_dir_with_stale(
        tmp_path,
        profile_id="web",
        required_sections=["overview"],
        fragment_titles={
            "overview": "프로젝트 개요",
            "interface.http": "HTTP API",
        },
    )
    docs_dir = tmp_path / "project" / "docs"
    plan_path = _write_plan(
        docs_dir,
        profile_ids=["web"],
        included=["overview", "interface.http"],
    )
    _write_skeleton(docs_dir, [(1, "프로젝트 개요"), (2, "HTTP API")])
    frags_dir = harness_dir / "templates" / "skeleton"

    # 1회
    result1 = run_migrate_logic(
        plan_path,
        harness_dir,
        frags_dir,
        apply=True,
        no_backup=True,
        mark_skeleton_stale=True,
    )
    assert "interface.http" in result1["skeleton_marked_sections"]

    content_after_first = (docs_dir / "skeleton.md").read_text(encoding="utf-8")
    stale_count_after_first = content_after_first.count("<!-- STALE:")

    # plan 이 이미 apply 됐으므로 다시 적재해서 2회 실행 시뮬레이션
    # (plan 의 included 가 이미 갱신됐으므로 removed_sections=[] — 멱등 확인)
    result2 = run_migrate_logic(
        plan_path,
        harness_dir,
        frags_dir,
        apply=True,
        no_backup=True,
        mark_skeleton_stale=True,
    )
    content_after_second = (docs_dir / "skeleton.md").read_text(encoding="utf-8")
    stale_count_after_second = content_after_second.count("<!-- STALE:")

    assert stale_count_after_second == stale_count_after_first, (
        f"STALE 마커 개수가 늘어남: {stale_count_after_first} → {stale_count_after_second}"
    )


# ── 테스트 12: --apply --mark-skeleton-stale → skeleton 백업 생성 ─────────


def test_migrate_mark_skeleton_stale_creates_backup(tmp_path: Path) -> None:
    """--apply --mark-skeleton-stale 시 skeleton 백업 파일이 생성된다."""
    harness_dir = _make_harness_dir_with_stale(
        tmp_path,
        profile_id="web",
        required_sections=["overview"],
        fragment_titles={
            "overview": "프로젝트 개요",
            "interface.http": "HTTP API",
        },
    )
    docs_dir = tmp_path / "project" / "docs"
    plan_path = _write_plan(
        docs_dir,
        profile_ids=["web"],
        included=["overview", "interface.http"],
    )
    _write_skeleton(docs_dir, [(1, "프로젝트 개요"), (2, "HTTP API")])

    result = run_migrate_logic(
        plan_path,
        harness_dir,
        harness_dir / "templates" / "skeleton",
        apply=True,
        no_backup=False,  # 백업 활성
        mark_skeleton_stale=True,
    )

    assert result["skeleton_backup_path"] is not None
    backup_path = Path(result["skeleton_backup_path"])
    assert backup_path.exists(), f"skeleton 백업 파일이 존재해야 함: {backup_path}"
    assert backup_path.name.startswith(".backup-pre-migrate-skeleton-")


# ── 테스트 13: removed_sections=[] → skeleton 변경 없음 ─────────────────


def test_migrate_no_removed_sections_no_marking(tmp_path: Path) -> None:
    """removed_sections 가 없으면 skeleton.md 변화 없음."""
    harness_dir = _make_harness_dir_with_stale(
        tmp_path,
        profile_id="web",
        required_sections=["overview"],
        fragment_titles={"overview": "프로젝트 개요"},
    )
    docs_dir = tmp_path / "project" / "docs"
    plan_path = _write_plan(
        docs_dir,
        profile_ids=["web"],
        included=["overview"],  # plan 과 profile 이 일치 → removed_sections=[]
    )
    skeleton_path = _write_skeleton(docs_dir, [(1, "프로젝트 개요")])
    original_content = skeleton_path.read_text(encoding="utf-8")

    result = run_migrate_logic(
        plan_path,
        harness_dir,
        harness_dir / "templates" / "skeleton",
        apply=True,
        no_backup=True,
        mark_skeleton_stale=True,
    )

    assert result["skeleton_marked_sections"] == []
    assert result["skeleton_backup_path"] is None
    assert skeleton_path.read_text(encoding="utf-8") == original_content


# ── 테스트 14: skeleton.md 없으면 경고 + skip ────────────────────────────


def test_migrate_skeleton_missing_skip_with_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """skeleton.md 없을 때 STALE 마킹 skip, plan apply 는 정상 완료."""
    harness_dir = _make_harness_dir_with_stale(
        tmp_path,
        profile_id="web",
        required_sections=["overview"],
        fragment_titles={
            "overview": "프로젝트 개요",
            "interface.http": "HTTP API",
        },
    )
    docs_dir = tmp_path / "project" / "docs"
    plan_path = _write_plan(
        docs_dir,
        profile_ids=["web"],
        included=["overview", "interface.http"],
    )
    # skeleton.md 생성 안 함

    result = run_migrate_logic(
        plan_path,
        harness_dir,
        harness_dir / "templates" / "skeleton",
        apply=True,
        no_backup=True,
        mark_skeleton_stale=True,
    )

    # plan apply 는 정상 완료
    assert result["applied"] is True
    # skeleton 마킹은 skip
    assert result["skeleton_marked_sections"] == []
    assert result["skeleton_backup_path"] is None
