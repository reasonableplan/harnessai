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


def test_enter_build_regresses_from_reviewed(ha_build, monkeypatch) -> None:
    """reviewed → building 회귀 + 저장."""
    plan = _plan("reviewed")
    saved: dict = {}
    monkeypatch.setattr(ha_build, "save_plan", lambda p, pp: saved.update(step=p.pipeline.current_step))

    ha_build._enter_build_state(plan, Path("x"))

    assert plan.pipeline.current_step == "building", "reviewed 에서 building 회귀 실패 (#9 재발)"
    assert saved.get("step") == "building", "회귀 후 save_plan 미호출"


def test_enter_build_regresses_from_verified(ha_build, monkeypatch) -> None:
    """verified 도 동일하게 building 회귀."""
    plan = _plan("verified")
    monkeypatch.setattr(ha_build, "save_plan", lambda p, pp: None)
    ha_build._enter_build_state(plan, Path("x"))
    assert plan.pipeline.current_step == "building"


def test_enter_build_noop_from_planned(ha_build, monkeypatch) -> None:
    """planned 는 정상 빌드 상태 — 회귀/저장 없음."""
    plan = _plan("planned")
    called = {"save": False}
    monkeypatch.setattr(ha_build, "save_plan", lambda p, pp: called.update(save=True))
    ha_build._enter_build_state(plan, Path("x"))
    assert plan.pipeline.current_step == "planned"
    assert called["save"] is False, "planned 에서 불필요한 회귀/저장 발생"


def test_enter_build_blocks_from_designed(ha_build) -> None:
    """designed 는 빌드 불가 상태 → assert_state 가 exit 2."""
    plan = _plan("designed")
    with pytest.raises(SystemExit) as exc:
        ha_build._enter_build_state(plan, Path("x"))
    assert exc.value.code == 2
