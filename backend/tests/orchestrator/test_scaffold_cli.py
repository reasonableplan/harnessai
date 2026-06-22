"""harness scaffold CLI 서브커맨드 테스트 (Track B — 멀티에이전트 배선).

subprocess 로 설치 미러(~/.claude/harness/bin/harness)를 직접 실행하여 검증.
scaffold 는 backend/src/orchestrator/agent_scaffold.py 를 standalone 로드하므로
HARNESS_AI_HOME 환경변수를 레포 루트로 지정해야 한다.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

# 설치 미러 CLI (test_graph_cli 와 동일 타깃)
_HARNESS_CLI = Path.home() / ".claude" / "harness" / "bin" / "harness"

# 레포 루트: backend/tests/orchestrator/<file> → parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _run_scaffold(*args: str, out: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "HARNESS_AI_HOME": str(_REPO_ROOT)}
    return subprocess.run(
        [sys.executable, str(_HARNESS_CLI), "scaffold", *args, "--out", str(out)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


def test_gemini_single_skill_writes_valid_toml(tmp_path: Path) -> None:
    r = _run_scaffold("--agent", "gemini", "--skill", "ha-verify", out=tmp_path)
    assert r.returncode == 0, r.stderr
    toml_file = tmp_path / ".gemini" / "commands" / "ha-verify.toml"
    assert toml_file.is_file()
    parsed = tomllib.loads(toml_file.read_text(encoding="utf-8"))
    assert "prompt" in parsed and "description" in parsed
    # 컨텍스트 파일도 생성
    assert (tmp_path / "GEMINI.md").is_file()


def test_gemini_path_substitution(tmp_path: Path) -> None:
    r = _run_scaffold("--agent", "gemini", "--skill", "ha-verify", out=tmp_path)
    assert r.returncode == 0, r.stderr
    content = (tmp_path / ".gemini" / "commands" / "ha-verify.toml").read_text(encoding="utf-8")
    assert "~/.claude/" not in content
    assert "${HARNESS_AI_HOME}/skills/" in content
    assert "${HARNESS_AI_HOME}/harness/bin/harness" in content


def test_all_agents_single_skill_writes_five_files(tmp_path: Path) -> None:
    r = _run_scaffold("--agent", "all", "--skill", "ha-verify", out=tmp_path)
    assert r.returncode == 0, r.stderr
    # 3 command files + 2 context files (gemini/copilot)
    assert (tmp_path / ".claude" / "skills" / "ha-verify" / "SKILL.md").is_file()
    assert (tmp_path / ".gemini" / "commands" / "ha-verify.toml").is_file()
    assert (tmp_path / ".github" / "prompts" / "ha-verify.prompt.md").is_file()
    assert (tmp_path / "GEMINI.md").is_file()
    assert (tmp_path / ".github" / "copilot-instructions.md").is_file()


def test_claude_keeps_native_paths(tmp_path: Path) -> None:
    r = _run_scaffold("--agent", "claude", "--skill", "ha-verify", out=tmp_path)
    assert r.returncode == 0, r.stderr
    content = (tmp_path / ".claude" / "skills" / "ha-verify" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "~/.claude/skills/" in content
    assert "${HARNESS_AI_HOME}" not in content


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    r = _run_scaffold("--agent", "gemini", "--skill", "ha-verify", "--dry-run", out=tmp_path)
    assert r.returncode == 0, r.stderr
    assert not (tmp_path / ".gemini").exists()
    assert "[DRY]" in r.stdout


def test_all_skills_for_gemini(tmp_path: Path) -> None:
    r = _run_scaffold("--agent", "gemini", out=tmp_path)
    assert r.returncode == 0, r.stderr
    toml_files = list((tmp_path / ".gemini" / "commands").glob("ha-*.toml"))
    # 11 ha-* skills (init/design/plan/build/verify/review/smoke/ship/redesign/deepinit/log)
    assert len(toml_files) >= 11
    for f in toml_files:
        tomllib.loads(f.read_text(encoding="utf-8"))  # all parse


def test_unknown_agent_exits_2(tmp_path: Path) -> None:
    r = _run_scaffold("--agent", "openai", "--skill", "ha-verify", out=tmp_path)
    assert r.returncode == 2
    assert "unknown agent" in r.stderr


def test_missing_skill_exits_3(tmp_path: Path) -> None:
    r = _run_scaffold("--agent", "gemini", "--skill", "ha-nonexistent", out=tmp_path)
    assert r.returncode == 3
    assert "SKILL.md" in r.stderr
