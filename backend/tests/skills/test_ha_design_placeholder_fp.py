"""FP #6 회귀 테스트: ha-design commit placeholder 검사가 TS 제네릭 오집계.

실전 결함 (Mendline dogfood, /ha-design commit):
- skeleton 본문의 `IpcResult<T> = { ok: true; data: T } | ...` (코드 블록 제네릭)
  의 <T> 2건이 placeholders_remaining 으로 집계 → 진짜 미해결 placeholder 가 묻힘.

Fix: _find_placeholders 가 TS 제네릭(<T>, <K, V>)을 제외. 실제 placeholder
(<DOMAIN>, <DB_URL>, _미작성_)는 유지.
"""

from __future__ import annotations

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HA_DESIGN_RUN = REPO_ROOT / "skills" / "ha-design" / "run.py"


@pytest.fixture(scope="module")
def ha_design() -> ModuleType:
    loader = SourceFileLoader("ha_design_placeholder_fp", str(HA_DESIGN_RUN))
    spec = importlib.util.spec_from_loader("ha_design_placeholder_fp", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_design_placeholder_fp"] = mod
    loader.exec_module(mod)
    return mod


def test_generic_type_not_counted(ha_design: ModuleType) -> None:
    """코드 블록의 TS 제네릭 <T> 는 placeholder 로 집계되지 않음."""
    text = "type IpcResult<T> = { ok: true; data: T } | { ok: false };\n"
    assert ha_design._find_placeholders(text) == []


def test_multi_param_generic_not_counted(ha_design: ModuleType) -> None:
    """<K, V> 같은 다중 타입 파라미터도 제외."""
    text = "const m: Map<K, V> = new Map();\n"
    assert ha_design._find_placeholders(text) == []


def test_real_placeholders_still_counted(ha_design: ModuleType) -> None:
    """실제 placeholder(<DOMAIN>, <DB_URL>, _미작성_)는 유지 (TP 보존)."""
    text = "경로: <DOMAIN>/api\nDATABASE_URL=<DB_URL>\n상태: _미작성_\n"
    found = ha_design._find_placeholders(text)
    assert "<DOMAIN>" in found
    assert "<DB_URL>" in found
    assert "_미작성_" in found


def test_generic_and_real_mixed(ha_design: ModuleType) -> None:
    """제네릭과 실제 placeholder 가 섞이면 제네릭만 제외."""
    text = "Result<T> 를 <PROJECT_NAME> 에서 사용\n"
    found = ha_design._find_placeholders(text)
    assert "<T>" not in found
    assert "<PROJECT_NAME>" in found
