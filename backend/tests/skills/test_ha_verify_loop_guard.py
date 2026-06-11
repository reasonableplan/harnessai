"""ha-verify 루프 탈출 가드 회귀 테스트 (architecture review ④).

"동일 T-ID 2회+ FAIL → /ha-redesign 검토" 가 가드레일 *문장* 으로만 존재해
build↔verify 무한 왕복이 가능했다. 결정론 강제: 동일 태스크가 3회째 FAIL 로
보고되면 record 가 --force-continue 없이는 exit 1.
"""

from __future__ import annotations

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HA_VERIFY_RUN = REPO_ROOT / "skills" / "ha-verify" / "run.py"


@pytest.fixture(scope="module")
def ha_verify() -> ModuleType:
    loader = SourceFileLoader("ha_verify_loop_guard", str(HA_VERIFY_RUN))
    spec = importlib.util.spec_from_loader("ha_verify_loop_guard", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_verify_loop_guard"] = mod
    loader.exec_module(mod)
    return mod


def _failed_entry(rework_csv: str) -> SimpleNamespace:
    return SimpleNamespace(
        step="ha-verify", passed=False, summary=f"pytest fail [rework: {rework_csv}]"
    )


def _plan(prior_fail_rework: list[str]):
    return SimpleNamespace(
        pipeline=SimpleNamespace(current_step="built"),
        verify_history=[_failed_entry(csv) for csv in prior_fail_rework],
    )


def _args(rework: str, force: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        passed="false",
        summary="pytest 1 failed",
        rework_tasks=rework,
        no_rework=False,
        force_continue=force,
    )


def _run_record(ha_verify, plan, args) -> int:
    with (
        patch.object(
            ha_verify,
            "load_plan",
            return_value=(plan, Path("/fake/harness-plan.md"), Path("/fake")),
        ),
        patch.object(ha_verify, "assert_state"),
        patch.object(ha_verify, "record_verify"),
        patch.object(ha_verify, "regress"),
        patch.object(ha_verify, "save_plan"),
    ):
        return ha_verify.cmd_record(args)


def test_third_fail_blocked(ha_verify) -> None:
    """같은 T-ID 가 이미 2회 FAIL (CSV 혼재 포함) → 3회째 record 는 exit 1."""
    plan = _plan(["T-003", "T-003, T-001"])
    rc = _run_record(ha_verify, plan, _args("T-003"))
    assert rc == 1


def test_third_fail_block_message_mentions_redesign(ha_verify, capsys) -> None:
    plan = _plan(["T-003", "T-003"])
    rc = _run_record(ha_verify, plan, _args("T-003"))
    cap = capsys.readouterr()
    combined = cap.out + cap.err
    assert rc == 1
    assert "[BLOCK]" in combined
    assert "ha-redesign" in combined
    assert "--force-continue" in combined


def test_third_fail_force_continue_proceeds(ha_verify, capsys) -> None:
    """--force-continue 명시 시 가드 통과 (의도적 재시도)."""
    plan = _plan(["T-003", "T-003"])
    rc = _run_record(ha_verify, plan, _args("T-003", force=True))
    assert rc == 0


def test_second_fail_allowed(ha_verify) -> None:
    """2회째 FAIL 까지는 정상 기록 (가드는 3회째부터)."""
    plan = _plan(["T-003"])
    rc = _run_record(ha_verify, plan, _args("T-003"))
    assert rc == 0


def test_unrelated_prior_fails_do_not_block(ha_verify) -> None:
    """다른 T-ID 의 과거 FAIL 은 카운트 안 됨."""
    plan = _plan(["T-001", "T-002"])
    rc = _run_record(ha_verify, plan, _args("T-003"))
    assert rc == 0


# ── 가짜 FAIL 방지: 테스트 디렉토리 부재 사전 경고 ──────────────────


def test_missing_test_dir_warns_with_parent_hint(ha_verify, tmp_path) -> None:
    """cwd 에 tests/ 가 없는데 상위(루트)에 있으면 — path 오매칭 경고."""
    (tmp_path / "tests").mkdir()
    cwd = tmp_path / "backend"
    cwd.mkdir()
    w = ha_verify._missing_test_dir_warning(cwd, "uv run pytest tests/ --rootdir=.")
    assert w is not None
    assert "가짜 FAIL" in w
    assert "profile path" in w or "상위" in w


def test_existing_test_dir_no_warning(ha_verify, tmp_path) -> None:
    (tmp_path / "tests").mkdir()
    assert ha_verify._missing_test_dir_warning(tmp_path, "uv run pytest tests/ --rootdir=.") is None


def test_no_test_path_in_command_no_warning(ha_verify, tmp_path) -> None:
    """명령에 디렉토리 표기가 없으면 (jest 등) 판단 보류 — 경고 없음."""
    assert ha_verify._missing_test_dir_warning(tmp_path, "bun test") is None
    assert ha_verify._missing_test_dir_warning(tmp_path, None) is None
