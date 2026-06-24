"""ha-design/run.py cmd_prepare 의 activation_trace 출력 회귀 테스트.

ha-design/run.py 는 _ha_shared/utils.py 를 통해 backend 모듈을 import 하므로,
여기서는 PlanManager / HarnessPlan 을 직접 import 해서 픽스처를 구성하고
subprocess 를 통해 run.py 를 실행 — stdout/stderr 를 분리 수집.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from src.orchestrator.plan_manager import (
    HarnessPlan,
    PlanManager,
    ProfileRef,
    SkeletonSpec,
)

# ha-design/run.py 절대 경로
_RUN_PY = Path.home() / ".claude" / "skills" / "ha-design" / "run.py"

# HARNESS_AI_HOME: agent/ 디렉토리 (backend/ 의 부모)
# __file__ = backend/tests/orchestrator/test_ha_design_run.py
# parents[0]=orchestrator, [1]=tests, [2]=backend, [3]=agent
_HARNESS_HOME = Path(__file__).resolve().parents[3]  # agent/


def _make_env() -> dict[str, str]:
    """subprocess 용 환경 변수. HARNESS_AI_HOME 을 이 레포로 명시 설정."""
    env = os.environ.copy()
    env["HARNESS_AI_HOME"] = str(_HARNESS_HOME)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _write_plan(tmp_path: Path, plan: HarnessPlan) -> Path:
    """tmp_path/docs/harness-plan.md 에 plan 저장 후 plan_path 반환."""
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    plan_path = docs / "harness-plan.md"
    PlanManager().save(plan, plan_path)
    return plan_path


def _make_plan(
    *,
    included: tuple[str, ...] = ("overview", "stack", "interface.http"),
    activation_trace: dict[str, str] | None = None,
) -> HarnessPlan:
    """테스트용 HarnessPlan 생성 헬퍼."""
    pm = PlanManager()
    plan = pm.create(
        project_name="TestProject",
        project_type="web",
        scale="small",
        user_description_original="테스트 프로젝트",
        profiles=[ProfileRef(id="fastapi", path="backend/")],
        skeleton_sections=SkeletonSpec(
            required=("overview", "stack"),
            optional=("interface.http",),
            included=included,
        ),
        pipeline_steps=["ha-init", "ha-design", "ha-plan", "ha-build", "ha-verify"],
        activation_trace=activation_trace,
    )
    return plan


def _run_prepare(project_dir: Path) -> tuple[dict, str]:
    """cmd_prepare 실행. (parsed_json, stderr_text) 반환."""
    result = subprocess.run(
        [sys.executable, str(_RUN_PY), "prepare"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(project_dir),
        env=_make_env(),
    )
    assert result.returncode == 0, (
        f"prepare 실패 (returncode={result.returncode})\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )
    return json.loads(result.stdout), result.stderr


# ── 테스트 1: activation_trace 필드 존재 + dict 타입 ──────────────────


def test_prepare_includes_activation_trace(tmp_path: Path) -> None:
    """prepare JSON 출력에 activation_trace 필드가 존재하고 dict 여야 한다."""
    trace = {
        "interface.http": "has.http_server",
        "overview": "always",
        "stack": "always",
    }
    plan = _make_plan(
        included=("overview", "stack", "interface.http"),
        activation_trace=trace,
    )
    _write_plan(tmp_path, plan)

    output, _ = _run_prepare(tmp_path)

    assert "activation_trace" in output, "activation_trace 필드 누락"
    assert isinstance(output["activation_trace"], dict), (
        f"activation_trace 가 dict 아님: {type(output['activation_trace'])}"
    )
    assert output["activation_trace"] == trace


# ── 테스트 2: legacy plan (trace 없음) — stderr 경고 + JSON 에 {} ─────


def test_prepare_legacy_plan_warns_to_stderr(tmp_path: Path) -> None:
    """activation_trace 없는 legacy plan 이면 stderr 경고 + JSON 의 activation_trace 가 {} 여야 한다."""
    plan = _make_plan(activation_trace=None)  # empty dict
    _write_plan(tmp_path, plan)

    output, stderr = _run_prepare(tmp_path)

    # stderr 경고
    assert "trace 미포함" in stderr or "cross-check 불가능" in stderr, (
        f"legacy plan 경고 없음. stderr: {stderr!r}"
    )
    # stdout JSON 은 정상 응답 — activation_trace 는 빈 dict
    assert "activation_trace" in output
    assert output["activation_trace"] == {}


# ── 테스트 3: trace keys 가 included_sections 의 부분집합 ─────────────


def test_prepare_trace_keys_match_included_sections(tmp_path: Path) -> None:
    """trace 의 keys 가 included_sections 와 일치하거나 부분집합이어야 한다."""
    included = ("overview", "stack", "interface.http")
    trace = {
        "overview": "always",
        "stack": "always",
        "interface.http": "has.http_server",
    }
    plan = _make_plan(included=included, activation_trace=trace)
    _write_plan(tmp_path, plan)

    output, _ = _run_prepare(tmp_path)

    trace_keys = set(output["activation_trace"].keys())
    included_set = set(output["included_sections"])
    assert trace_keys.issubset(included_set), (
        f"trace keys {trace_keys} 가 included_sections {included_set} 의 부분집합 아님"
    )


# ── 테스트 4: trace value 가 required_when 표현식 문자열 ──────────────


def test_prepare_trace_value_is_required_when_expression(tmp_path: Path) -> None:
    """trace 의 각 value 가 문자열 (required_when 표현식) 이어야 한다."""
    trace = {
        "overview": "always",
        "stack": "always",
        "interface.http": "has.http_server",
        "audit_log": "data_sensitivity in [pii, payment]",
    }
    included = tuple(trace.keys())
    plan = _make_plan(included=included, activation_trace=trace)
    _write_plan(tmp_path, plan)

    output, _ = _run_prepare(tmp_path)

    for section_id, expr in output["activation_trace"].items():
        assert isinstance(expr, str) and expr, (
            f"trace['{section_id}'] 가 빈 문자열 또는 str 아님: {expr!r}"
        )


# ── 테스트 5: trace 에 parse-error 마커가 있으면 그대로 보존 ───────────


def test_prepare_trace_contains_parse_error_marker_when_present(tmp_path: Path) -> None:
    """trace value 중 <parse-error: ...> 형식이 있으면 수정/필터 없이 그대로 JSON 에 보존된다."""
    error_marker = "<parse-error: unknown token 'foo'>"
    trace = {
        "overview": "always",
        "stack": error_marker,
    }
    plan = _make_plan(
        included=("overview", "stack"),
        activation_trace=trace,
    )
    _write_plan(tmp_path, plan)

    output, _ = _run_prepare(tmp_path)

    assert output["activation_trace"].get("stack") == error_marker, (
        f"parse-error 마커가 변형됨: {output['activation_trace'].get('stack')!r}"
    )


# ── 테스트 6: consistency_violations 필드 존재 ────────────────────────


def test_prepare_includes_consistency_violations_field(tmp_path: Path) -> None:
    """prepare JSON 출력에 consistency_violations 필드가 항상 존재한다 (빈 list 또는 list of dicts)."""
    trace = {
        "overview": "always",
        "stack": "always",
        "interface.http": "has.http_server",
    }
    plan = _make_plan(
        included=("overview", "stack", "interface.http"),
        activation_trace=trace,
    )
    _write_plan(tmp_path, plan)

    output, _ = _run_prepare(tmp_path)

    assert "consistency_violations" in output, "consistency_violations 필드 누락"
    assert isinstance(output["consistency_violations"], list), (
        f"consistency_violations 가 list 아님: {type(output['consistency_violations'])}"
    )


# ── 테스트 7: mobile-only 시나리오에서 violation 감지 ─────────────────


def test_prepare_consistency_violations_mobile_only_with_interface_http(
    tmp_path: Path,
) -> None:
    """mobile-only plan (profile=react-native-expo) + interface.http 활성 →
    consistency_violations 에 http_server violation 포함.
    exit code 0 (차단 안 함).
    """
    trace = {
        "overview": "always",
        "stack": "always",
        "interface.http": "has.http_server",
    }
    # react-native-expo 단독 — fastapi/nestjs 없음
    pm = PlanManager()
    plan = pm.create(
        project_name="MobileOnlyProject",
        project_type="mobile",
        scale="small",
        user_description_original="모바일 전용 프로젝트",
        profiles=[ProfileRef(id="react-native-expo", path=".")],
        skeleton_sections=SkeletonSpec(
            required=("overview", "stack"),
            optional=("interface.http",),
            included=("overview", "stack", "interface.http"),
        ),
        pipeline_steps=["ha-init", "ha-design", "ha-plan", "ha-build", "ha-verify"],
        activation_trace=trace,
    )
    _write_plan(tmp_path, plan)

    output, _ = _run_prepare(tmp_path)

    # exit code 0 — 차단 안 함 (subprocess 자체가 returncode 0 이어야)
    assert "consistency_violations" in output
    violations = output["consistency_violations"]
    assert isinstance(violations, list)

    # interface.http 섹션의 http_server violation 이 있어야 함
    http_violations = [v for v in violations if v.get("section_id") == "interface.http"]
    assert http_violations, f"interface.http violation 없음. 전체 violations: {violations}"
    v = http_violations[0]
    assert v["missing_atom"] == "http_server"
    assert set(v["expected_providers"]) == {"fastapi", "nestjs", "nextjs"}


# ── commit: LESSON 검증 통합 테스트 ─────────────────────────────────────────


def _write_skeleton(docs_dir: Path, body: str) -> Path:
    """docs/skeleton.md 에 최소 헤딩 + 주어진 body 를 기록."""
    docs_dir.mkdir(parents=True, exist_ok=True)
    skel = docs_dir / "skeleton.md"
    skel.write_text(
        "## 1. 개요\n\n" + body,
        encoding="utf-8",
    )
    return skel


def _write_shared_lessons(docs_dir: Path, ids: list[str]) -> Path:
    """docs/shared-lessons.md 에 주어진 LESSON ID 를 정의 헤딩으로 기록."""
    docs_dir.mkdir(parents=True, exist_ok=True)
    lines = ["# Shared Lessons\n"]
    for lid in ids:
        lines.append(f"\n## {lid}: 테스트용 레슨\n\n내용.\n\n---\n")
    path = docs_dir / "shared-lessons.md"
    path.write_text("".join(lines), encoding="utf-8")
    return path


def _run_commit(
    project_dir: Path,
    skeleton_path: Path,
    *,
    allow_unknown_lessons: bool = False,
    harness_home_override: Path | None = None,
    locked_sections: list[str] | None = None,
    ai_drafted_sections: list[str] | None = None,
    ai_draft: bool = False,
) -> tuple[int, dict | None, str]:
    """cmd_commit 실행. (returncode, parsed_json_or_None, stderr) 반환.

    harness_home_override: HARNESS_AI_HOME 환경변수를 이 경로로 덮어씀.
    shared-lessons.md 부재 시나리오 테스트에 사용.
    """
    cmd = [sys.executable, str(_RUN_PY), "commit", "--skeleton-path", str(skeleton_path)]
    if allow_unknown_lessons:
        cmd.append("--allow-unknown-lessons")
    if locked_sections:
        cmd += ["--locked-sections"] + locked_sections
    if ai_drafted_sections:
        cmd += ["--ai-drafted-sections"] + ai_drafted_sections
    if ai_draft:
        cmd.append("--ai-draft")
    env = _make_env()
    if harness_home_override is not None:
        env["HARNESS_AI_HOME"] = str(harness_home_override)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(project_dir),
        env=env,
    )
    try:
        parsed = json.loads(result.stdout) if result.stdout.strip() else None
    except json.JSONDecodeError:
        parsed = None
    return result.returncode, parsed, result.stderr


def test_commit_fails_on_unknown_lesson_references(tmp_path: Path) -> None:
    """skeleton.md 에 미정의 LESSON-999 인용 → exit code 1, stderr 에 LESSON-999 + 에러 메시지."""
    plan = _make_plan(activation_trace={"overview": "always", "stack": "always"})
    _write_plan(tmp_path, plan)
    skel = _write_skeleton(tmp_path / "docs", "LESSON-999 를 참고한 설계.")
    # shared-lessons.md 에 LESSON-999 없음 (LESSON-001 만 정의)
    _write_shared_lessons(tmp_path / "docs", ["LESSON-001"])

    returncode, out, stderr = _run_commit(tmp_path, skel)

    assert returncode != 0, "미정의 LESSON 인용 시 exit code 0 — fail-fast 미작동"
    assert "LESSON-999" in stderr, f"stderr 에 LESSON-999 누락: {stderr!r}"
    assert "shared-lessons.md" in stderr or "정의 없음" in stderr, (
        f"stderr 에 에러 맥락 없음: {stderr!r}"
    )
    # JSON 출력에 unknown_lesson_references 포함
    assert out is not None, "stdout JSON 없음"
    assert "unknown_lesson_references" in out
    assert any(r["lesson_id"] == "LESSON-999" for r in out["unknown_lesson_references"])


def test_commit_passes_with_allow_unknown_lessons_flag(tmp_path: Path) -> None:
    """--allow-unknown-lessons flag 시 미정의 LESSON 있어도 exit code 0, stderr 경고, JSON 필드 포함."""
    plan = _make_plan(activation_trace={"overview": "always", "stack": "always"})
    _write_plan(tmp_path, plan)
    skel = _write_skeleton(tmp_path / "docs", "LESSON-999 를 참고한 설계.")
    _write_shared_lessons(tmp_path / "docs", ["LESSON-001"])

    returncode, out, stderr = _run_commit(tmp_path, skel, allow_unknown_lessons=True)

    assert returncode == 0, f"--allow-unknown-lessons 에도 불구하고 실패: stderr={stderr!r}"
    # stderr 에 WARN 포함
    assert "LESSON-999" in stderr, f"경고 없음: {stderr!r}"
    # JSON 에 unknown_lesson_references 비어있지 않음
    assert out is not None
    assert "unknown_lesson_references" in out
    assert len(out["unknown_lesson_references"]) > 0, (
        "unknown_lesson_references 가 비어있음 — 경고 대상 레슨이 누락됨"
    )


def test_commit_passes_when_lessons_md_missing(tmp_path: Path) -> None:
    """shared-lessons.md 자체 없으면 LESSON 검증 skip, exit code 0, stderr 안내.

    HARNESS_AI_HOME 을 backend/ 디렉토리만 있고 shared-lessons.md 가 없는
    임시 경로로 덮어씌워 실제 레포 파일에 의존하지 않고 테스트.
    utils.py 는 HARNESS_AI_HOME/backend/ 존재를 요구하므로 최소 구조만 생성.
    """
    # HARNESS_AI_HOME 최소 구조: backend/ 만 있으면 됨 (shared-lessons.md 없음)
    fake_home = tmp_path / "fake_harness_home"
    (fake_home / "backend").mkdir(parents=True)

    # plan + skeleton 은 별도 project_dir 에
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    plan = _make_plan(activation_trace={"overview": "always", "stack": "always"})
    _write_plan(project_dir, plan)
    skel = _write_skeleton(project_dir / "docs", "LESSON-001 참고.")

    returncode, out, stderr = _run_commit(project_dir, skel, harness_home_override=fake_home)

    assert returncode == 0, f"shared-lessons.md 없을 때 실패: stderr={stderr!r}"
    # stderr 에 skip 또는 없음 안내
    assert "skip" in stderr or "없음" in stderr, f"shared-lessons.md 없음 안내 없음: {stderr!r}"


# ── v0.10.0 HITL gate 테스트 ────────────────────────────────────────────────


def test_prepare_outputs_locked_section_ids(tmp_path: Path) -> None:
    """included 에 requirements/user_journey 있으면 output 의 locked_section_ids 에 포함."""
    plan = _make_plan(
        included=("overview", "stack", "requirements", "user_journey"),
        activation_trace={
            "overview": "always",
            "stack": "always",
            "requirements": "always",
            "user_journey": "always",
        },
    )
    _write_plan(tmp_path, plan)

    output, _ = _run_prepare(tmp_path)

    assert "locked_section_ids" in output, "locked_section_ids 필드 누락"
    locked = output["locked_section_ids"]
    assert isinstance(locked, list), f"locked_section_ids 가 list 아님: {type(locked)}"
    assert "requirements" in locked, f"requirements 미포함: {locked}"
    assert "user_journey" in locked, f"user_journey 미포함: {locked}"
    # view.screens 는 included 에 없으므로 미포함
    assert "view.screens" not in locked, f"view.screens 가 포함됨 (included 에 없음): {locked}"
    # overview/stack 은 LOCKED 대상 아님
    assert "overview" not in locked
    assert "stack" not in locked


def test_prepare_locked_section_status_without_skeleton(tmp_path: Path) -> None:
    """skeleton.md 부재 시 locked_section_status 의 3개 LOCKED id 전부 not_included.

    백포트 회귀 가드: 이 필드는 SKILL.md §0/복구 절차가 참조 — run.py 가 출력하지
    않으면 명세-코드 격차 (2026-06-12 미러→repo 백포트 누락으로 실재했던 결함).
    """
    plan = _make_plan(activation_trace={"overview": "always", "stack": "always"})
    _write_plan(tmp_path, plan)

    output, _ = _run_prepare(tmp_path)

    assert "locked_section_status" in output, "locked_section_status 필드 누락"
    status = output["locked_section_status"]
    assert status == {
        "requirements": "not_included",
        "user_journey": "not_included",
        "view.screens": "not_included",
    }, f"skeleton 부재 시 전부 not_included 여야 함: {status}"


def test_prepare_locked_section_status_empty_vs_filled(tmp_path: Path) -> None:
    """HUMAN-LOCKED 블록의 AI-WRITABLE 존 상태로 empty/filled/not_included 판정."""
    plan = _make_plan(activation_trace={"overview": "always", "stack": "always"})
    _write_plan(tmp_path, plan)
    # requirements: placeholder 3개 → empty / user_journey: 채워짐 → filled
    # view.screens: 블록 없음 → not_included
    _write_skeleton(
        tmp_path / "docs",
        "<!-- HUMAN-LOCKED:requirements -->\n"
        "<!-- AI-WRITABLE:candidates -->\n"
        "| <후보 1> | <후보 2> | <후보 3> |\n"
        "<!-- /AI-WRITABLE -->\n"
        "<!-- /HUMAN-LOCKED:requirements -->\n"
        "\n"
        "<!-- HUMAN-LOCKED:user_journey -->\n"
        "<!-- AI-WRITABLE:candidates -->\n"
        "사용자가 도면을 열고 검사 결과를 확인한다.\n"
        "<!-- /AI-WRITABLE -->\n"
        "<!-- /HUMAN-LOCKED:user_journey -->\n",
    )

    output, _ = _run_prepare(tmp_path)

    status = output["locked_section_status"]
    assert status["requirements"] == "empty", f"placeholder 가득인데 empty 아님: {status}"
    assert status["user_journey"] == "filled", f"채워졌는데 filled 아님: {status}"
    assert status["view.screens"] == "not_included", f"블록 없는데 not_included 아님: {status}"


def test_prepare_locked_section_status_real_template_marker(tmp_path: Path) -> None:
    """실제 템플릿 마커(`HUMAN-LOCKED:id — 설명 -->`)도 정확히 판정 — 이슈 #5 회귀.

    fragment 템플릿(templates/skeleton/requirements.md)의 여는 마커는 id 뒤에
    ` — 설명` 접미사가 붙는다. 정규식이 id 바로 뒤 `-->` 만 허용하면 이 마커를
    못 찾아 항상 not_included → LOCKED HITL 인터뷰가 통째로 스킵된다.
    기존 fixture 가 bare 마커만 써서 새지 않았던 케이스.
    """
    plan = _make_plan(activation_trace={"overview": "always", "stack": "always"})
    _write_plan(tmp_path, plan)
    _write_skeleton(
        tmp_path / "docs",
        "<!-- HUMAN-LOCKED:requirements — 이 섹션은 사용자 인터뷰로만 채움. "
        "/ha-redesign 거쳐서만 변경 허용. -->\n"
        "<!-- AI-WRITABLE:candidates -->\n"
        "| <후보 1> | <후보 2> | <후보 3> |\n"
        "<!-- /AI-WRITABLE -->\n"
        "<!-- /HUMAN-LOCKED:requirements -->\n",
    )

    output, _ = _run_prepare(tmp_path)

    status = output["locked_section_status"]
    assert status["requirements"] == "empty", (
        f"실제 템플릿 마커(설명 접미사 포함)인데 not_included 로 새는가? {status}"
    )


def test_commit_freeze_called_with_locked_sections(tmp_path: Path) -> None:
    """--locked-sections requirements user_journey 박으면 frontmatter 에 frozen_status='frozen' + locked_sections 박힘."""
    plan = _make_plan(activation_trace={"overview": "always", "stack": "always"})
    plan_path = _write_plan(tmp_path, plan)
    skel = _write_skeleton(tmp_path / "docs", "정상 내용.")
    _write_shared_lessons(tmp_path / "docs", [])

    returncode, out, stderr = _run_commit(
        tmp_path,
        skel,
        locked_sections=["requirements", "user_journey"],
    )

    assert returncode == 0, f"commit 실패: stderr={stderr!r}\nstdout={out}"
    assert out is not None
    assert out["frozen_status"] == "frozen", f"frozen_status 미변경: {out['frozen_status']}"
    assert set(out["locked_sections"]) == {"requirements", "user_journey"}, (
        f"locked_sections 불일치: {out['locked_sections']}"
    )
    # 실제 파일 frontmatter 에도 반영됐는지 확인
    saved_text = plan_path.read_text(encoding="utf-8")
    assert "frozen_status: frozen" in saved_text, "frontmatter 에 frozen_status 미기록"
    assert "requirements" in saved_text


def test_commit_ai_drafted_without_optin_fails(tmp_path: Path) -> None:
    """--ai-drafted-sections 박았는데 --ai-draft 없으면 exit 1, frontmatter 변경 X."""
    plan = _make_plan(activation_trace={"overview": "always", "stack": "always"})
    plan_path = _write_plan(tmp_path, plan)
    original_text = plan_path.read_text(encoding="utf-8")
    skel = _write_skeleton(tmp_path / "docs", "정상 내용.")
    _write_shared_lessons(tmp_path / "docs", [])

    returncode, out, stderr = _run_commit(
        tmp_path,
        skel,
        locked_sections=["requirements"],
        ai_drafted_sections=["requirements"],
        ai_draft=False,  # 옵트인 누락
    )

    assert returncode != 0, "옵트인 누락 시 exit code 0 — 방어선 미작동"
    assert out is not None
    assert out["transitioned_to"] is None, "실패 시 상태 전이 발생 — 이상"
    # 파일 미변경 (상태 전이 + freeze 둘 다 미적용)
    after_text = plan_path.read_text(encoding="utf-8")
    assert after_text == original_text, "실패 시 frontmatter 변경됨 — 이상"


def test_commit_ai_drafted_with_optin_succeeds(tmp_path: Path) -> None:
    """--ai-drafted-sections + --ai-draft 양쪽 박으면 ai_drafted_sections 박힘."""
    plan = _make_plan(activation_trace={"overview": "always", "stack": "always"})
    plan_path = _write_plan(tmp_path, plan)
    skel = _write_skeleton(tmp_path / "docs", "정상 내용.")
    _write_shared_lessons(tmp_path / "docs", [])

    returncode, out, stderr = _run_commit(
        tmp_path,
        skel,
        locked_sections=["requirements"],
        ai_drafted_sections=["requirements"],
        ai_draft=True,
    )

    assert returncode == 0, f"옵트인 포함 시 실패: stderr={stderr!r}\nstdout={out}"
    assert out is not None
    assert out["frozen_status"] == "frozen"
    assert "requirements" in out["ai_drafted_sections"], (
        f"ai_drafted_sections 에 requirements 없음: {out['ai_drafted_sections']}"
    )
    # 파일에도 반영
    saved_text = plan_path.read_text(encoding="utf-8")
    assert "ai_drafted_sections" in saved_text, "frontmatter 에 ai_drafted_sections 미기록"


def test_commit_no_locked_sections_skips_freeze(tmp_path: Path) -> None:
    """--locked-sections 인자 없으면 freeze() 호출 X. frozen_status='drafting' 유지."""
    plan = _make_plan(activation_trace={"overview": "always", "stack": "always"})
    _write_plan(tmp_path, plan)
    skel = _write_skeleton(tmp_path / "docs", "정상 내용.")
    _write_shared_lessons(tmp_path / "docs", [])

    # locked_sections 인자 없이 기존 방식 그대로
    returncode, out, stderr = _run_commit(tmp_path, skel)

    assert returncode == 0, f"기본 commit 실패: stderr={stderr!r}\nstdout={out}"
    assert out is not None
    assert out["frozen_status"] == "drafting", (
        f"locked_sections 없는데 frozen: {out['frozen_status']}"
    )
    assert out["locked_sections"] == [], f"locked_sections 비어있어야: {out['locked_sections']}"
    assert out["transitioned_to"] == "designed", "상태 전이 미작동"


# ── A3: clarify 서브커맨드 통합 테스트 ─────────────────────────────────────────


def _run_clarify(
    project_dir: Path,
    *,
    max_n: int | None = None,
) -> tuple[int, dict | None, str]:
    """cmd_clarify 실행. (returncode, parsed_json_or_None, stderr) 반환."""
    cmd = [sys.executable, str(_RUN_PY), "clarify"]
    if max_n is not None:
        cmd += ["--max", str(max_n)]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(project_dir),
        env=_make_env(),
    )
    try:
        parsed = json.loads(result.stdout) if result.stdout.strip() else None
    except json.JSONDecodeError:
        parsed = None
    return result.returncode, parsed, result.stderr


def test_clarify_with_vague_skeleton_returns_candidates(tmp_path: Path) -> None:
    """skeleton 에 애매어(빠르게) + I/O 경계(HTTP API) 있으면 clarification_candidates 존재 + exit 0."""
    plan = _make_plan(activation_trace={"overview": "always", "stack": "always"})
    _write_plan(tmp_path, plan)
    # Write skeleton with vague word + I/O boundary section lacking failure path
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "skeleton.md").write_text(
        "## 1. 성능 목표\nAPI는 빠르게 응답해야 한다.\n\n"
        "## 2. HTTP API\nPOST /api/users 사용자 생성. 200 OK 반환.\n",
        encoding="utf-8",
    )

    returncode, out, stderr = _run_clarify(tmp_path)

    assert returncode == 0, f"clarify 실패: stderr={stderr!r}\nstdout={out}"
    assert out is not None, "stdout JSON 없음"
    assert "checklist_findings" in out, "checklist_findings 필드 누락"
    assert "clarification_candidates" in out, "clarification_candidates 필드 누락"
    assert isinstance(out["clarification_candidates"], list)
    assert len(out["clarification_candidates"]) > 0, "후보가 0개인데 애매어/I/O 경계 있음"

    # Each candidate must have required fields
    for cand in out["clarification_candidates"]:
        assert "section_id" in cand
        assert "category" in cand
        assert "question" in cand
        assert "hint" in cand


def test_clarify_without_skeleton_exits_3(tmp_path: Path) -> None:
    """skeleton.md 없으면 exit code 3."""
    plan = _make_plan(activation_trace={"overview": "always", "stack": "always"})
    _write_plan(tmp_path, plan)
    # Do NOT write skeleton.md

    returncode, out, stderr = _run_clarify(tmp_path)

    assert returncode == 3, f"skeleton 없을 때 exit 3 이어야 함: returncode={returncode}"
