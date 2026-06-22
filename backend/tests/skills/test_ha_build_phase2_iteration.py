"""ha-build Phase 추가 빌드 (issue #9) 회귀 테스트.

forward-only 파이프라인이 reviewed 이후 Phase 2 태스크 빌드를 막던 결함:
`_enter_build_state` 가 built/verified/reviewed 에서 building 으로 회귀시켜
새 코드가 verify/review 게이트를 다시 거치게 한다. planned/building 은 무변경,
designed 등 빌드 불가 상태는 차단(exit 2).
"""

from __future__ import annotations

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_ha_build() -> ModuleType:
    loader = SourceFileLoader(
        "ha_build_phase2", str(REPO_ROOT / "skills" / "ha-build" / "run.py")
    )
    spec = importlib.util.spec_from_loader("ha_build_phase2", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_build_phase2"] = mod
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ha_build() -> ModuleType:
    return _load_ha_build()


def _plan(step: str) -> SimpleNamespace:
    return SimpleNamespace(
        pipeline=SimpleNamespace(
            current_step=step,
            completed_steps=("ha-design", "ha-plan"),
            skipped_steps=(),
            steps=("init", "designed", "planned", "building", "built", "verified", "reviewed", "shipped"),
            gstack_mode="manual",
        )
    )


def test_enter_build_delegates_to_reenter_or_assert(ha_build, monkeypatch) -> None:
    """_enter_build_state 는 공유 유틸 reenter_or_assert 에 올바른 파라미터로 위임한다.

    재진입/회귀/차단의 실제 동작은 test_reenter_or_assert.py 에서 직접 검증.
    여기서는 ha-build 가 prerequisite=planned, working=building 으로 배선했는지만 본다.
    """
    captured: dict = {}

    def _fake(plan, plan_path, *, prerequisite_state, working_state, skill_name):
        captured.update(
            prerequisite_state=prerequisite_state,
            working_state=working_state,
            skill_name=skill_name,
        )
        return False

    monkeypatch.setattr(ha_build, "reenter_or_assert", _fake)
    ha_build._enter_build_state(_plan("reviewed"), Path("x"))

    assert captured == {
        "prerequisite_state": "planned",
        "working_state": "building",
        "skill_name": "/ha-build",
    }, f"ha-build 의 빌드 상태 배선 오류: {captured}"
