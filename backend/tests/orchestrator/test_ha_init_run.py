"""ha-init/run.py cmd_write 의 --external-capabilities 옵션 회귀 테스트.

Group 1-D: BaaS escape hatch — 사용자가 Firebase / Supabase 같은 외부 서비스를
사용할 때 external_capabilities 를 명시해서 false-positive violation 방지.

subprocess 방식으로 run.py 를 직접 실행 — test_ha_design_run.py 패턴 동일.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

# ha-init/run.py 절대 경로
_RUN_PY = Path.home() / ".claude" / "skills" / "ha-init" / "run.py"

# HARNESS_AI_HOME: agent/ 디렉토리
# __file__ = backend/tests/orchestrator/test_ha_init_run.py
# parents[0]=orchestrator, [1]=tests, [2]=backend, [3]=agent
_HARNESS_HOME = Path(__file__).resolve().parents[3]  # agent/


def _make_env() -> dict[str, str]:
    """subprocess 용 환경 변수. HARNESS_AI_HOME 을 이 레포로 명시 설정."""
    env = os.environ.copy()
    env["HARNESS_AI_HOME"] = str(_HARNESS_HOME)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


@pytest.mark.skipif(not _RUN_PY.exists(), reason="ha-init/run.py not found")
def test_write_accepts_external_capabilities_flag(tmp_path: Path) -> None:
    """--external-capabilities 'http_server,users' → plan.external_capabilities 저장.

    react-native-expo 프로파일을 수동 로드해서 cmd_write write 실행 후
    생성된 harness-plan.md 를 PlanManager.load() 로 읽어 external_capabilities 확인.
    """
    from src.orchestrator.plan_manager import PlanManager  # noqa: PLC0415

    # Setup: react-native-expo 프로파일이 없을 수 있으므로 profiles 를 --profiles 에
    # 임의 ID 대신 detect 가능한 프로파일 또는 직접 명시. 여기서는 --included 로 override
    # 해서 fragment 평가 없이 진행 (auto 대신 직접 섹션 지정).
    project = tmp_path / "project"
    project.mkdir()

    # 최소 구성 — python-cli 감지 파일 생성
    (project / "pyproject.toml").write_text(
        "[project.scripts]\nmyapp = 'myapp:main'\n", encoding="utf-8"
    )

    result = subprocess.run(
        [
            sys.executable,
            str(_RUN_PY),
            "write",
            "--project",
            str(project),
            "--profiles",
            "python-cli",
            "--included",
            "overview,stack",
            "--description",
            "Firebase BaaS 사용",
            "--project-type",
            "mobile BaaS",
            "--external-capabilities",
            "http_server,users",
            "--overwrite",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_make_env(),
    )

    assert result.returncode == 0, (
        f"exit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    out = json.loads(result.stdout)
    plan_path = Path(out["plan_path"])

    pm = PlanManager()
    plan = pm.load(plan_path)
    assert sorted(plan.external_capabilities) == ["http_server", "users"], (
        f"external_capabilities 불일치: {plan.external_capabilities}"
    )


@pytest.mark.skipif(not _RUN_PY.exists(), reason="ha-init/run.py not found")
def test_write_rejects_unknown_external_atom(tmp_path: Path) -> None:
    """--external-capabilities 'foobar' → exit code != 0, stderr 에 'unknown atom'."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        "[project.scripts]\nmyapp = 'myapp:main'\n", encoding="utf-8"
    )

    result = subprocess.run(
        [
            sys.executable,
            str(_RUN_PY),
            "write",
            "--project",
            str(project),
            "--profiles",
            "python-cli",
            "--included",
            "overview",
            "--external-capabilities",
            "foobar",
            "--overwrite",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_make_env(),
    )

    assert result.returncode != 0, (
        f"unknown atom 은 exit != 0 이어야 함. exit={result.returncode}\nstderr={result.stderr}"
    )
    assert "unknown atom" in result.stderr.lower() or "unknown" in result.stderr, (
        f"stderr 에 'unknown atom' 메시지 없음: {result.stderr}"
    )


# ── 6축 모순 결정론 체크 (design backlog D) ─────────────────────────


_REPO_RUN_PY = _HARNESS_HOME / "skills" / "ha-init" / "run.py"


@pytest.fixture(scope="module")
def ha_init_module() -> ModuleType:
    """repo 의 ha-init/run.py 를 모듈로 로드 (_axis_warnings 단위 테스트용)."""
    loader = SourceFileLoader("ha_init_run_axes", str(_REPO_RUN_PY))
    spec = importlib.util.spec_from_loader("ha_init_run_axes", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_init_run_axes"] = mod
    loader.exec_module(mod)
    return mod


def _axes(**kw):
    base = dict(
        user_scale="small",
        data_sensitivity="none",
        team_size="solo",
        availability="standard",
        monetization="none",
        lifecycle="mvp",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_axis_warning_payment_without_sensitivity(ha_init_module) -> None:
    warnings = ha_init_module._axis_warnings(_axes(monetization="payment"))
    assert len(warnings) == 1
    assert "data_sensitivity" in warnings[0]


def test_axis_warning_high_availability_poc(ha_init_module) -> None:
    warnings = ha_init_module._axis_warnings(_axes(availability="high", lifecycle="poc"))
    assert len(warnings) == 1


def test_axis_no_warning_for_consistent_answers(ha_init_module) -> None:
    assert ha_init_module._axis_warnings(_axes()) == []
    assert (
        ha_init_module._axis_warnings(_axes(monetization="payment", data_sensitivity="payment"))
        == []
    )


# ── S-1: 활성 섹션 canonical 삽입 배치 ──────────────────────────────

_FASTAPI_ORDER = [
    "overview",
    "requirements",
    "stack",
    "configuration",
    "environments",
    "errors",
    "auth",
    "persistence",
    "integrations",
    "interface.http",
    "rate_limiting",
    "state.flow",
    "core.logic",
    "observability",
    "deployment",
    "test_strategy",
    "ci_cd",
]


def test_order_inserts_auto_sections_canonically(ha_init_module) -> None:
    """프로파일 order 에 없는 6축 자동 활성 섹션이 끝에 append 되지 않고
    canonical 위치에 삽입된다 (기존: user_journey 가 notes 뒤 dangling)."""
    included = [*_FASTAPI_ORDER, "user_journey", "threat_model", "tasks", "notes"]
    ordered = ha_init_module._order_included_sections(included, _FASTAPI_ORDER)

    assert ordered.index("user_journey") == ordered.index("requirements") + 1
    assert ordered.index("threat_model") < ordered.index("persistence")
    assert ordered[-2:] == ["tasks", "notes"]


def test_order_terminal_always_last(ha_init_module) -> None:
    """canonical 후미 섹션(test_strategy 등)이 있어도 tasks/notes 가 마지막."""
    included = ["overview", "test_strategy", "tasks", "notes", "slo"]
    ordered = ha_init_module._order_included_sections(included, ["overview"])
    assert ordered[-2:] == ["tasks", "notes"]
    assert set(ordered) == set(included)


def test_order_keeps_profile_primacy(ha_init_module) -> None:
    """프로파일이 canonical 과 다른 순서를 명시하면 프로파일이 이긴다."""
    profile_order = ["overview", "test_strategy", "ci_cd"]  # canonical 은 ci_cd 먼저
    included = ["overview", "ci_cd", "test_strategy"]
    ordered = ha_init_module._order_included_sections(included, profile_order)
    assert ordered == ["overview", "test_strategy", "ci_cd"]


def test_order_unknown_id_lands_before_terminal(ha_init_module) -> None:
    """canonical 에 없는 미지 ID 는 본문 끝 (terminal 직전) 에 배치."""
    included = ["overview", "zzz.custom", "tasks"]
    ordered = ha_init_module._order_included_sections(included, ["overview"])
    assert ordered == ["overview", "zzz.custom", "tasks"]


# ── 조각3: --decision-rationale (blueprint 흡수 B) ──────────────────────


@pytest.mark.skipif(not _RUN_PY.exists(), reason="ha-init/run.py not found")
def test_write_records_decision_rationale(tmp_path: Path) -> None:
    """--decision-rationale → plan body 판단 근거에 '결정 근거' 블록 기록."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        "[project.scripts]\nmyapp = 'myapp:main'\n", encoding="utf-8"
    )

    rationale = "python-cli — 이유: 단일 명령 자동화. 트레이드오프: GUI 없음"
    result = subprocess.run(
        [
            sys.executable,
            str(_RUN_PY),
            "write",
            "--project",
            str(project),
            "--profiles",
            "python-cli",
            "--included",
            "overview,stack",
            "--description",
            "CLI 자동화 도구",
            "--decision-rationale",
            rationale,
            "--overwrite",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_make_env(),
    )
    assert result.returncode == 0, (
        f"exit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    out = json.loads(result.stdout)
    plan_text = Path(out["plan_path"]).read_text(encoding="utf-8")
    assert "결정 근거" in plan_text
    assert rationale in plan_text


@pytest.mark.skipif(not _RUN_PY.exists(), reason="ha-init/run.py not found")
def test_write_without_rationale_omits_block(tmp_path: Path) -> None:
    """--decision-rationale 미전달 → '결정 근거' 블록 없음 (기존 동작 유지)."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        "[project.scripts]\nmyapp = 'myapp:main'\n", encoding="utf-8"
    )

    result = subprocess.run(
        [
            sys.executable,
            str(_RUN_PY),
            "write",
            "--project",
            str(project),
            "--profiles",
            "python-cli",
            "--included",
            "overview",
            "--description",
            "CLI 도구",
            "--overwrite",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_make_env(),
    )
    assert result.returncode == 0, f"stderr={result.stderr}"
    out = json.loads(result.stdout)
    plan_text = Path(out["plan_path"]).read_text(encoding="utf-8")
    assert "결정 근거" not in plan_text
