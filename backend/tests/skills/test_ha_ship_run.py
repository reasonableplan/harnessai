"""ha-ship 회귀 테스트 — reviewed → shipped 라스트마일 마킹.

상태머신에 shipped 가 정의돼 있었지만 전이시키는 스킬이 없어 도달 불가였다
(2026-06-10 시스템 리뷰). /ha-ship mark 가 그 전이의 유일한 운전자.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HA_SHIP_RUN = REPO_ROOT / "skills" / "ha-ship" / "run.py"


@pytest.fixture(scope="module")
def ha_ship() -> ModuleType:
    loader = SourceFileLoader("ha_ship_run", str(HA_SHIP_RUN))
    spec = importlib.util.spec_from_loader("ha_ship_run", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_ship_run"] = mod
    loader.exec_module(mod)
    return mod


def test_mark_transitions_reviewed_to_shipped(ha_ship, capsys) -> None:
    plan = SimpleNamespace(pipeline=SimpleNamespace(current_step="reviewed"))
    transitions: list[tuple] = []
    saved: list = []

    def _fake_transition(p, target, completed_step=None):
        transitions.append((target, completed_step))
        p.pipeline.current_step = target

    with (
        patch.object(
            ha_ship, "load_plan",
            return_value=(plan, Path("/fake/harness-plan.md"), Path("/fake")),
        ),
        patch.object(ha_ship, "assert_state") as mock_assert,
        patch.object(ha_ship, "transition", side_effect=_fake_transition),
        patch.object(ha_ship, "save_plan", side_effect=lambda p, pp: saved.append(p)),
    ):
        rc = ha_ship.cmd_mark(SimpleNamespace())

    assert rc == 0
    mock_assert.assert_called_once()
    assert mock_assert.call_args.args[1] == ["reviewed"]
    assert transitions == [("shipped", "ha-ship")]
    assert saved, "save_plan 미호출 — 전이가 영속화되지 않음"

    out = json.loads(capsys.readouterr().out)
    assert out["current_step"] == "shipped"
