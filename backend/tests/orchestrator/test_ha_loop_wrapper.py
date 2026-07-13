"""ha-loop: Ralph-style fresh-context outer loop for ha-run (opt-in).

2026-07-08 adoption: pipeline state lives entirely in harness-plan.md/tasks.md
(ha-run's "상태 캐싱 금지"), so each step can run in a fresh `claude -p` session
without losing progress — solving long-run context rot and the 30-loop cap.
The wrapper is a deterministic driver over `ha-run run.py next`:
auto steps → fresh claude invocation; HITL → stop (exit 2, interactive만 가능);
child gate failure → stop without auto-bypass; stall guard → stop.
"""

from __future__ import annotations

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HA_LOOP = REPO_ROOT / "harness" / "bin" / "ha-loop"


@pytest.fixture(scope="module")
def ha_loop() -> ModuleType:
    loader = SourceFileLoader("ha_loop_wrapper", str(HA_LOOP))
    spec = importlib.util.spec_from_loader("ha_loop_wrapper", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_loop_wrapper"] = mod
    loader.exec_module(mod)
    return mod


def _run(
    ha_loop: ModuleType, next_seq: list[dict], invoke_rc: int = 0, **kwargs
) -> tuple[int, MagicMock]:
    invoke = MagicMock(return_value=invoke_rc)
    with (
        patch.object(ha_loop, "read_next", side_effect=next_seq),
        patch.object(ha_loop, "invoke_claude", invoke),
        patch("builtins.print"),
    ):
        rc = ha_loop.run_loop(
            project=Path("."),
            max_loops=kwargs.get("max_loops", 50),
            claude_args=[],
            dry_run=kwargs.get("dry_run", False),
        )
    return rc, invoke


def test_done_exits_zero_without_invoking(ha_loop: ModuleType) -> None:
    rc, invoke = _run(ha_loop, [{"action": "done", "mode": "auto", "current_step": "shipped"}])
    assert rc == 0
    invoke.assert_not_called()


def test_hitl_stops_with_exit_2(ha_loop: ModuleType) -> None:
    """HITL 지점은 headless 로 처리 불가 — 정지 후 인터랙티브 안내."""
    rc, invoke = _run(
        ha_loop,
        [{"action": "design", "mode": "hitl", "current_step": "init", "reason": "인터뷰 필요"}],
    )
    assert rc == 2
    invoke.assert_not_called()


def test_auto_step_invokes_claude_then_done(ha_loop: ModuleType) -> None:
    rc, invoke = _run(
        ha_loop,
        [
            {
                "action": "verify",
                "mode": "auto",
                "skill": "ha-verify",
                "args": "",
                "current_step": "built",
            },
            {"action": "done", "mode": "auto", "current_step": "shipped"},
        ],
    )
    assert rc == 0
    invoke.assert_called_once()
    assert invoke.call_args.args[0] == "/ha-verify"


def test_auto_step_passes_skill_args(ha_loop: ModuleType) -> None:
    rc, invoke = _run(
        ha_loop,
        [
            {
                "action": "build",
                "mode": "auto",
                "skill": "ha-build",
                "args": "--resume",
                "current_step": "building",
            },
            {"action": "done", "mode": "auto", "current_step": "shipped"},
        ],
    )
    assert rc == 0
    assert invoke.call_args.args[0] == "/ha-build --resume"


def test_stall_guard_stops_after_3_identical(ha_loop: ModuleType) -> None:
    """같은 action + current_step 3연속 무전이 → 정지 (invoke 는 2회만)."""
    same = {
        "action": "verify",
        "mode": "auto",
        "skill": "ha-verify",
        "args": "",
        "current_step": "built",
    }
    rc, invoke = _run(ha_loop, [same, same, same])
    assert rc == 1
    assert invoke.call_count == 2


def test_child_failure_stops_without_bypass(ha_loop: ModuleType) -> None:
    """하위 claude 실행 실패 (게이트 BLOCK 등) → 우회 없이 즉시 정지."""
    rc, invoke = _run(
        ha_loop,
        [
            {
                "action": "verify",
                "mode": "auto",
                "skill": "ha-verify",
                "args": "",
                "current_step": "built",
            }
        ],
        invoke_rc=1,
    )
    assert rc == 1
    invoke.assert_called_once()


def test_max_loops_cap(ha_loop: ModuleType) -> None:
    """max_loops 초과 → exit 1 (상태는 파일에 있으므로 재실행으로 이어짐)."""
    a = {
        "action": "build",
        "mode": "auto",
        "skill": "ha-build",
        "args": "",
        "current_step": "building",
    }
    b = {
        "action": "verify",
        "mode": "auto",
        "skill": "ha-verify",
        "args": "",
        "current_step": "built",
    }
    rc, invoke = _run(ha_loop, [a, b], max_loops=2)
    assert rc == 1
    assert invoke.call_count == 2


def test_dry_run_previews_one_step(ha_loop: ModuleType) -> None:
    """dry-run 은 첫 auto 스텝 미리보기 후 종료 (claude 미실행은 invoke_claude 내부 책임)."""
    rc, invoke = _run(
        ha_loop,
        [
            {
                "action": "verify",
                "mode": "auto",
                "skill": "ha-verify",
                "args": "",
                "current_step": "built",
            }
        ],
        dry_run=True,
    )
    assert rc == 0
    invoke.assert_called_once()
    assert invoke.call_args.args[3] is True  # dry_run 전달
