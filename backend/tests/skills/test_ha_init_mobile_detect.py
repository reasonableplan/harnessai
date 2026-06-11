"""Task B1: ha-init detect 출력에 is_mobile 필드 + stderr 모바일 안내 검증."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HA_INIT_RUN = REPO_ROOT / "skills" / "ha-init" / "run.py"

_MOBILE_PROFILE_IDS = frozenset({"react-native-expo", "flutter", "android-kotlin", "ios-swift"})


def _run_detect(project: Path) -> tuple[dict, str]:
    """ha-init detect 실행. (stdout_json, stderr_text) 반환."""
    env = dict(os.environ)
    env["HARNESS_AI_HOME"] = str(REPO_ROOT)
    result = subprocess.run(
        [sys.executable, str(HA_INIT_RUN), "detect", str(project)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(project),
        env=env,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"ha-init detect failed (rc={result.returncode}):\n"
        f"stdout: {result.stdout[:500]}\nstderr: {result.stderr[:500]}"
    )
    return json.loads(result.stdout), result.stderr


# ── 픽스처 ──────────────────────────────────────────────────────────────


@pytest.fixture()
def flutter_project(tmp_path: Path) -> Path:
    project = tmp_path / "myflutterapp"
    project.mkdir()
    (project / "pubspec.yaml").write_text(
        "name: myflutterapp\nflutter:\n  sdk: flutter\n", encoding="utf-8"
    )
    return project


@pytest.fixture()
def rn_project(tmp_path: Path) -> Path:
    project = tmp_path / "myrnapp"
    project.mkdir()
    (project / "package.json").write_text(
        '{"name": "myrnapp", "dependencies": {"expo": "^50.0.0", "react-native": "0.73.0"}}',
        encoding="utf-8",
    )
    return project


@pytest.fixture()
def python_cli_project(tmp_path: Path) -> Path:
    project = tmp_path / "mycli"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        "[project]\nname = 'mycli'\n[project.scripts]\nmycli = 'mycli:main'\n",
        encoding="utf-8",
    )
    return project


@pytest.fixture()
def fastapi_project(tmp_path: Path) -> Path:
    project = tmp_path / "myapi"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        "[project]\nname = 'myapi'\ndependencies = ['fastapi', 'uvicorn']\n",
        encoding="utf-8",
    )
    return project


# ── 테스트 ──────────────────────────────────────────────────────────────


def test_flutter_is_mobile_true(flutter_project: Path) -> None:
    """flutter 프로젝트 → matches 의 flutter 항목에 is_mobile: true."""
    output, _ = _run_detect(flutter_project)
    flutter_match = next((m for m in output["matches"] if m["profile_id"] == "flutter"), None)
    assert flutter_match is not None, "flutter profile not detected"
    assert flutter_match.get("is_mobile") is True, f"expected is_mobile=true, got: {flutter_match}"


def test_react_native_expo_is_mobile_true(rn_project: Path) -> None:
    """react-native-expo 프로젝트 → is_mobile: true."""
    output, _ = _run_detect(rn_project)
    rn_match = next((m for m in output["matches"] if m["profile_id"] == "react-native-expo"), None)
    assert rn_match is not None, "react-native-expo profile not detected"
    assert rn_match.get("is_mobile") is True, f"expected is_mobile=true, got: {rn_match}"


def test_python_cli_is_mobile_false(python_cli_project: Path) -> None:
    """python-cli 프로젝트 → 모든 matches 에 is_mobile: false."""
    output, _ = _run_detect(python_cli_project)
    for m in output["matches"]:
        assert m.get("is_mobile") is False, (
            f"expected is_mobile=false for {m['profile_id']}, got: {m}"
        )


def test_fastapi_is_mobile_false(fastapi_project: Path) -> None:
    """fastapi 프로젝트 → 모든 matches 에 is_mobile: false."""
    output, _ = _run_detect(fastapi_project)
    for m in output["matches"]:
        assert m.get("is_mobile") is False, (
            f"expected is_mobile=false for {m['profile_id']}, got: {m}"
        )


def test_mobile_detect_stderr_message(flutter_project: Path) -> None:
    """flutter 감지 시 stderr 에 '모바일 프로젝트 감지' 메시지 포함."""
    _, stderr = _run_detect(flutter_project)
    assert "모바일 프로젝트 감지" in stderr, f"expected mobile guidance in stderr, got: {stderr!r}"
