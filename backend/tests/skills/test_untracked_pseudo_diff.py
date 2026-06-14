"""dogfood P1 회귀: untracked 신규 파일이 보안/슬롭 스캔을 우회하는 갭.

git diff (HEAD / main...HEAD / --cached) 는 미추적 파일을 포함하지 않는다.
ha-build security gate 는 방금 생성된 (아직 add 안 된) 파일 검사가 존재
이유인데 정작 그 파일들이 입력에서 빠졌고, ha-review 도 동일했다.
utils.untracked_pseudo_diff 가 `diff --git` 형식 의사 diff 로 합성해
기존 strip_doc_files_from_diff / 보안 훅 입력에 그대로 합류한다.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType

import pytest

from src.orchestrator.security_hooks import strip_doc_files_from_diff

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_module(name: str, path: Path) -> ModuleType:
    loader = SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def utils() -> ModuleType:
    return _load_module(
        "ha_shared_utils_untracked", REPO_ROOT / "skills" / "_ha_shared" / "utils.py"
    )


@pytest.fixture(scope="module")
def ha_review() -> ModuleType:
    return _load_module("ha_review_run_untracked", REPO_ROOT / "skills" / "ha-review" / "run.py")


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@example.com",
            "-c",
            "user.name=t",
            "commit",
            "--allow-empty",
            "-m",
            "init",
            "-q",
        ],
        cwd=path,
        check=True,
    )


# ── untracked_pseudo_diff 단위 ─────────────────────────────────────────────


def test_untracked_py_included(utils, tmp_path) -> None:
    """미추적 .py 가 diff --git 헤더 + '+' 라인으로 합성된다."""
    _init_repo(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("result = eval(user_input)\n", encoding="utf-8")

    out = utils.untracked_pseudo_diff(tmp_path)

    assert "diff --git a/src/app.py b/src/app.py" in out
    assert "+result = eval(user_input)" in out


def test_tracked_file_not_included(utils, tmp_path) -> None:
    """커밋된 파일은 의사 diff 대상 아님 (실제 diff 가 책임)."""
    _init_repo(tmp_path)
    (tmp_path / "tracked.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.py"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@example.com",
            "-c",
            "user.name=t",
            "commit",
            "-m",
            "add",
            "-q",
        ],
        cwd=tmp_path,
        check=True,
    )

    assert "tracked.py" not in utils.untracked_pseudo_diff(tmp_path)


def test_doc_block_strippable(utils, tmp_path) -> None:
    """합성 헤더가 strip_doc_files_from_diff 형식과 호환 — .md 만 제거, .py 유지."""
    _init_repo(tmp_path)
    (tmp_path / "notes.md").write_text("external eval ( prose\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("eval(x)\n", encoding="utf-8")

    stripped = strip_doc_files_from_diff(utils.untracked_pseudo_diff(tmp_path))

    assert "app.py" in stripped
    assert "notes.md" not in stripped


def test_binary_skipped(utils, tmp_path) -> None:
    """NUL 포함 바이너리는 제외."""
    _init_repo(tmp_path)
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01\x02")

    assert "blob.bin" not in utils.untracked_pseudo_diff(tmp_path)


def test_oversize_file_skipped(utils, tmp_path) -> None:
    """파일 크기 상한 초과 (생성물/락파일 폭주 방지)."""
    _init_repo(tmp_path)
    (tmp_path / "big.py").write_text("x = 1\n" * 50_000, encoding="utf-8")  # ~300KB

    assert "big.py" not in utils.untracked_pseudo_diff(tmp_path)


def test_vendor_dir_skipped(utils, tmp_path) -> None:
    """.gitignore 없는 신규 프로젝트에서 node_modules 폭주 방지."""
    _init_repo(tmp_path)
    nm = tmp_path / "node_modules" / "pkg"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("eval(x)\n", encoding="utf-8")

    assert "node_modules" not in utils.untracked_pseudo_diff(tmp_path)


def test_not_git_repo_returns_empty(utils, tmp_path) -> None:
    """git repo 아니면 빈 문자열 (호출처의 기존 not-git 처리 유지)."""
    (tmp_path / "a.py").write_text("eval(x)\n", encoding="utf-8")

    assert utils.untracked_pseudo_diff(tmp_path) == ""


# ── ha-review _extract_diff 합류 ──────────────────────────────────────────


def test_extract_diff_includes_untracked(ha_review, tmp_path) -> None:
    """tracked diff 가 비어도 untracked 신규 모듈이 스캔 입력에 들어온다."""
    _init_repo(tmp_path)
    (tmp_path / "new_module.py").write_text("token = eval(payload)\n", encoding="utf-8")

    diff, _scope = ha_review._extract_diff(tmp_path)

    assert "+token = eval(payload)" in diff
