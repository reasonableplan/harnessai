"""ha-verify 런타임 기동 스모크 게이트 (issue #6) 회귀 테스트.

test/lint/type 통과가 "앱이 실제로 뜬다"를 보장하지 않는다. cli_entrypoint
프로파일은 toolchain.smoke 를 verify 단계에서 실제 invoke 해 import/기동/콘솔
인코딩(cp949 em-dash UnicodeEncodeError 등) 크래시를 잡아야 한다.

인코딩 크래시는 stdout 을 ascii 로 reconfigure 후 em-dash 를 출력해 cross-platform
으로 결정론적으로 재현한다 (실제 Windows cp949 와 동일한 UnicodeEncodeError).
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


def _load_ha_verify() -> ModuleType:
    loader = SourceFileLoader(
        "ha_verify_run_smoke", str(REPO_ROOT / "skills" / "ha-verify" / "run.py")
    )
    spec = importlib.util.spec_from_loader("ha_verify_run_smoke", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_verify_run_smoke"] = mod
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ha_verify() -> ModuleType:
    return _load_ha_verify()


def _profile(*, smoke: str | None, provides: tuple[str, ...] = ("cli_entrypoint",)):
    return SimpleNamespace(
        id="python-cli",
        toolchain=SimpleNamespace(
            install="uv sync",
            test="pytest",
            lint="ruff check src/",
            type="pyright src/",
            format="ruff format",
            smoke=smoke,
        ),
        components=[],
        provides_capabilities=provides,
    )


def _plan():
    return SimpleNamespace(
        pipeline=SimpleNamespace(
            current_step="built",
            completed_steps=(),
            skipped_steps=(),
            steps=("built", "verified"),
            gstack_mode="manual",
        ),
        profiles=[SimpleNamespace(path=".")],
        skeleton_hash="",
    )


def _patch(ha_verify, monkeypatch, plan, profiles, tmp_path: Path) -> None:
    plan_path = tmp_path / "docs" / "harness-plan.md"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(ha_verify, "load_plan", lambda: (plan, plan_path, tmp_path))
    monkeypatch.setattr(ha_verify, "assert_state", lambda *a, **k: None)
    monkeypatch.setattr(ha_verify, "get_active_profiles", lambda p, pr: profiles)
    monkeypatch.setattr(
        ha_verify,
        "_run_integrity_check",
        lambda project: {"passed": None, "skipped": True, "reason": "", "output": ""},
    )


def _run(ha_verify, capsys) -> tuple[int, dict, str]:
    rc = ha_verify.cmd_prepare(SimpleNamespace())
    cap = capsys.readouterr()
    out = json.loads(cap.out)
    return rc, out, cap.err


def test_smoke_passes_on_clean_cli(ha_verify, tmp_path, monkeypatch, capsys) -> None:
    """정상 기동 (exit 0) → smoke_check.passed True, smoke_failures 비어있음."""
    plan = _plan()
    prof = _profile(smoke='python -c "print(\'ok\')"')
    _patch(ha_verify, monkeypatch, plan, [prof], tmp_path)

    rc, out, _err = _run(ha_verify, capsys)

    assert rc == 0
    assert out["smoke_failures"] == []
    sc = out["profiles"][0]["smoke_check"]
    assert sc["ran"] is True and sc["passed"] is True, sc


def test_smoke_catches_encoding_crash(ha_verify, tmp_path, monkeypatch, capsys) -> None:
    """ascii stdout + em-dash 출력 → UnicodeEncodeError 크래시 → smoke 실패로 표면화.

    이게 #6 의 핵심 — test/lint/type(CliRunner utf-8 버퍼)는 green 이지만 실제
    invoke 는 비-ASCII 출력에서 죽는다. verify 스모크가 이를 잡아야 한다.
    """
    plan = _plan()
    crash_cmd = (
        "python -c \"import sys; sys.stdout.reconfigure(encoding='ascii'); "
        "print('error \\u2014 detail')\""
    )
    prof = _profile(smoke=crash_cmd)
    _patch(ha_verify, monkeypatch, plan, [prof], tmp_path)

    rc, out, err = _run(ha_verify, capsys)

    assert rc == 0  # prepare 자체는 advisory — 결과는 출력으로 보고
    assert out["smoke_failures"] == ["python-cli"], out
    sc = out["profiles"][0]["smoke_check"]
    assert sc["ran"] is True and sc["passed"] is False, sc
    assert "[FAIL]" in err and "런타임 스모크 실패" in err


def test_smoke_warns_when_missing_for_cli(ha_verify, tmp_path, monkeypatch, capsys) -> None:
    """cli_entrypoint 인데 smoke 미설정 → WARN (런타임 게이트 부재 경고)."""
    plan = _plan()
    prof = _profile(smoke=None)
    _patch(ha_verify, monkeypatch, plan, [prof], tmp_path)

    rc, out, err = _run(ha_verify, capsys)

    assert rc == 0
    assert out["smoke_failures"] == []
    assert out["profiles"][0]["smoke_check"]["ran"] is False
    assert "[WARN]" in err and "런타임 스모크 미설정" in err


def test_smoke_skipped_for_non_cli_profile(ha_verify, tmp_path, monkeypatch, capsys) -> None:
    """non-cli (서버/UI) 프로파일은 verify 스모크 대상 아님 — /ha-smoke 위임, WARN 없음."""
    plan = _plan()
    prof = _profile(smoke=None, provides=("http_server",))
    _patch(ha_verify, monkeypatch, plan, [prof], tmp_path)

    rc, out, err = _run(ha_verify, capsys)

    assert rc == 0
    assert out["smoke_failures"] == []
    sc = out["profiles"][0]["smoke_check"]
    assert sc["ran"] is False and "non-cli" in sc["reason"]
    assert "런타임 스모크 미설정" not in err
