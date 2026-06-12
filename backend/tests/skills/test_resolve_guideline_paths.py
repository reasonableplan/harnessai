"""Task 1: resolve_guideline_paths helper 단위 테스트.

대상: `skills/_ha_shared/utils.py::resolve_guideline_paths`
전략: 실제 `harness/templates/guidelines/` 디렉토리를 사용 (mock 없음).
"""

from __future__ import annotations

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
UTILS_PATH = REPO_ROOT / "skills" / "_ha_shared" / "utils.py"


def _load_utils() -> ModuleType:
    loader = SourceFileLoader("ha_shared_utils", str(UTILS_PATH))
    spec = importlib.util.spec_from_loader("ha_shared_utils", loader)
    assert spec is not None, f"spec load failed: {UTILS_PATH}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_shared_utils"] = mod
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def utils() -> ModuleType:
    return _load_utils()


# ── 실제 guidelines 디렉토리 존재 전제 ─────────────────────────────────


def test_flutter_returns_four_sorted_paths(utils) -> None:
    """flutter 프로파일 → 4개 .md 파일, 정렬 보장."""
    paths = utils.resolve_guideline_paths("flutter")
    assert len(paths) == 4
    names = [p.name for p in paths]
    assert names == sorted(names)
    assert all(p.suffix == ".md" for p in paths)
    assert all(p.is_absolute() for p in paths)
    expected_names = {"navigation.md", "state.md", "storage.md", "style.md"}
    assert set(names) == expected_names


def test_react_native_expo_returns_four_sorted_paths(utils) -> None:
    """react-native-expo 프로파일 → 4개 .md 파일, 정렬 보장."""
    paths = utils.resolve_guideline_paths("react-native-expo")
    assert len(paths) == 4
    names = [p.name for p in paths]
    assert names == sorted(names)
    expected_names = {"navigation.md", "state.md", "storage.md", "style.md"}
    assert set(names) == expected_names


def test_android_kotlin_returns_four_sorted_paths(utils) -> None:
    """android-kotlin 프로파일 → 4개 .md 파일."""
    paths = utils.resolve_guideline_paths("android-kotlin")
    assert len(paths) == 4
    names = [p.name for p in paths]
    assert names == sorted(names)
    expected_names = {"architecture.md", "compose.md", "network.md", "storage.md"}
    assert set(names) == expected_names


def test_ios_swift_returns_four_sorted_paths(utils) -> None:
    """ios-swift 프로파일 → 4개 .md 파일."""
    paths = utils.resolve_guideline_paths("ios-swift")
    assert len(paths) == 4
    names = [p.name for p in paths]
    assert names == sorted(names)
    expected_names = {"architecture.md", "network.md", "storage.md", "swiftui.md"}
    assert set(names) == expected_names


def test_fastapi_returns_three_sorted_paths(utils) -> None:
    """fastapi 프로파일 → 3개 .md 파일 (web 프로파일 호환)."""
    paths = utils.resolve_guideline_paths("fastapi")
    assert len(paths) == 3
    names = [p.name for p in paths]
    assert names == sorted(names)
    expected_names = {"api.md", "services.md", "structure.md"}
    assert set(names) == expected_names


def test_electron_returns_four_sorted_paths(utils) -> None:
    """electron 프로파일 → 4개 .md 파일 (IPC envelope + kalpie 계열 renderer)."""
    paths = utils.resolve_guideline_paths("electron")
    assert len(paths) == 4
    names = [p.name for p in paths]
    assert names == sorted(names)
    expected_names = {"ipc.md", "state.md", "structure.md", "style.md"}
    assert set(names) == expected_names


def test_nextjs_returns_four_sorted_paths(utils) -> None:
    """nextjs 프로파일 → 4개 .md 파일 (RSC/Server Actions 중심)."""
    paths = utils.resolve_guideline_paths("nextjs")
    assert len(paths) == 4
    names = [p.name for p in paths]
    assert names == sorted(names)
    expected_names = {"components.md", "data.md", "routing.md", "style.md"}
    assert set(names) == expected_names


def test_nestjs_returns_three_sorted_paths(utils) -> None:
    """nestjs 프로파일 → 3개 .md 파일 (fastapi 와 동형: api/services/structure)."""
    paths = utils.resolve_guideline_paths("nestjs")
    assert len(paths) == 3
    names = [p.name for p in paths]
    assert names == sorted(names)
    expected_names = {"api.md", "services.md", "structure.md"}
    assert set(names) == expected_names


def test_nonexistent_profile_returns_empty_list(utils) -> None:
    """존재하지 않는 프로파일 → 빈 리스트 (silent skip)."""
    paths = utils.resolve_guideline_paths("nonexistent-profile-xyz")
    assert paths == []
