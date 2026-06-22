"""reenter_or_assert (재진입 유틸 일원화, 축A 패턴1) 단위 테스트.

forward-only 상태머신이 막던 "이전 phase 재실행"(re-plan/추가 빌드/재설계)을 1급
동작으로: prerequisite 미만은 차단, working 이하는 그대로, working 초과는 working 으로
regress(+save) 하여 downstream 게이트 재통과. #2/#9 ad-hoc 수정의 공통 모델.
"""

from __future__ import annotations

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
UTILS_PY = REPO_ROOT / "skills" / "_ha_shared" / "utils.py"


def _load_utils() -> ModuleType:
    loader = SourceFileLoader("ha_utils_reenter", str(UTILS_PY))
    spec = importlib.util.spec_from_loader("ha_utils_reenter", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_utils_reenter"] = mod
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def utils() -> ModuleType:
    return _load_utils()


def _plan(step: str) -> SimpleNamespace:
    return SimpleNamespace(
        pipeline=SimpleNamespace(
            current_step=step,
            completed_steps=(),
            skipped_steps=(),
            steps=(
                "init",
                "designed",
                "planned",
                "building",
                "built",
                "verified",
                "reviewed",
                "shipped",
            ),
            gstack_mode="manual",
        )
    )


def test_blocks_when_before_prerequisite(utils) -> None:
    """current < prerequisite → exit 2 (선행 phase 미완료)."""
    plan = _plan("init")
    with pytest.raises(SystemExit) as exc:
        utils.reenter_or_assert(
            plan,
            Path("x"),
            prerequisite_state="planned",
            working_state="building",
            skill_name="/ha-build",
        )
    assert exc.value.code == 2


def test_passes_at_prerequisite_no_regress(utils, monkeypatch) -> None:
    """prerequisite == current (working 이하) → 그대로, regress/save 없음, False."""
    plan = _plan("planned")
    saved = {"called": False}
    monkeypatch.setattr(utils, "save_plan", lambda p, pp: saved.update(called=True))
    out = utils.reenter_or_assert(
        plan,
        Path("x"),
        prerequisite_state="planned",
        working_state="building",
        skill_name="/ha-build",
    )
    assert out is False
    assert plan.pipeline.current_step == "planned"
    assert saved["called"] is False


def test_passes_at_working_no_regress(utils, monkeypatch) -> None:
    """current == working → 그대로, regress 없음."""
    plan = _plan("building")
    monkeypatch.setattr(utils, "save_plan", lambda p, pp: None)
    out = utils.reenter_or_assert(
        plan,
        Path("x"),
        prerequisite_state="planned",
        working_state="building",
        skill_name="/ha-build",
    )
    assert out is False
    assert plan.pipeline.current_step == "building"


def test_regresses_when_after_working(utils, monkeypatch) -> None:
    """current > working → working 으로 regress + save, True 반환 (재진입)."""
    plan = _plan("reviewed")
    saved = {"step": None}
    monkeypatch.setattr(
        utils, "save_plan", lambda p, pp: saved.update(step=p.pipeline.current_step)
    )
    out = utils.reenter_or_assert(
        plan,
        Path("x"),
        prerequisite_state="planned",
        working_state="building",
        skill_name="/ha-build",
    )
    assert out is True
    assert plan.pipeline.current_step == "building"
    assert saved["step"] == "building"


def test_ha_plan_replan_from_building_regresses_to_planned(utils, monkeypatch) -> None:
    """ha-plan --replan 시나리오: building 에서 planned 로 재진입."""
    plan = _plan("building")
    monkeypatch.setattr(utils, "save_plan", lambda p, pp: None)
    out = utils.reenter_or_assert(
        plan,
        Path("x"),
        prerequisite_state="designed",
        working_state="planned",
        skill_name="/ha-plan",
    )
    assert out is True
    assert plan.pipeline.current_step == "planned"
