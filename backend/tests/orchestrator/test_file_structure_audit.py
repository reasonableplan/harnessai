"""file_structure_audit.py 단위 테스트 (B6).

parse_profile_file_structure, scan_project_directories, compute_drift 를
직접 import 해서 검증. harness CLI integrity 통합 테스트는 별도.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent
from unittest.mock import MagicMock

from src.orchestrator.file_structure_audit import (
    _parse_tree_to_dirs,
    compute_drift,
    parse_profile_file_structure,
    scan_project_directories,
)

# ── parse_profile_file_structure ─────────────────────────────────────────


def _make_profile(file_structure: str) -> MagicMock:
    """Profile mock — file_structure 만 설정."""
    p = MagicMock()
    p.file_structure = file_structure
    return p


def test_parse_profile_file_structure_rn_expo() -> None:
    """react-native-expo profile 의 file_structure 파싱."""
    file_structure = dedent("""\
        mobile/
          app/
            (auth)/
              login.tsx
            (main)/
              index.tsx
          src/
            shared/
              components/
              store/
              api/
              types/
              hooks/
              theme/
            containers/
              <domain>/
                components/
                store/
          __tests__/
          assets/
            images/
            fonts/
    """)
    profile = _make_profile(file_structure)
    result = parse_profile_file_structure(profile)

    # 최상위 디렉토리
    assert "mobile/" in result
    assert "mobile/app/" in result
    assert "mobile/app/(auth)/" in result
    assert "mobile/app/(main)/" in result
    assert "mobile/src/" in result
    assert "mobile/src/shared/" in result
    assert "mobile/src/shared/components/" in result
    assert "mobile/src/shared/store/" in result
    assert "mobile/src/shared/api/" in result
    assert "mobile/src/shared/types/" in result
    assert "mobile/src/shared/hooks/" in result
    assert "mobile/src/shared/theme/" in result
    assert "mobile/assets/" in result
    assert "mobile/assets/images/" in result
    assert "mobile/assets/fonts/" in result

    # 파일은 포함 안 됨
    assert "mobile/app/(auth)/login.tsx" not in result
    assert "mobile/app/(main)/index.tsx" not in result

    # 플레이스홀더 디렉토리는 포함 (< > 있는 항목)
    assert "mobile/src/containers/<domain>/" in result


def test_parse_profile_file_structure_empty() -> None:
    """빈 file_structure → 빈 set."""
    profile = _make_profile("")
    assert parse_profile_file_structure(profile) == set()


def test_parse_profile_file_structure_inline_comments_stripped() -> None:
    """인라인 주석 (#) 이 제거되고 dir 이름만 남아야 한다."""
    file_structure = dedent("""\
        mobile/                    # 또는 apps/mobile/
          src/
            shared/
              components/          # Button / Input / Modal
    """)
    profile = _make_profile(file_structure)
    result = parse_profile_file_structure(profile)

    assert "mobile/" in result
    assert "mobile/src/" in result
    assert "mobile/src/shared/" in result
    assert "mobile/src/shared/components/" in result
    # 주석이 dir 이름의 일부로 들어가면 안 됨
    for d in result:
        assert "#" not in d


def test_parse_profile_file_structure_files_excluded() -> None:
    """파일 항목은 포함되지 않는다."""
    file_structure = dedent("""\
        backend/
          pyproject.toml
          src/
            main.py
    """)
    profile = _make_profile(file_structure)
    result = parse_profile_file_structure(profile)

    assert "backend/" in result
    assert "backend/src/" in result
    assert "backend/pyproject.toml" not in result
    assert "backend/src/main.py" not in result


def test_parse_tree_trailing_slash_explicit() -> None:
    """trailing '/' 로 명시된 항목은 files_next_check 없이도 dir 로 인식."""
    tree = "mobile/\n  app/\n"
    result = _parse_tree_to_dirs(tree)
    assert "mobile/" in result
    assert "mobile/app/" in result


def test_parse_tree_parent_child_chain() -> None:
    """중첩 깊이 제대로 처리."""
    tree = dedent("""\
        a/
          b/
            c/
              d/
    """)
    result = _parse_tree_to_dirs(tree)
    assert "a/" in result
    assert "a/b/" in result
    assert "a/b/c/" in result
    assert "a/b/c/d/" in result


# ── scan_project_directories ─────────────────────────────────────────────


def test_scan_project_directories_basic(tmp_path: Path) -> None:
    """기본 디렉토리 스캔 — top_n=3 깊이까지."""
    # 구조 생성
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "components").mkdir()
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "images").mkdir()

    result = scan_project_directories(tmp_path, ".", top_n=3)

    assert "src/" in result
    assert "src/components/" in result
    assert "assets/" in result
    assert "assets/images/" in result


