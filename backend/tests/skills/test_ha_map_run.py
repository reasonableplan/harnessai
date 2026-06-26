"""ha-map/run.py 단위 테스트.

대상: skills/ha-map/run.py
전략: tmp_path 기반 + subprocess monkeypatch — mmdc 실설치 불요.
회귀 커버:
- 결함1: mmdc timeout(TimeoutExpired) 이 렌더 루프를 죽이지 않고 ok:false 로 보고
- 결함2: ```mermaid 코드펜스가 CRLF 줄끝이어도 블록 추출 (Windows)
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HA_MAP_RUN = REPO_ROOT / "skills" / "ha-map" / "run.py"


def _load_ha_map() -> ModuleType:
    loader = SourceFileLoader("ha_map_run", str(HA_MAP_RUN))
    spec = importlib.util.spec_from_loader("ha_map_run", loader)
    assert spec is not None, f"spec load failed: {HA_MAP_RUN}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_map_run"] = mod
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ha_map() -> ModuleType:
    return _load_ha_map()


# ── 결함2: CRLF mermaid 펜스 추출 ──────────────────────────────────────────


def test_extract_mermaid_lf(ha_map) -> None:
    """LF 줄끝의 ```mermaid 블록을 추출."""
    md = "intro\n```mermaid\nflowchart TD\nA-->B\n```\noutro\n"
    blocks = ha_map._extract_mermaid_blocks(md)
    assert len(blocks) == 1
    assert "flowchart TD" in blocks[0]


def test_extract_mermaid_crlf(ha_map) -> None:
    """CRLF(Windows) 줄끝이어도 블록을 추출 — 결함2 회귀.

    구 정규식 `mermaid\\n` 은 `mermaid\\r\\n` 과 매칭 실패해 0개 → silent no-render.
    """
    md = "intro\r\n```mermaid\r\nflowchart TD\r\nA-->B\r\n```\r\noutro\r\n"
    blocks = ha_map._extract_mermaid_blocks(md)
    assert len(blocks) == 1, "CRLF mermaid 펜스 추출 실패 (결함2 회귀)"
    assert "flowchart TD" in blocks[0]


def test_extract_ignores_non_mermaid_fence(ha_map) -> None:
    """```python 등 다른 코드펜스는 무시."""
    md = "```python\nprint(1)\n```\n```mermaid\ngraph LR\n```\n"
    blocks = ha_map._extract_mermaid_blocks(md)
    assert len(blocks) == 1
    assert "graph LR" in blocks[0]


# ── 결함1: mmdc timeout 이 렌더 루프를 죽이지 않음 ──────────────────────────


def test_render_one_timeout_returns_false_not_raise(
    ha_map, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """mmdc 가 timeout 초과로 TimeoutExpired 를 던져도 ok:false 반환, 예외 전파 X — 결함1 회귀."""

    def fake_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="mmdc", timeout=180)

    monkeypatch.setattr(ha_map.subprocess, "run", fake_run)

    result = ha_map._render_one("mmdc", tmp_path / "x.mmd", tmp_path / "x.png")
    assert result["ok"] is False
    assert result["error"]  # 비어있지 않은 에러 메시지


def test_render_one_both_launch_fail_returns_false(
    ha_map, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """list 실행 OSError → shell 재시도도 OSError 면 크래시 없이 ok:false."""

    def fake_run(*_args, **_kwargs):
        raise OSError("launch failed")

    monkeypatch.setattr(ha_map.subprocess, "run", fake_run)

    result = ha_map._render_one("mmdc", tmp_path / "x.mmd", tmp_path / "x.png")
    assert result["ok"] is False


# ── skeleton 탐색 ──────────────────────────────────────────────────────────


def test_find_skeleton_direct(ha_map, tmp_path: Path) -> None:
    """root/docs/skeleton.md 를 직접 찾는다."""
    (tmp_path / "docs").mkdir()
    sk = tmp_path / "docs" / "skeleton.md"
    sk.write_text("# skeleton\n", encoding="utf-8")
    assert ha_map._find_skeleton(tmp_path) == sk


def test_find_skeleton_none_when_absent(ha_map, tmp_path: Path) -> None:
    """skeleton 없으면 None."""
    assert ha_map._find_skeleton(tmp_path) is None


def test_find_skeleton_skips_node_modules(ha_map, tmp_path: Path) -> None:
    """node_modules 내부 skeleton 은 무시 (None)."""
    nested = tmp_path / "node_modules" / "pkg" / "docs"
    nested.mkdir(parents=True)
    (nested / "skeleton.md").write_text("# noise\n", encoding="utf-8")
    assert ha_map._find_skeleton(tmp_path) is None


# ── 결함#2: tmp 쓰기 실패가 렌더 루프를 죽이지 않음 ──────────────────────────


def test_cmd_render_survives_tmp_write_failure(
    ha_map, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """렌더 루프 내 tmp.write_text 가 OSError 면 ok:false 기록 후 계속 — 크래시 X."""
    md = tmp_path / "architecture.md"
    md.write_text("```mermaid\nflowchart TD\nA-->B\n```\n", encoding="utf-8")

    monkeypatch.setattr(ha_map.shutil, "which", lambda _name: "mmdc")  # mmdc 있는 척
    monkeypatch.setattr(ha_map, "_render_one", lambda *_a, **_k: {"ok": True})

    def boom(self, *_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(ha_map.Path, "write_text", boom)

    class _Args:
        architecture_md = str(md)

    assert ha_map.cmd_render(_Args()) == 0  # 크래시 없이 정상 종료
