"""R1 회귀 테스트: ha-review not-git 프로젝트 silent-pass 방지.

결함 요약:
  not-git repo 에서 git diff 가 빈 문자열을 반환 → changed_files: [],
  diff_size_bytes: 0, ai_slop_findings: [] 로 모든 보안/슬롭 훅이 빈 입력 →
  무조건 0건 발견 (silent fail). 챙겼니 dogfood 에서 26 task 코드가
  리뷰 0건 통과한 원인.

Fix: cmd_prepare 시작부에서 git rev-parse --git-dir 로 git repo 게이트 추가.
  not-git → stderr actionable 에러 + sys.exit(2).
  git 미설치 → 동일 exit 2, 메시지만 구분.
"""

from __future__ import annotations

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HA_REVIEW_RUN = REPO_ROOT / "skills" / "ha-review" / "run.py"


@pytest.fixture(scope="module")
def ha_review() -> ModuleType:
    """ha-review/run.py (repo mirror) 를 모듈로 로드."""
    loader = SourceFileLoader("ha_review_git_gate", str(HA_REVIEW_RUN))
    spec = importlib.util.spec_from_loader("ha_review_git_gate", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ha_review_git_gate"] = mod
    loader.exec_module(mod)
    return mod


# ── _check_git_repo 단위 테스트 ───────────────────────────────────────


def test_check_git_repo_exits_2_when_not_git(ha_review: ModuleType, tmp_path: Path) -> None:
    """not-git 디렉토리에서 _check_git_repo 호출 → SystemExit(2)."""
    # tmp_path 는 git init 안 된 순수 임시 디렉토리
    with pytest.raises(SystemExit) as exc_info:
        ha_review._check_git_repo(tmp_path)
    assert exc_info.value.code == 2


def test_check_git_repo_error_message_mentions_git_repo(
    ha_review: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """not-git 시 에러 메시지에 'git 저장소 아님' 포함."""
    with pytest.raises(SystemExit):
        ha_review._check_git_repo(tmp_path)
    captured = capsys.readouterr()
    # info() 는 stderr 에 출력
    assert "git 저장소 아님" in captured.err or "git 저장소 아님" in captured.out


def test_check_git_repo_exits_2_when_git_not_installed(
    ha_review: ModuleType, tmp_path: Path
) -> None:
    """git 명령 미설치 (FileNotFoundError) → SystemExit(2)."""
    with (
        patch("subprocess.run", side_effect=FileNotFoundError("git not found")),
        pytest.raises(SystemExit) as exc_info,
    ):
        ha_review._check_git_repo(tmp_path)
    assert exc_info.value.code == 2


def test_check_git_repo_git_not_installed_message(
    ha_review: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """git 미설치 시 에러 메시지에 '미설치' 포함."""
    with (
        patch("subprocess.run", side_effect=FileNotFoundError("git not found")),
        pytest.raises(SystemExit),
    ):
        ha_review._check_git_repo(tmp_path)
    captured = capsys.readouterr()
    assert "미설치" in captured.err or "미설치" in captured.out


def test_check_git_repo_passes_in_git_repo(ha_review: ModuleType) -> None:
    """실제 git repo (이 레포 자체) 에서 _check_git_repo → 정상 반환 (exit 없음)."""
    # REPO_ROOT 는 git repo 이므로 exit 없이 통과해야 함
    ha_review._check_git_repo(REPO_ROOT)  # SystemExit 발생 시 테스트 실패


# ── cmd_prepare 통합: not-git 이면 gate 에서 막힘 ─────────────────────


def test_cmd_prepare_blocked_on_non_git_project(ha_review: ModuleType, tmp_path: Path) -> None:
    """not-git 프로젝트에서 cmd_prepare → exit 2 (gate before any diff logic)."""
    # harness-plan.md + minimal project 구조
    docs = tmp_path / "docs"
    docs.mkdir()
    plan_content = """---
version: 2
project_name: test-project
pipeline:
  current_step: verified
  completed_steps: [designing, planning, building, verifying]
  verify_history: []
profiles:
  - id: react-native-expo
    path: "."
skeleton_hash: ""
redesign_history: []
---
"""
    (docs / "harness-plan.md").write_text(plan_content, encoding="utf-8")

    # load_plan 이 tmp_path 기준 plan 을 반환하도록 mock
    mock_plan = MagicMock()
    mock_plan.pipeline.current_step = "verified"
    mock_plan.profiles = []

    with (
        patch.object(
            ha_review, "load_plan", return_value=(mock_plan, docs / "harness-plan.md", tmp_path)
        ),
        patch.object(ha_review, "assert_state"),  # state assertion 통과
        pytest.raises(SystemExit) as exc_info,
    ):
        args = MagicMock()
        ha_review.cmd_prepare(args)

    assert exc_info.value.code == 2


# ── #18: _extract_diff base 자동결정 ──────────────────────────────────────


def _git_init_repo(tmp_path: Path):
    """tmp_path 에 main 브랜치 git repo 초기화 후 git(*args) 헬퍼 반환."""
    import subprocess

    def git(*a: str) -> str:
        r = subprocess.run(
            ["git", *a], cwd=tmp_path, capture_output=True, text=True, encoding="utf-8"
        )
        assert r.returncode == 0, f"git {a} 실패: {r.stderr}"
        return r.stdout.strip()

    git("init", "-b", "main")
    git("config", "user.email", "t@t.t")
    git("config", "user.name", "tester")
    return git


def test_extract_diff_uses_origin_main_base_on_main_branch(
    ha_review: ModuleType, tmp_path: Path
) -> None:
    """main 직작업 + 커밋 완료 시 main...HEAD(빈 결과) 대신 origin/main...HEAD 로
    빌드 diff 를 잡는다 (이슈 #18 — main 워크플로우 보안훅 vacuous pass 방지)."""
    git = _git_init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("base\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "initial")
    git("update-ref", "refs/remotes/origin/main", git("rev-parse", "HEAD"))
    # 빌드 커밋 — main 이 origin/main 보다 앞섬
    (tmp_path / "feature.py").write_text("def build():\n    return 1\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "T-001 build")

    diff, scope = ha_review._extract_diff(tmp_path)

    assert "feature.py" in diff, f"커밋된 빌드가 diff 에 없음 (vacuous). scope={scope}"
    assert "origin/main" in scope, f"origin/main base 미사용: {scope}"


def test_extract_diff_explicit_base_override(ha_review: ModuleType, tmp_path: Path) -> None:
    """--base <ref> 로 base 를 명시하면 그 ref...HEAD 를 사용 (이슈 #18 escape hatch)."""
    git = _git_init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("base\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "initial")
    base_sha = git("rev-parse", "HEAD")
    (tmp_path / "feature.py").write_text("x = 1\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "T-001")

    diff, scope = ha_review._extract_diff(tmp_path, base_sha)

    assert "feature.py" in diff, f"explicit base diff 누락. scope={scope}"
    assert base_sha[:7] in scope or base_sha in scope, f"scope 에 base ref 없음: {scope}"


def test_extract_diff_working_tree_scope_when_committed_no_remote(
    ha_review: ModuleType, tmp_path: Path
) -> None:
    """main 직작업 + 커밋 완료 + 원격 없음 → base 미결정 → 워킹트리 collapse 를
    scope 라벨로 표면화 (silent 아님 — 이슈 #18 정직성)."""
    git = _git_init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("base\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "initial")
    (tmp_path / "b.py").write_text("y = 2\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "T-001")

    _diff, scope = ha_review._extract_diff(tmp_path)

    assert scope.startswith("working-tree"), f"collapse 가 scope 에 안 드러남: {scope}"