def test_scan_project_directories_skips_noise(tmp_path: Path) -> None:
    """_SKIP_DIRS (node_modules, __pycache__, .git 등) 는 포함되지 않는다."""
    (tmp_path / "src").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / ".git").mkdir()

    result = scan_project_directories(tmp_path, ".", top_n=3)

    assert "src/" in result
    assert "node_modules/" not in result
    assert "__pycache__/" not in result
    assert ".git/" not in result


def test_scan_project_directories_skips_hidden(tmp_path: Path) -> None:
    """.으로 시작하는 숨김 디렉토리는 포함되지 않는다."""
    (tmp_path / "src").mkdir()
    (tmp_path / ".cache").mkdir()
    (tmp_path / ".expo").mkdir()

    result = scan_project_directories(tmp_path, ".", top_n=3)

    assert "src/" in result
    assert ".cache/" not in result
    assert ".expo/" not in result


def test_scan_project_directories_depth_limit(tmp_path: Path) -> None:
    """top_n=2 이면 3단계 이상은 포함되지 않는다."""
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "b").mkdir()
    (tmp_path / "a" / "b" / "c").mkdir()  # 3단계

    result = scan_project_directories(tmp_path, ".", top_n=2)

    assert "a/" in result
    assert "a/b/" in result
    assert "a/b/c/" not in result


def test_scan_project_directories_nonexistent_root(tmp_path: Path) -> None:
    """존재하지 않는 profile_path → 빈 set (에러 없이)."""
    result = scan_project_directories(tmp_path, "apps/nonexistent/", top_n=3)
    assert result == set()


def test_scan_project_directories_profile_subpath(tmp_path: Path) -> None:
    """profile_path='apps/mobile/' → apps/mobile/ 아래만 스캔."""
    mobile = tmp_path / "apps" / "mobile"
    mobile.mkdir(parents=True)
    (mobile / "src").mkdir()
    (mobile / "app").mkdir()

    result = scan_project_directories(tmp_path, "apps/mobile/", top_n=3)

    # scan_root 는 apps/mobile/, 결과는 그 아래 상대 경로
    assert "src/" in result
    assert "app/" in result
    # 상위 디렉토리는 포함되지 않아야 함
    assert "apps/" not in result


# ── compute_drift ─────────────────────────────────────────────────────────


def test_compute_drift_no_diff() -> None:
    """declared == actual → match=True, extras=[], missing=[]."""
    declared = {"src/", "src/components/", "assets/"}
    actual = {"src/", "src/components/", "assets/"}
    result = compute_drift(declared, actual)
    assert result.match is True
    assert result.extras == []
    assert result.missing == []


def test_compute_drift_extras() -> None:
    """actual 에 declared 에 없는 dir → extras 에 포함."""
    declared = {"src/", "assets/"}
    actual = {"src/", "assets/", "deeplink/", "notifications/"}
    result = compute_drift(declared, actual)
    assert result.match is False
    assert "deeplink/" in result.extras
    assert "notifications/" in result.extras
    assert result.missing == []


def test_compute_drift_missing() -> None:
    """declared 에 있지만 actual 에 없는 dir → missing 에 포함 (concrete only)."""
    declared = {"src/", "assets/", "docs/"}
    actual = {"src/"}
    result = compute_drift(declared, actual)
    assert result.match is False
    assert "assets/" in result.missing
    assert "docs/" in result.missing


