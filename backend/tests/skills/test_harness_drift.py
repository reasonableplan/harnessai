"""harness CLI 의 `drift` 서브커맨드 단위 테스트.

대상 함수: `cmd_drift()` — repo(HARNESS_AI_HOME) ↔ 설치 미러(~/.claude) 정합성 검사.
비교 대상: harness/ 전체 + skills/{ha-*,_ha_shared}. CRLF 차이는 drift 아님.

모든 픽스처는 tmp_path 기반 (실제 ~/.claude 를 건드리지 않음).
"""

from __future__ import annotations

from pathlib import Path


def _write(root: Path, rel: str, content: bytes = b"same\n") -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


def _make_pair(tmp_path: Path) -> tuple[Path, Path]:
    """repo/target 두 트리에 동일한 미러 파일 세트를 만든다."""
    repo = tmp_path / "repo"
    target = tmp_path / "target"
    for root in (repo, target):
        _write(root, "harness/profiles/python-cli.md")
        _write(root, "harness/bin/harness")
        _write(root, "skills/ha-build/run.py")
        _write(root, "skills/_ha_shared/utils.py")
    return repo, target


def test_drift_clean_identical_trees(harness_module, tmp_path: Path) -> None:
    repo, target = _make_pair(tmp_path)
    assert harness_module.cmd_drift(repo, target) == 0


def test_drift_detects_content_diff(harness_module, tmp_path: Path, capsys) -> None:
    repo, target = _make_pair(tmp_path)
    _write(target, "skills/ha-build/run.py", b"changed\n")
    assert harness_module.cmd_drift(repo, target) == 1
    out = capsys.readouterr().out
    assert "[DIFF]" in out
    assert "skills/ha-build/run.py" in out


def test_drift_crlf_only_difference_is_clean(harness_module, tmp_path: Path) -> None:
    repo, target = _make_pair(tmp_path)
    _write(repo, "harness/profiles/python-cli.md", b"line1\r\nline2\r\n")
    _write(target, "harness/profiles/python-cli.md", b"line1\nline2\n")
    assert harness_module.cmd_drift(repo, target) == 0


def test_drift_detects_missing_in_target(harness_module, tmp_path: Path, capsys) -> None:
    repo, target = _make_pair(tmp_path)
    _write(repo, "harness/templates/skeleton/stack.md")
    assert harness_module.cmd_drift(repo, target) == 1
    out = capsys.readouterr().out
    assert "[MISSING]" in out
    assert "harness/templates/skeleton/stack.md" in out


def test_drift_detects_extra_in_target(harness_module, tmp_path: Path, capsys) -> None:
    """설치본에만 있는 파일 = 레포 미백포트 작업 또는 stale 잔재 — drift 로 보고."""
    repo, target = _make_pair(tmp_path)
    _write(target, "skills/ha-build/helper.py")
    assert harness_module.cmd_drift(repo, target) == 1
    out = capsys.readouterr().out
    assert "[EXTRA]" in out
    assert "skills/ha-build/helper.py" in out


def test_drift_ignores_pycache_pyc_manifest_and_backups(harness_module, tmp_path: Path) -> None:
    repo, target = _make_pair(tmp_path)
    _write(repo, "skills/ha-build/__pycache__/run.cpython-312.pyc", b"\x00repo")
    _write(target, "skills/ha-build/__pycache__/run.cpython-313.pyc", b"\x00target")
    _write(target, "harness/.install-manifest.json", b"{}")
    _write(target, "skills/ha-build/SKILL.md.bak", b"old snapshot")
    assert harness_module.cmd_drift(repo, target) == 0


def test_drift_ignores_non_ha_skill_dirs(harness_module, tmp_path: Path) -> None:
    """skills/ 아래 ha-*/_ha_shared 외 디렉토리(다른 도구 스킬)는 미러 범위 아님."""
    repo, target = _make_pair(tmp_path)
    _write(target, "skills/gstack/SKILL.md")
    _write(repo, "skills/.omc/state/mission-state.json")
    assert harness_module.cmd_drift(repo, target) == 0


def test_drift_missing_root_is_usage_error(harness_module, tmp_path: Path) -> None:
    repo, _ = _make_pair(tmp_path)
    assert harness_module.cmd_drift(repo, tmp_path / "nonexistent") == 2
