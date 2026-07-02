"""harness CLI + ha-review 스킬 테스트용 헬퍼.

CLI 스크립트는 import 경로가 없어 importlib.util 로 직접 로드한다.
레포 루트(`<repo>/harness/`, `<repo>/skills/`) 를 소스로 삼아 `~/.claude/` 환경과 독립.
"""

from __future__ import annotations

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HARNESS_BIN = REPO_ROOT / "harness" / "bin" / "harness"
HA_REVIEW_RUN = REPO_ROOT / "skills" / "ha-review" / "run.py"


def _load_module(name: str, path: Path) -> ModuleType:
    """Extension 무관 파이썬 파일을 모듈로 로드 (harness bin 은 .py 없음)."""
    loader = SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec is not None, f"spec load failed: {path}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def harness_module() -> ModuleType:
    """`harness` CLI 스크립트를 모듈로 로드."""
    return _load_module("harness_bin", HARNESS_BIN)


@pytest.fixture(scope="session")
def ha_review_module() -> ModuleType:
    """`ha-review/run.py` 를 모듈로 로드."""
    return _load_module("ha_review_run", HA_REVIEW_RUN)


@pytest.fixture(scope="session")
def ha_run_module() -> ModuleType:
    """`ha-run/run.py` 를 모듈로 로드."""
    return _load_module("ha_run_run", REPO_ROOT / "skills" / "ha-run" / "run.py")
