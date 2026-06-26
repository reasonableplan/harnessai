"""_ha_shared/utils.py::project_root 단위 테스트.

회귀 커버: git rev-parse 가 timeout/미설치여도 cwd 로 폴백 (크래시 X).
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
UTILS = REPO_ROOT / "skills" / "_ha_shared" / "utils.py"


def _load() -> ModuleType:
    loader = SourceFileLoader("ha_shared_utils_project_root", str(UTILS))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None, f"spec load failed: {UTILS}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = mod
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def utils() -> ModuleType:
    return _load()


def test_project_root_falls_back_to_cwd_on_timeout(utils, monkeypatch: pytest.MonkeyPatch) -> None:
    """git rev-parse 가 TimeoutExpired 여도 cwd 폴백 — timeout 추가가 새 미처리 경로를 안 만듦."""

    def fake_run(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="git", timeout=10)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert utils.project_root() == Path.cwd().resolve()


def test_project_root_falls_back_when_git_missing(utils, monkeypatch: pytest.MonkeyPatch) -> None:
    """git 미설치(FileNotFoundError) 면 cwd 폴백."""

    def fake_run(*_a, **_k):
        raise FileNotFoundError("git not found")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert utils.project_root() == Path.cwd().resolve()
