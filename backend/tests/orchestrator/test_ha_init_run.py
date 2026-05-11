"""ha-init/run.py cmd_write 의 --external-capabilities 옵션 회귀 테스트.

Group 1-D: BaaS escape hatch — 사용자가 Firebase / Supabase 같은 외부 서비스를
사용할 때 external_capabilities 를 명시해서 false-positive violation 방지.

subprocess 방식으로 run.py 를 직접 실행 — test_ha_design_run.py 패턴 동일.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

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
            "--project", str(project),
            "--profiles", "python-cli",
            "--included", "overview,stack",
            "--description", "Firebase BaaS 사용",
            "--project-type", "mobile BaaS",
            "--external-capabilities", "http_server,users",
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
            "--project", str(project),
            "--profiles", "python-cli",
            "--included", "overview",
            "--external-capabilities", "foobar",
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