def test_compute_drift_placeholder_excluded_from_missing() -> None:
    """<domain> 같은 플레이스홀더 dir 는 missing 검사에서 제외된다."""
    declared = {"src/", "src/containers/<domain>/"}
    actual = {"src/"}  # <domain> 실제 존재 안 함 (정상)
    result = compute_drift(declared, actual)
    # <domain>/ 는 missing 에 없어야 함
    assert "src/containers/<domain>/" not in result.missing


def test_compute_drift_both_extras_and_missing() -> None:
    """extras + missing 동시에 있는 케이스."""
    declared = {"src/", "docs/"}
    actual = {"src/", "extra_dir/"}
    result = compute_drift(declared, actual)
    assert "extra_dir/" in result.extras
    assert "docs/" in result.missing
    assert result.match is False


# ── integrity WARN 통합 (harness CLI 직접 호출) ───────────────────────────


def test_integrity_file_structure_drift_warns(tmp_path: Path) -> None:
    """harness integrity 가 profile file_structure drift 시 WARN 을 낸다.

    tmp_path 아래 가짜 프로젝트 + profile 을 구성하고
    harness 의 _check_file_structure_drift 를 직접 호출해 검증.
    """
    import importlib
    import importlib.util
    import sys as _sys
    from importlib.machinery import SourceFileLoader

    repo_root = Path(__file__).resolve().parents[3]
    harness_bin = repo_root / "harness" / "bin" / "harness"
    loader = SourceFileLoader("_harness_drift_test", str(harness_bin))
    spec = importlib.util.spec_from_loader("_harness_drift_test", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    _sys.modules["_harness_drift_test"] = mod
    loader.exec_module(mod)

    # profiles_dir 에 가짜 profile 작성
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()

    import yaml

    profile_data = {
        "id": "test-profile",
        "name": "Test Profile",
        "status": "confirmed",
        "version": 1,
        "file_structure": "mobile/\n  src/\n    shared/\n",
    }
    profile_md = "---\n" + yaml.safe_dump(profile_data, allow_unicode=True) + "---\n"
    (profiles_dir / "test-profile.md").write_text(profile_md, encoding="utf-8")

    # 프로젝트: mobile/src/shared/ + extra dir mobile/deeplink/
    project = tmp_path / "project"
    (project / "mobile" / "src" / "shared").mkdir(parents=True)
    (project / "mobile" / "deeplink").mkdir(parents=True)  # extra

    report = mod.Report()
    mod._check_file_structure_drift(project, profiles_dir, report)

    # WARN 이 나야 함 (extra dir 가 있으므로)
    warns = [i for i in report.issues if i.severity == "warn"]
    assert len(warns) >= 1
    # extras 에 deeplink/ 가 언급되어야 함
    assert any("deeplink" in w.message for w in warns)


def test_integrity_file_structure_no_drift_no_warn(tmp_path: Path) -> None:
    """extra dir 없으면 WARN 없음."""
    import importlib
    import importlib.util
    import sys as _sys
    from importlib.machinery import SourceFileLoader

    repo_root = Path(__file__).resolve().parents[3]
    harness_bin = repo_root / "harness" / "bin" / "harness"
    loader = SourceFileLoader("_harness_nodrift_test", str(harness_bin))
    spec = importlib.util.spec_from_loader("_harness_nodrift_test", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    _sys.modules["_harness_nodrift_test"] = mod
    loader.exec_module(mod)

    import yaml

    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    profile_data = {
        "id": "test-profile2",
        "name": "Test Profile2",
        "status": "confirmed",
        "version": 1,
        "file_structure": "mobile/\n  src/\n",
    }
    profile_md = "---\n" + yaml.safe_dump(profile_data, allow_unicode=True) + "---\n"
    (profiles_dir / "test-profile2.md").write_text(profile_md, encoding="utf-8")

    # 프로젝트: profile 과 정확히 일치
    project = tmp_path / "project"
    (project / "mobile" / "src").mkdir(parents=True)

    report = mod.Report()
    mod._check_file_structure_drift(project, profiles_dir, report)

    drift_warns = [
        i for i in report.issues if i.severity == "warn" and "file_structure drift" in i.message
    ]
    assert drift_warns == []
