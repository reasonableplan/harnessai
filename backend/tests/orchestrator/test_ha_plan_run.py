"""ha-plan/run.py cmd_commit 의 agent mismatch 검증 회귀 테스트 (Group 3 Step 2).

패턴: subprocess 로 run.py 실행 (test_ha_design_run.py 와 동일).
PlanManager / HarnessPlan 을 직접 import 해 픽스처 구성,
subprocess 를 통해 cmd_commit 을 호출 — stdout/stderr 분리 수집.

테스트 커버리지:
  1. 모든 task agent 가 active context 와 매칭 → exit 0, agent_mismatches=[]
  2. task agent 가 context 불일치 → exit 1, stderr 에 task ID
  3. --allow-agent-mismatch flag → exit 0, stderr 에 WARN, agent_mismatches 채워짐
  4. capability-agnostic agent (architect, reviewer 등) → 항상 pass
  5. paired profile (fastapi + react-native-expo) → backend_coder + mobile_coder_rn 둘 다 pass
  6. agents.yaml 에 없는 unknown agent_id → exit 1, "unknown agent" 형식 에러
  7. --tasks-content 빈 문자열 → exit != 0 (commit 거부) — 회귀 보호
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
    ScaleAxes,
    SkeletonSpec,
)

# ha-plan/run.py 절대 경로
_RUN_PY = Path.home() / ".claude" / "skills" / "ha-plan" / "run.py"

# HARNESS_AI_HOME: agent/ 디렉토리 (backend/ 의 부모)
# __file__ = backend/tests/orchestrator/test_ha_plan_run.py
# parents[0]=orchestrator, [1]=tests, [2]=backend, [3]=agent
_HARNESS_HOME = Path(__file__).resolve().parents[3]


def _make_env() -> dict[str, str]:
    """subprocess 용 환경변수. HARNESS_AI_HOME 을 이 레포로 명시 설정."""
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


def _write_skeleton(tmp_path: Path) -> Path:
    """docs/skeleton.md 최소 구조 생성 (commit 이 read 하는 필수 파일)."""
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    skel = docs / "skeleton.md"
    skel.write_text(
        "## 1. 개요\n\n테스트 프로젝트.\n\n## 18. 태스크 분해\n\n",
        encoding="utf-8",
    )
    return skel


def _make_plan(
    *,
    profiles: list[ProfileRef],
    scale_axes: ScaleAxes | None = None,
    activation_trace: dict[str, str] | None = None,
    included: tuple[str, ...] = ("overview", "stack"),
) -> HarnessPlan:
    """state="designed" HarnessPlan 생성 헬퍼."""
    pm = PlanManager()
    plan = pm.create(
        project_name="TestProject",
        project_type="app",
        scale="small",
        user_description_original="테스트 프로젝트",
        profiles=profiles,
        skeleton_sections=SkeletonSpec(
            required=("overview", "stack"),
            optional=("interface.http",),
            included=included,
        ),
        pipeline_steps=["ha-init", "ha-design", "ha-plan", "ha-build", "ha-verify"],
        scale_axes=scale_axes or ScaleAxes(),
        activation_trace=activation_trace,
    )
    # init → designed 전이 (assert_state 가 "designed" 를 요구)
    plan = pm.transition(plan, "designed", completed_step="ha-design")
    return plan


def _run_prepare(project_dir: Path) -> tuple[int, dict | None, str]:
    """cmd_prepare 실행. (returncode, parsed_json_or_None, stderr) 반환."""
    result = subprocess.run(
        [sys.executable, str(_RUN_PY), "prepare"],
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


def _make_tasks_content(rows: list[tuple[str, str]]) -> str:
    """(task_id, agent_id) 리스트로 최소 tasks.md 본문 생성.

    포맷: | T-NNN | agent_id | - | 설명 | 대기 |
    """
    header = "### Phase 1 — MVP\n| ID | 에이전트 | 의존성 | 설명 | 상태 |\n|----|---------|--------|------|------|\n"
    task_rows = "".join(f"| {tid} | {agent} | - | 테스트 태스크 | 대기 |\n" for tid, agent in rows)
    return header + task_rows


def _run_commit(
    project_dir: Path,
    tasks_content: str,
    *,
    allow_mismatch: bool = False,
    allow_format_drift: bool = False,
) -> tuple[int, dict | None, str]:
    """cmd_commit 실행. (returncode, parsed_json_or_None, stderr) 반환."""
    cmd = [
        sys.executable,
        str(_RUN_PY),
        "commit",
        "--tasks-content",
        tasks_content,
    ]
    if allow_mismatch:
        cmd.append("--allow-agent-mismatch")
    if allow_format_drift:
        cmd.append("--allow-format-drift")
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


# ── Test 1: 모든 task agent 가 active context 와 매칭 → exit 0 ──────────────


def test_commit_passes_when_all_tasks_match_context(tmp_path: Path) -> None:
    """react-native-expo plan + mobile_coder_rn task → exit 0, agent_mismatches=[]."""
    plan = _make_plan(
        profiles=[ProfileRef(id="react-native-expo", path=".")],
        scale_axes=ScaleAxes(
            user_scale="medium",
            data_sensitivity="pii",
            team_size="small",
            availability="standard",
            monetization="none",
            lifecycle="mvp",
        ),
    )
    _write_plan(tmp_path, plan)
    _write_skeleton(tmp_path)

    tasks_content = _make_tasks_content(
        [
            ("T-001", "mobile_coder_rn"),
            ("T-002", "mobile_coder_rn"),
            ("T-003", "mobile_coder_rn"),
        ]
    )
    returncode, out, stderr = _run_commit(tmp_path, tasks_content)

    assert returncode == 0, (
        f"모든 task 가 context 와 매칭임에도 실패. returncode={returncode}\nstderr={stderr!r}"
    )
    assert out is not None, "stdout JSON 없음"
    assert out.get("agent_mismatches") == [], (
        f"agent_mismatches 가 비어있지 않음: {out.get('agent_mismatches')}"
    )


def test_commit_task_count_excludes_dependency_cells(tmp_path: Path) -> None:
    """task_count 는 완전한 태스크 행만 센다 — 의존성 컬럼의 단일 T-ID 셀 제외 (이슈 #10).

    순진한 `\\|\\s*(T-\\d+)\\s*\\|` 는 `| T-001 |` 같은 단일-의존 셀도 집계해
    3행을 5로 부풀렸다. _TASK_AGENT_ROW_RE(완전한 행)로 카운트해야 정확하다.
    """
    plan = _make_plan(
        profiles=[ProfileRef(id="react-native-expo", path=".")],
        scale_axes=ScaleAxes(
            user_scale="medium",
            data_sensitivity="pii",
            team_size="small",
            availability="standard",
            monetization="none",
            lifecycle="mvp",
        ),
    )
    _write_plan(tmp_path, plan)
    _write_skeleton(tmp_path)

    tasks_content = (
        "### Phase 1 — MVP\n"
        "| ID | 에이전트 | 의존성 | 설명 | 상태 |\n"
        "|----|---------|--------|------|------|\n"
        "| T-001 | mobile_coder_rn | - | 첫 태스크 | 대기 |\n"
        "| T-002 | mobile_coder_rn | T-001 | 둘째 태스크 | 대기 |\n"
        "| T-003 | mobile_coder_rn | T-002 | 셋째 태스크 | 대기 |\n"
    )
    returncode, out, stderr = _run_commit(tmp_path, tasks_content)

    assert out is not None, f"stdout JSON 없음. stderr={stderr!r}"
    assert out["task_count"] == 3, (
        f"의존성 셀이 카운트에 새는가? task_count={out['task_count']} (기대 3)"
    )


# ── Test 2: task agent 가 context 불일치 → exit 1, stderr 에 task ID ────────


def test_commit_fails_when_task_agent_mismatches_context(tmp_path: Path) -> None:
    """react-native-expo plan + backend_coder task → exit 1 (http_server 없음)."""
    plan = _make_plan(
        profiles=[ProfileRef(id="react-native-expo", path=".")],
    )
    _write_plan(tmp_path, plan)
    _write_skeleton(tmp_path)

    # backend_coder requires http_server/cli_entrypoint/sdk_surface — rn profile 에 없음
    tasks_content = _make_tasks_content(
        [
            ("T-001", "backend_coder"),
        ]
    )
    returncode, out, stderr = _run_commit(tmp_path, tasks_content)

    assert returncode != 0, "mismatch 상황에서 exit code 0 — fail-fast 미작동"
    assert "T-001" in stderr, f"stderr 에 T-001 누락: {stderr!r}"
    # stdout JSON 에 agent_mismatches 가 포함되어야 함 (--allow 없이도 출력)
    # run.py 는 fail 시 JSON 없이 종료할 수 있으므로 out is None 도 허용,
    # 그 경우 stderr 에 "backend_coder" 언급 확인
    if out is not None:
        assert len(out.get("agent_mismatches", [])) > 0, "agent_mismatches 가 비어있음"
    else:
        assert "backend_coder" in stderr, f"stderr 에 agent 정보 없음: {stderr!r}"


# ── Test 3: --allow-agent-mismatch → exit 0, WARN, agent_mismatches 채워짐 ──


def test_commit_passes_with_allow_agent_mismatch_flag(tmp_path: Path) -> None:
    """mismatch 상황 + --allow-agent-mismatch → exit 0, stderr WARN, JSON 비어있지 않음."""
    plan = _make_plan(
        profiles=[ProfileRef(id="react-native-expo", path=".")],
    )
    _write_plan(tmp_path, plan)
    _write_skeleton(tmp_path)

    tasks_content = _make_tasks_content(
        [
            ("T-001", "backend_coder"),
        ]
    )
    returncode, out, stderr = _run_commit(tmp_path, tasks_content, allow_mismatch=True)

    assert returncode == 0, (
        f"--allow-agent-mismatch 에도 불구하고 실패. returncode={returncode}\nstderr={stderr!r}"
    )
    # stderr 에 WARN 또는 경고 메시지
    assert "WARN" in stderr or "경고" in stderr or "mismatch" in stderr.lower(), (
        f"stderr 에 경고 없음: {stderr!r}"
    )
    assert out is not None, "stdout JSON 없음"
    assert len(out.get("agent_mismatches", [])) > 0, (
        "agent_mismatches 가 비어있음 — 경고 대상이 누락됨"
    )


# ── Test 4: capability-agnostic agents 는 항상 pass ─────────────────────────


def test_commit_capability_agnostic_agents_always_pass(tmp_path: Path) -> None:
    """architect / reviewer / qa 는 어떤 plan 컨텍스트에서도 mismatch 없음."""
    # 최소 프로파일 — react-native-expo (backend capability 없음)
    plan = _make_plan(
        profiles=[ProfileRef(id="react-native-expo", path=".")],
    )
    _write_plan(tmp_path, plan)
    _write_skeleton(tmp_path)

    # capability-agnostic agents: requires_capabilities=[], requires_profile_ids=[]
    tasks_content = _make_tasks_content(
        [
            ("T-001", "architect"),
            ("T-002", "reviewer"),
            ("T-003", "qa"),
            ("T-004", "designer"),
            ("T-005", "orchestrator"),
        ]
    )
    returncode, out, stderr = _run_commit(tmp_path, tasks_content)

    assert returncode == 0, (
        f"agnostic agents 가 fail 됨. returncode={returncode}\nstderr={stderr!r}"
    )
    assert out is not None
    assert out.get("agent_mismatches") == [], (
        f"agnostic agents 에서 mismatches 발생: {out.get('agent_mismatches')}"
    )


# ── Test 5: paired profiles → backend_coder + mobile_coder_rn 둘 다 pass ────


def test_commit_paired_profiles_unlock_backend_tasks(tmp_path: Path) -> None:
    """fastapi + react-native-expo paired → backend_coder 와 mobile_coder_rn 모두 OK."""
    plan = _make_plan(
        profiles=[
            ProfileRef(id="fastapi", path="backend/"),
            ProfileRef(id="react-native-expo", path="mobile/"),
        ],
    )
    _write_plan(tmp_path, plan)
    _write_skeleton(tmp_path)

    tasks_content = _make_tasks_content(
        [
            ("T-001", "backend_coder"),
            ("T-002", "mobile_coder_rn"),
        ]
    )
    returncode, out, stderr = _run_commit(tmp_path, tasks_content)

    assert returncode == 0, f"paired profiles 에서 fail. returncode={returncode}\nstderr={stderr!r}"
    assert out is not None
    assert out.get("agent_mismatches") == [], (
        f"paired profiles 에서 mismatches 발생: {out.get('agent_mismatches')}"
    )


# ── Test 6: agents.yaml 에 없는 unknown agent_id → exit 1 ───────────────────


def test_commit_unknown_agent_id_reported(tmp_path: Path) -> None:
    """tasks.md 에 agents.yaml 에 없는 agent → exit 1, "unknown agent" 형식 에러."""
    plan = _make_plan(
        profiles=[ProfileRef(id="react-native-expo", path=".")],
    )
    _write_plan(tmp_path, plan)
    _write_skeleton(tmp_path)

    tasks_content = _make_tasks_content(
        [
            ("T-001", "mystery_coder"),
        ]
    )
    returncode, out, stderr = _run_commit(tmp_path, tasks_content)

    assert returncode != 0, "unknown agent 에서 exit code 0 — 오류 감지 미작동"
    # stderr 또는 JSON 에 "unknown" 언급
    has_unknown_in_stderr = "unknown" in stderr.lower() or "mystery_coder" in stderr
    has_unknown_in_json = out is not None and any(
        "unknown" in mm.get("reason", "").lower() for mm in out.get("agent_mismatches", [])
    )
    assert has_unknown_in_stderr or has_unknown_in_json, (
        f"unknown agent 에러 메시지 없음. stderr={stderr!r}, out={out}"
    )


# ── Test 7: --tasks-content 빈 문자열 → exit != 0 (회귀 보호) ───────────────


def test_commit_empty_tasks_content_returns_error(tmp_path: Path) -> None:
    """--tasks-content 빈 문자열 → commit 거부 (exit != 0) — 기존 동작 회귀 보호."""
    plan = _make_plan(
        profiles=[ProfileRef(id="react-native-expo", path=".")],
    )
    _write_plan(tmp_path, plan)
    _write_skeleton(tmp_path)

    returncode, _out, stderr = _run_commit(tmp_path, "")

    assert returncode != 0, f"빈 tasks-content 에서 exit code 0 — 검증 누락\nstderr={stderr!r}"


# ── prepare: consistency_violations 검증 테스트 (Group 2 Step 1) ─────────────


def test_prepare_includes_consistency_violations_field(tmp_path: Path) -> None:
    """prepare JSON 출력에 consistency_violations 필드가 항상 존재한다 (list 타입)."""
    trace = {
        "overview": "always",
        "stack": "always",
        "interface.http": "has.http_server",
    }
    plan = _make_plan(
        profiles=[ProfileRef(id="fastapi", path="backend/")],
        activation_trace=trace,
        included=("overview", "stack", "interface.http"),
    )
    _write_plan(tmp_path, plan)
    _write_skeleton(tmp_path)

    returncode, out, stderr = _run_prepare(tmp_path)

    assert returncode == 0, f"prepare 실패 (exit {returncode})\nstderr={stderr!r}"
    assert out is not None, "stdout JSON 없음"
    assert "consistency_violations" in out, "consistency_violations 필드 누락"
    assert isinstance(out["consistency_violations"], list), (
        f"consistency_violations 가 list 아님: {type(out['consistency_violations'])}"
    )


def test_prepare_consistency_violations_mobile_only_with_interface_http(
    tmp_path: Path,
) -> None:
    """mobile-only plan (react-native-expo) + interface.http 활성 →
    consistency_violations 에 http_server violation 포함.
    exit code 0 (advisory — 차단 안 함).
    """
    trace = {
        "overview": "always",
        "stack": "always",
        "interface.http": "has.http_server",
    }
    plan = _make_plan(
        profiles=[ProfileRef(id="react-native-expo", path=".")],
        activation_trace=trace,
        included=("overview", "stack", "interface.http"),
    )
    _write_plan(tmp_path, plan)
    _write_skeleton(tmp_path)

    returncode, out, stderr = _run_prepare(tmp_path)

    assert returncode == 0, (
        f"advisory 검증임에도 prepare 차단됨 (exit {returncode})\nstderr={stderr!r}"
    )
    assert out is not None, "stdout JSON 없음"
    assert "consistency_violations" in out

    violations = out["consistency_violations"]
    assert isinstance(violations, list)

    http_violations = [v for v in violations if v.get("section_id") == "interface.http"]
    assert http_violations, f"interface.http violation 없음. 전체 violations: {violations}"
    v = http_violations[0]
    assert v["missing_atom"] == "http_server", f"missing_atom 불일치: {v['missing_atom']!r}"
    assert "fastapi" in v["expected_providers"] or "nestjs" in v["expected_providers"], (
        f"expected_providers 에 backend profile 없음: {v['expected_providers']}"
    )


def test_prepare_legacy_plan_empty_trace_warns_to_stderr(tmp_path: Path) -> None:
    """activation_trace 없는 (legacy) plan — stderr 경고 출력, consistency_violations=[], exit 0."""
    plan = _make_plan(
        profiles=[ProfileRef(id="react-native-expo", path=".")],
        activation_trace=None,  # legacy: empty dict
    )
    _write_plan(tmp_path, plan)
    _write_skeleton(tmp_path)

    returncode, out, stderr = _run_prepare(tmp_path)

    assert returncode == 0, f"legacy plan prepare 실패 (exit {returncode})\nstderr={stderr!r}"
    assert out is not None, "stdout JSON 없음"
    # stderr 에 legacy 경고
    assert "trace 미포함" in stderr or "cross-check 불가능" in stderr, (
        f"legacy plan 경고 없음. stderr: {stderr!r}"
    )
    # consistency_violations 는 빈 list (trace 없으면 검증 skip)
    assert out.get("consistency_violations") == [], (
        f"legacy plan 에서 consistency_violations 비어있지 않음: {out.get('consistency_violations')}"
    )


def test_prepare_paired_no_violations(tmp_path: Path) -> None:
    """fastapi + react-native-expo paired + 정합 trace → consistency_violations=[]."""
    trace = {
        "overview": "always",
        "stack": "always",
        "interface.http": "has.http_server",
    }
    plan = _make_plan(
        profiles=[
            ProfileRef(id="fastapi", path="backend/"),
            ProfileRef(id="react-native-expo", path="mobile/"),
        ],
        activation_trace=trace,
        included=("overview", "stack", "interface.http"),
    )
    _write_plan(tmp_path, plan)
    _write_skeleton(tmp_path)

    returncode, out, stderr = _run_prepare(tmp_path)

    assert returncode == 0, f"paired plan prepare 실패 (exit {returncode})\nstderr={stderr!r}"
    assert out is not None, "stdout JSON 없음"
    assert out.get("consistency_violations") == [], (
        f"paired plan 에서 violation 발생: {out.get('consistency_violations')}"
    )


# ── Test 10: fractional task ID → schema fail-fast (Group 4 Step 1) ──────────


def test_commit_fails_on_fractional_task_id(tmp_path: Path) -> None:
    """tasks.md 에 T-024.5 → exit code != 0, stderr 에 line + kind, JSON 에 schema_violations."""
    plan = _make_plan(
        profiles=[ProfileRef(id="react-native-expo", path=".")],
    )
    _write_plan(tmp_path, plan)
    _write_skeleton(tmp_path)

    # fractional ID: T-024.5 는 _TASK_ID_CANDIDATE_RE 에 매칭되어 먼저 차단될 수 있으나
    # validate_tasks_md 도 동일하게 잡아야 한다 (이중 검증 일관성).
    # _TASK_ID_CANDIDATE_RE 는 \| T-[\w-]+ \| 를 추출하므로 "T-024.5" 는
    # '.' 가 \w 에 포함 안 돼 추출 안 될 수 있음 — validate_tasks_md 가 유일한 방어선일 수 있음.
    fractional_content = (
        "### Phase 1 — MVP\n"
        "| ID | 에이전트 | 의존성 | 설명 | 상태 |\n"
        "|----|---------|--------|------|------|\n"
        "| T-001 | mobile_coder_rn | - | 정상 태스크 | 대기 |\n"
        "| T-024.5 | mobile_coder_rn | T-001 | fractional ID | 대기 |\n"
    )
    returncode, out, stderr = _run_commit(tmp_path, fractional_content)

    assert returncode != 0, (
        f"T-024.5 fractional ID 에서 exit code 0 — schema fail-fast 미작동\nstderr={stderr!r}"
    )
    # stderr 또는 stdout JSON 에 위반 정보 존재
    has_violation_in_stderr = (
        "T-024.5" in stderr or "schema" in stderr.lower() or "형식 위반" in stderr
    )
    has_violation_in_json = out is not None and len(out.get("schema_violations", [])) > 0
    assert has_violation_in_stderr or has_violation_in_json, (
        f"T-024.5 위반 정보 없음. returncode={returncode}\nstderr={stderr!r}\nout={out}"
    )


# ── Test 11: --allow-format-drift → exit 0, schema_violations 채워짐 ─────────


def test_commit_passes_with_allow_format_drift_flag(tmp_path: Path) -> None:
    """fractional ID + --allow-format-drift → exit 0, JSON 의 schema_violations 채워짐."""
    plan = _make_plan(
        profiles=[ProfileRef(id="react-native-expo", path=".")],
    )
    _write_plan(tmp_path, plan)
    _write_skeleton(tmp_path)

    # T-024.5 는 _TASK_ID_CANDIDATE_RE 로 추출이 안 될 수 있으므로
    # 먼저 상위 candidate 검증을 우회한 후 schema 검증만 발동되도록
    # 컬럼 수 또는 상태 위반으로 schema violation 을 유발.
    # 상태 "invalid_status_value" → VALID_STATUSES 에 없음 → schema violation.
    bad_status_content = (
        "### Phase 1 — MVP\n"
        "| ID | 에이전트 | 의존성 | 설명 | 상태 |\n"
        "|----|---------|--------|------|------|\n"
        "| T-001 | mobile_coder_rn | - | 태스크 | invalid_status_value |\n"
    )
    returncode, out, stderr = _run_commit(tmp_path, bad_status_content, allow_format_drift=True)

    assert returncode == 0, (
        f"--allow-format-drift 에도 불구하고 실패. returncode={returncode}\nstderr={stderr!r}"
    )
    assert out is not None, "stdout JSON 없음"
    violations = out.get("schema_violations", [])
    assert len(violations) > 0, (
        "--allow-format-drift 로 진행 시 schema_violations 가 비어있음 — 위반 추적 불가"
    )
    # stderr 에 WARN 포함
    assert "WARN" in stderr or "schema" in stderr.lower(), (
        f"--allow-format-drift 시 경고 없음. stderr={stderr!r}"
    )


# ── Test 12: 정상 tasks.md → exit 0, schema_violations=[] ───────────────────


def test_commit_passes_on_compliant_tasks_md(tmp_path: Path) -> None:
    """정상 tasks.md → exit 0, schema_violations=[]."""
    plan = _make_plan(
        profiles=[ProfileRef(id="react-native-expo", path=".")],
    )
    _write_plan(tmp_path, plan)
    _write_skeleton(tmp_path)

    # 챙겼니 형식과 동일한 정상 tasks.md
    compliant_content = (
        "### Phase 1 — MVP\n"
        "| ID | 에이전트 | 의존성 | 설명 | 상태 |\n"
        "|----|---------|--------|------|------|\n"
        "| T-001 | mobile_coder_rn | - | 프로젝트 초기화 | 대기 |\n"
        "| T-002 | mobile_coder_rn | T-001 | NativeWind 설정 | 대기 |\n"
        "| T-003 | mobile_coder_rn | T-001, T-002 | 컴포넌트 | 대기 |\n"
    )
    returncode, out, stderr = _run_commit(tmp_path, compliant_content)

    assert returncode == 0, f"정상 tasks.md 에서 실패. returncode={returncode}\nstderr={stderr!r}"
    assert out is not None, "stdout JSON 없음"
    assert out.get("schema_violations") == [], (
        f"정상 tasks.md 에서 schema_violations 비어있지 않음: {out.get('schema_violations')}"
    )
