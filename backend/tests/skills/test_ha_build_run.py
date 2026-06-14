"""v0.10.0 HITL gate — /ha-build prepare/complete frozen_status 게이트 테스트.

대상: skills/ha-build/run.py::cmd_prepare, cmd_complete
전략: load_plan / save_plan / validate_task_id / transition monkeypatch.
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
        "ha_build_run_gate", str(REPO_ROOT / "skills" / "ha-build" / "run.py")
    )
    spec = importlib.util.spec_from_loader("ha_build_run_gate", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_build_run_gate"] = mod
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ha_build() -> ModuleType:
    return _load_ha_build()


_TASKS_TABLE = (
    "| ID    | Agent         | Depends On | Description | Status     |\n"
    "|-------|---------------|------------|-------------|------------|\n"
    "| T-001 | backend_coder | -          | desc        | done       |\n"
)

# 이슈 #16 회귀용 — T-001 이 '대기' 상태. 1차 complete 가 :<10 패딩으로 done 을
# 쓰면, 2차 complete 는 re.sub 결과가 원본과 동일(new_text == text)해진다.
_TASKS_TABLE_PENDING = (
    "| ID    | Agent         | Depends On | Description | Status     |\n"
    "|-------|---------------|------------|-------------|------------|\n"
    "| T-001 | backend_coder | -          | desc        | 대기        |\n"
)


def _make_plan(frozen_status: str = "drafting") -> SimpleNamespace:
    return SimpleNamespace(
        pipeline=SimpleNamespace(
            current_step="planned",
            completed_steps=(),
            skipped_steps=(),
            steps=("planned", "building", "built"),
            gstack_mode="manual",
        ),
        profiles=[SimpleNamespace(id="fastapi", path=".")],
        skeleton_hash=None,
        frozen_status=frozen_status,
    )


def _patch_common(ha_build, monkeypatch, plan, tmp_path: Path, tasks_text: str):
    tasks_path = tmp_path / "tasks.md"
    tasks_path.write_text(tasks_text, encoding="utf-8")
    plan_path = tmp_path / "harness-plan.md"
    plan_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(ha_build, "load_plan", lambda: (plan, plan_path, tmp_path))
    monkeypatch.setattr(ha_build, "save_plan", lambda p, pp: None)
    monkeypatch.setattr(ha_build, "validate_task_id", lambda tid: None)
    monkeypatch.setattr(ha_build, "transition", lambda *a, **kw: None)
    monkeypatch.setattr(ha_build, "get_active_profiles", lambda plan, project: [])
    monkeypatch.setattr(ha_build, "_run_toolchain_gate", lambda *a, **kw: [])
    monkeypatch.setattr(ha_build, "_run_security_gate", lambda *a, **kw: [])

    return tasks_path


def _prepare_args(task: str = "T-001", skip_frozen_gate: bool = False) -> SimpleNamespace:
    return SimpleNamespace(task=task, skip_frozen_gate=skip_frozen_gate)


def _complete_args(
    task: str = "T-001",
    status: str = "done",
    reason: str = "",
    skip_toolchain: bool = True,
    skip_security: bool = True,
    skip_frozen_gate: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        task=task,
        status=status,
        reason=reason,
        skip_toolchain=skip_toolchain,
        skip_security=skip_security,
        skip_frozen_gate=skip_frozen_gate,
    )


# ---------------------------------------------------------------------------
# prepare 게이트 테스트
# ---------------------------------------------------------------------------


def test_prepare_blocks_when_drafting(ha_build, tmp_path, monkeypatch, capsys) -> None:
    """frozen_status=drafting 인 plan 으로 prepare 호출 → exit 1 + BLOCK 메시지."""
    plan = _make_plan("drafting")
    _patch_common(ha_build, monkeypatch, plan, tmp_path, _TASKS_TABLE)

    rc = ha_build.cmd_prepare(_prepare_args("T-001", skip_frozen_gate=False))

    assert rc == 1
    err = capsys.readouterr().err
    assert "BLOCK" in err
    assert "frozen_status" in err


def test_prepare_passes_when_frozen(ha_build, tmp_path, monkeypatch, capsys) -> None:
    """frozen_status=frozen 인 plan 으로 prepare → 정상 진행 (tasks.md 없으면 FAIL, exit 1)."""
    plan = _make_plan("frozen")
    _patch_common(ha_build, monkeypatch, plan, tmp_path, _TASKS_TABLE)

    # tasks.md 가 있고 T-001 이 done 이라 depends_on 없음 → prepare JSON 출력
    rc = ha_build.cmd_prepare(_prepare_args("T-001", skip_frozen_gate=False))

    # frozen 게이트는 통과 — 이후 로직(태스크 파싱/depends_on) 에서 결과 결정
    # T-001 이 tasks.md 에 있고 depends_on 없으므로 rc=0 기대
    assert rc == 0


def test_prepare_skip_frozen_gate(ha_build, tmp_path, monkeypatch, capsys) -> None:
    """--skip-frozen-gate 박으면 drafting 이어도 통과 (마이그레이션용)."""
    plan = _make_plan("drafting")
    _patch_common(ha_build, monkeypatch, plan, tmp_path, _TASKS_TABLE)

    rc = ha_build.cmd_prepare(_prepare_args("T-001", skip_frozen_gate=True))

    # 게이트 우회 → T-001 처리 시도 (rc=0)
    assert rc == 0
    err = capsys.readouterr().err
    assert "BLOCK" not in err


# ---------------------------------------------------------------------------
# complete 게이트 테스트
# ---------------------------------------------------------------------------


def test_complete_blocks_when_drafting(ha_build, tmp_path, monkeypatch, capsys) -> None:
    """frozen_status=drafting 인 plan 으로 complete 호출 → exit 1 + BLOCK 메시지."""
    plan = _make_plan("drafting")
    _patch_common(ha_build, monkeypatch, plan, tmp_path, _TASKS_TABLE)

    rc = ha_build.cmd_complete(_complete_args("T-001", skip_frozen_gate=False))

    assert rc == 1
    err = capsys.readouterr().err
    assert "BLOCK" in err


def test_complete_passes_when_frozen(ha_build, tmp_path, monkeypatch) -> None:
    """frozen_status=frozen 인 plan 으로 complete → 게이트 통과, done 마킹."""
    plan = _make_plan("frozen")
    _patch_common(ha_build, monkeypatch, plan, tmp_path, _TASKS_TABLE)

    rc = ha_build.cmd_complete(_complete_args("T-001", status="done"))

    assert rc == 0


def test_complete_skip_frozen_gate(ha_build, tmp_path, monkeypatch, capsys) -> None:
    """--skip-frozen-gate 박으면 drafting 이어도 통과."""
    plan = _make_plan("drafting")
    _patch_common(ha_build, monkeypatch, plan, tmp_path, _TASKS_TABLE)

    rc = ha_build.cmd_complete(_complete_args("T-001", skip_frozen_gate=True))

    assert rc == 0
    err = capsys.readouterr().err
    assert "BLOCK" not in err


def test_complete_idempotent_when_already_done(ha_build, tmp_path, monkeypatch, capsys) -> None:
    """이미 done 인 행을 다시 complete → '행 못 찾음' 오진 없이 멱등 통과 (이슈 #16).

    run.py 자신이 쓴 `:<10` 패딩('done' + 6 spaces)이면 re.sub 결과가 원본과
    동일(new_text == text)해, 과거엔 '행을 찾지 못했습니다' + exit 1 로 오진했다.
    """
    plan = _make_plan("frozen")
    _patch_common(ha_build, monkeypatch, plan, tmp_path, _TASKS_TABLE_PENDING)

    # 1차: 대기 → done (run.py 가 :<10 패딩으로 기록)
    rc1 = ha_build.cmd_complete(_complete_args("T-001", status="done"))
    assert rc1 == 0, "1차 done 마킹 실패"
    capsys.readouterr()  # 버퍼 비우기

    # 2차: 이미 done (패딩 포맷 일치 → new_text == text) — 멱등 재실행
    rc2 = ha_build.cmd_complete(_complete_args("T-001", status="done"))

    assert rc2 == 0, "이미 done 인 행 재완료가 '행 못 찾음' 으로 거부됨 (이슈 #16)"
    err = capsys.readouterr().err
    assert "찾지 못했습니다" not in err, f"멱등 케이스를 행-부재로 오진: {err}"
    assert "idempotent" in err or "이미" in err, f"멱등 경로 미진입: {err}"
