"""FP #17 회귀 테스트: integrity file_structure drift 오탐 차단.

실전 결함 (Mendline dogfood, /ha-verify prepare integrity 게이트):
- 활성 프로파일은 electron 1개인데 비활성 12종 전부에 drift WARN (extras 노이즈).
- electron declared 의 desktop/__tests__/ 가 실재하는데 missing 으로 오보고
  (_scan_project_dirs 가 __tests__ 를 skip → declared 와 비대칭).

Fix: plan confirmed 프로파일만 순회 + declared 에서 _SKIP_DIRS 세그먼트 제외.
대상: harness/bin/harness 의 _check_file_structure_drift (단일출처).
"""

from __future__ import annotations

from pathlib import Path

import yaml

# fixtures: harness_module (from conftest)


def _write_profile(profiles_dir: Path, pid: str, file_structure: str) -> None:
    md = (
        "---\n"
        + yaml.safe_dump({"id": pid, "file_structure": file_structure}, allow_unicode=True)
        + "---\n"
    )
    (profiles_dir / f"{pid}.md").write_text(md, encoding="utf-8")


def _setup(tmp_path: Path) -> tuple[Path, Path]:
    """profiles_dir 를 scan 대상 밖에 두어 오염 방지. (project, profiles_dir) 반환."""
    project = tmp_path / "proj"
    project.mkdir()
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    return project, profiles_dir


def test_drift_only_confirmed_profiles(harness_module, tmp_path: Path) -> None:
    """confirmed_ids 가 주어지면 해당 프로파일만 drift_checks 에 포함."""
    project, profiles_dir = _setup(tmp_path)
    _write_profile(profiles_dir, "active-prof", "src/\n")
    _write_profile(profiles_dir, "inactive-prof", "android/\n")
    (project / "src").mkdir()

    report = harness_module.Report()
    checks = harness_module._check_file_structure_drift(
        project, profiles_dir, report, confirmed_ids={"active-prof"}
    )
    assert {c[0] for c in checks} == {"active-prof"}


def test_drift_all_profiles_when_no_confirmed(harness_module, tmp_path: Path) -> None:
    """confirmed_ids=None 이면 legacy 전 프로파일 순회 (하위호환)."""
    project, profiles_dir = _setup(tmp_path)
    _write_profile(profiles_dir, "p1", "src/\n")
    _write_profile(profiles_dir, "p2", "lib/\n")

    report = harness_module.Report()
    checks = harness_module._check_file_structure_drift(project, profiles_dir, report)
    assert {c[0] for c in checks} == {"p1", "p2"}


def test_drift_skip_dir_segment_not_missing(harness_module, tmp_path: Path) -> None:
    """declared 의 __tests__/ 가 실재하면 missing 으로 보고하지 않음 (비대칭 제거)."""
    project, profiles_dir = _setup(tmp_path)
    _write_profile(profiles_dir, "el", "desktop/\n  src/\n  __tests__/\n")
    (project / "desktop" / "src").mkdir(parents=True)
    (project / "desktop" / "__tests__").mkdir(parents=True)

    report = harness_module.Report()
    checks = harness_module._check_file_structure_drift(project, profiles_dir, report)
    _pid, extras, missing = next(c for c in checks if c[0] == "el")
    assert "desktop/__tests__/" not in missing
    assert missing == []
    assert extras == []


def test_drift_genuine_missing_still_reported(harness_module, tmp_path: Path) -> None:
    """TP 보존: skip-dir 가 아닌 실제 미존재 디렉토리는 여전히 missing."""
    project, profiles_dir = _setup(tmp_path)
    _write_profile(profiles_dir, "el", "desktop/\n  src/\n  components/\n")
    (project / "desktop" / "src").mkdir(parents=True)
    # desktop/components/ 는 생성 안 함 → 진짜 missing

    report = harness_module.Report()
    checks = harness_module._check_file_structure_drift(project, profiles_dir, report)
    el = next(c for c in checks if c[0] == "el")
    assert "desktop/components/" in el[2]


def test_drift_concrete_ancestor_of_placeholder_counts_as_declared(
    harness_module, tmp_path: Path
) -> None:
    """dogfood #6: 'src/<pkg>/' 선언 시 실재 'src/' 는 extras 아님 (구체적 조상 인정)."""
    project, profiles_dir = _setup(tmp_path)
    _write_profile(profiles_dir, "cli", "src/<pkg>/\n  __init__.py\n")
    (project / "src" / "urlshort").mkdir(parents=True)

    report = harness_module.Report()
    checks = harness_module._check_file_structure_drift(project, profiles_dir, report)
    _pid, extras, _missing = next(c for c in checks if c[0] == "cli")
    assert "src/" not in extras  # 구체적 조상 → declared 로 인정


def test_drift_docs_dir_is_benign_extra(harness_module, tmp_path: Path) -> None:
    """dogfood #6: docs/ 는 harness 상태 디렉토리 (harness-plan.md/skeleton.md) — extras 제외."""
    project, profiles_dir = _setup(tmp_path)
    _write_profile(profiles_dir, "cli", "src/\n")
    (project / "src").mkdir()
    (project / "docs").mkdir()  # harness 가 만드는 디렉토리

    report = harness_module.Report()
    checks = harness_module._check_file_structure_drift(project, profiles_dir, report)
    _pid, extras, _missing = next(c for c in checks if c[0] == "cli")
    assert "docs/" not in extras
