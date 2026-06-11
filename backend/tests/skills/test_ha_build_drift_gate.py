"""ha-build skeleton drift 게이트 + skipped 보고 회귀 테스트.

F2 (architecture review): skeleton.md 가 freeze 이후 외부 수정되면 prepare 가
BLOCK — --accept-skeleton-drift 로만 우회. legacy plan (hash 없음) 은 skip.
F5: built 전이 시 skipped 태스크 목록을 출력에 노출.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_ha_build() -> ModuleType:
    loader = SourceFileLoader(
        "ha_build_run_drift", str(REPO_ROOT / "skills" / "ha-build" / "run.py")
    )
    spec = importlib.util.spec_from_loader("ha_build_run_drift", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_build_run_drift"] = mod
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ha_build() -> ModuleType:
    return _load_ha_build()


def _make_plan(skeleton_hash: str | None):
    return SimpleNamespace(
        pipeline=SimpleNamespace(
            current_step="planned",
            completed_steps=(),
            skipped_steps=(),
            steps=("planned", "building", "built"),
            gstack_mode="manual",
        ),
        profiles=[SimpleNamespace(id="fastapi", path=".")],
        skeleton_hash=skeleton_hash,
        frozen_status="frozen",
    )


def _prepare_args(accept_drift: bool = False):
    return SimpleNamespace(
        task="T-001",
        skip_frozen_gate=False,
        accept_skeleton_drift=accept_drift,
    )


def _patch_prepare(ha_build, monkeypatch, plan, tmp_path: Path) -> None:
    plan_path = tmp_path / "harness-plan.md"
    plan_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(ha_build, "load_plan", lambda: (plan, plan_path, tmp_path))
    monkeypatch.setattr(ha_build, "assert_state", lambda *a, **kw: None)


# ── skeleton drift 게이트 ────────────────────────────────────────────


def test_prepare_blocks_on_skeleton_hash_mismatch(ha_build, tmp_path, monkeypatch, capsys) -> None:
    """freeze 이후 외부 수정 (hash mismatch) → prepare BLOCK."""
    (tmp_path / "skeleton.md").write_text("## 1. 개요\n수정된 내용\n", encoding="utf-8")
    plan = _make_plan(skeleton_hash="deadbeef" * 8)  # 실제 hash 와 불일치
    _patch_prepare(ha_build, monkeypatch, plan, tmp_path)

    rc = ha_build.cmd_prepare(_prepare_args())

    assert rc == 1
    cap = capsys.readouterr()
    assert "[BLOCK]" in (cap.out + cap.err)
    assert "hash mismatch" in (cap.out + cap.err)


def test_prepare_proceeds_with_accept_flag(ha_build, tmp_path, monkeypatch, capsys) -> None:
    """--accept-skeleton-drift → WARN 만 출력하고 게이트 통과."""
    (tmp_path / "skeleton.md").write_text("## 1. 개요\n수정된 내용\n", encoding="utf-8")
    plan = _make_plan(skeleton_hash="deadbeef" * 8)
    _patch_prepare(ha_build, monkeypatch, plan, tmp_path)

    # tasks.md 부재로 게이트 이후 단계에서 실패하는 것은 무방 — 게이트 통과만 검증.
    rc = ha_build.cmd_prepare(_prepare_args(accept_drift=True))

    cap = capsys.readouterr()
    combined = cap.out + cap.err
    assert "[BLOCK]" not in combined
    assert "[WARN]" in combined and "--accept-skeleton-drift" in combined
    assert rc == 1  # tasks.md 없음 — 게이트와 무관한 후속 실패
    assert "tasks.md 없음" in combined


def test_prepare_skips_gate_for_legacy_plan(ha_build, tmp_path, monkeypatch, capsys) -> None:
    """legacy plan (skeleton_hash 없음) → 비교 불가, 게이트 skip."""
    (tmp_path / "skeleton.md").write_text("## 1. 개요\n내용\n", encoding="utf-8")
    plan = _make_plan(skeleton_hash=None)
    _patch_prepare(ha_build, monkeypatch, plan, tmp_path)

    rc = ha_build.cmd_prepare(_prepare_args())

    cap = capsys.readouterr()
    assert "hash mismatch" not in (cap.out + cap.err)
    assert rc == 1  # tasks.md 없음 — 게이트와 무관한 후속 실패


# ── built 전이 시 skipped 보고 ───────────────────────────────────────


_TASKS_TABLE_HEADER = (
    "| ID    | Agent         | Depends On | Description | Status     |\n"
    "|-------|---------------|------------|-------------|------------|\n"
)


def test_built_transition_reports_skipped_tasks(ha_build, tmp_path, monkeypatch, capsys) -> None:
    """built 전이 시 skipped 태스크 목록이 경고 + 출력 JSON 에 노출된다."""
    plan = _make_plan(skeleton_hash=None)
    plan.pipeline.current_step = "building"

    tasks_text = _TASKS_TABLE_HEADER + (
        "| T-001 | backend_coder | -          | desc        | 대기       |\n"
        "| T-002 | backend_coder | -          | desc        | skipped    |\n"
    )
    tasks_path = tmp_path / "tasks.md"
    tasks_path.write_text(tasks_text, encoding="utf-8")
    plan_path = tmp_path / "harness-plan.md"
    plan_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(ha_build, "load_plan", lambda: (plan, plan_path, tmp_path))
    monkeypatch.setattr(ha_build, "save_plan", lambda p, pp: None)
    monkeypatch.setattr(ha_build, "validate_task_id", lambda tid: None)
    monkeypatch.setattr(
        ha_build,
        "transition",
        lambda p, target, completed_step=None: setattr(p.pipeline, "current_step", target),
    )

    args = SimpleNamespace(
        task="T-001",
        status="done",
        reason="",
        skip_toolchain=True,
        skip_security=True,
        skip_frozen_gate=False,
    )
    rc = ha_build.cmd_complete(args)

    assert rc == 0
    cap = capsys.readouterr()
    combined = cap.out + cap.err
    assert "skipped 1개 포함: T-002" in combined
    output = json.loads(cap.out)
    assert output["skipped_tasks"] == ["T-002"]
    assert output["all_tasks_resolved"] is True
