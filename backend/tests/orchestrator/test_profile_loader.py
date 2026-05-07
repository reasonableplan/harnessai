"""profile_loader 단위 테스트.

모든 픽스처는 tmp_path 기반 — 사용자 환경 ~/.claude/harness/ 비의존.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from src.orchestrator.plan_manager import ScaleAxes
from src.orchestrator.profile_loader import (
    CyclicInheritanceError,
    Profile,
    ProfileLoader,
    ProfileNotFoundError,
    SkeletonSections,
    Toolchain,
    Whitelist,
)


def _write_profile(
    dir_: Path,
    profile_id: str,
    *,
    extends: str | None = None,
    paths: list[str] | None = None,
    detect: dict | None = None,
    required_sections: list[str] | None = None,
    optional_sections: list[str] | None = None,
    runtime: list[str] | None = None,
    components: list[dict] | None = None,
    extra_frontmatter: dict | None = None,
    body: str = "",
) -> Path:
    """프로파일 파일 작성 헬퍼 — frontmatter + body."""
    dir_.mkdir(parents=True, exist_ok=True)
    fm: list[str] = [
        f"id: {profile_id}",
        f"name: {profile_id.title()}",
        "status: confirmed",
        "version: 1",
    ]
    if extends:
        fm.append(f"extends: {extends}")
    if paths is not None:
        fm.append(f"paths: {paths!r}")
    if detect is not None:
        fm.append("detect:")
        for k, v in detect.items():
            fm.append(f"  {k}: {v!r}")
    if components is not None:
        fm.append("components:")
        for c in components:
            fm.append(f"  - id: {c['id']}")
            fm.append(f"    required: {str(c.get('required', False)).lower()}")
            fm.append(f"    skeleton_section: {c.get('skeleton_section', '')}")
    fm.append("skeleton_sections:")
    fm.append(f"  required: {required_sections or []!r}")
    fm.append(f"  optional: {optional_sections or []!r}")
    fm.append(f"  order: {(required_sections or []) + (optional_sections or [])!r}")
    fm.append("toolchain:")
    fm.append("  install: null")
    fm.append("  test: null")
    fm.append("  lint: null")
    fm.append("  type: null")
    fm.append("  format: null")
    fm.append("whitelist:")
    fm.append(f"  runtime: {runtime or []!r}")
    fm.append("  dev: []")
    fm.append("  prefix_allowed: []")
    fm.append("file_structure: 'x'")
    fm.append("gstack_mode: manual")
    if extra_frontmatter:
        for k, v in extra_frontmatter.items():
            fm.append(f"{k}: {v!r}")

    text = "---\n" + "\n".join(fm) + "\n---\n" + body
    path = dir_ / f"{profile_id}.md"
    path.write_text(text, encoding="utf-8")
    return path


def _write_base(dir_: Path, runtime: list[str] | None = None) -> None:
    dir_.mkdir(parents=True, exist_ok=True)
    text = dedent(
        f"""\
        ---
        id: _base
        name: Base
        whitelist:
          runtime: {runtime or []!r}
          dev: []
          prefix_allowed: []
        ---
        # Base body
        """
    )
    (dir_ / "_base.md").write_text(text, encoding="utf-8")


def _write_registry(harness_dir: Path, rules: list[dict]) -> None:
    profiles_dir = harness_dir / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    import yaml as _yaml

    (profiles_dir / "_registry.yaml").write_text(
        _yaml.safe_dump({"version": 1, "rules": rules}),
        encoding="utf-8",
    )


# ── 기본 로드 ──────────────────────────────────────────────────────────


def test_load_basic_profile(tmp_path: Path) -> None:
    """단일 프로파일 로드 — 필드 매핑 확인."""
    harness = tmp_path / "harness"
    _write_profile(
        harness / "profiles",
        "minimal",
        required_sections=["overview", "core.logic"],
        runtime=["click"],
    )
    loader = ProfileLoader(harness_dir=harness)
    p = loader.load("minimal")
    assert p.id == "minimal"
    assert p.skeleton_sections.required == ("overview", "core.logic")
    assert p.whitelist.runtime == ("click",)
    assert p.gstack_mode == "manual"


def test_load_caches(tmp_path: Path) -> None:
    """동일 프로파일 두 번 로드 — 같은 인스턴스 (캐시)."""
    harness = tmp_path / "harness"
    _write_profile(harness / "profiles", "x", required_sections=["overview"])
    loader = ProfileLoader(harness_dir=harness)
    p1 = loader.load("x")
    p2 = loader.load("x")
    assert p1 is p2


def test_load_missing_profile_raises(tmp_path: Path) -> None:
    harness = tmp_path / "harness"
    (harness / "profiles").mkdir(parents=True)
    loader = ProfileLoader(harness_dir=harness)
    with pytest.raises(ProfileNotFoundError):
        loader.load("nonexistent")


def test_cannot_load_base_directly(tmp_path: Path) -> None:
    loader = ProfileLoader(harness_dir=tmp_path / "harness")
    with pytest.raises(ValueError, match="_base"):
        loader.load("_base")


# ── 로컬 override ─────────────────────────────────────────────────────


def test_local_override_wins(tmp_path: Path) -> None:
    """프로젝트 로컬 프로파일이 글로벌을 이긴다."""
    harness = tmp_path / "harness"
    project = tmp_path / "project"

    _write_profile(
        harness / "profiles",
        "stack-x",
        required_sections=["overview"],
        runtime=["from_global"],
    )
    _write_profile(
        project / ".claude" / "harness" / "profiles",
        "stack-x",
        required_sections=["overview"],
        runtime=["from_local"],
    )

    loader = ProfileLoader(harness_dir=harness, project_dir=project)
    p = loader.load("stack-x")
    assert p.whitelist.runtime == ("from_local",)


# ── 상속 (extends) ────────────────────────────────────────────────────


def test_implicit_base_inheritance(tmp_path: Path) -> None:
    """_base.md의 whitelist가 자식 프로파일에 합쳐진다."""
    harness = tmp_path / "harness"
    _write_base(harness / "profiles", runtime=["pytest"])
    _write_profile(
        harness / "profiles",
        "child",
        required_sections=["overview"],
        runtime=["fastapi"],
    )
    loader = ProfileLoader(harness_dir=harness)
    p = loader.load("child")
    # whitelist.runtime 은 합집합
    assert "pytest" in p.whitelist.runtime
    assert "fastapi" in p.whitelist.runtime


def test_explicit_extends_chain(tmp_path: Path) -> None:
    """extends 명시 — A → B → _base 체인."""
    harness = tmp_path / "harness"
    _write_base(harness / "profiles", runtime=["base_dep"])
    _write_profile(
        harness / "profiles",
        "middle",
        required_sections=["overview"],
        runtime=["middle_dep"],
    )
    _write_profile(
        harness / "profiles",
        "child",
        extends="middle",
        required_sections=["stack"],
        runtime=["child_dep"],
    )
    loader = ProfileLoader(harness_dir=harness)
    p = loader.load("child")
    assert "base_dep" in p.whitelist.runtime
    assert "middle_dep" in p.whitelist.runtime
    assert "child_dep" in p.whitelist.runtime
    # skeleton_sections.required 도 합집합
    assert "overview" in p.skeleton_sections.required
    assert "stack" in p.skeleton_sections.required


def test_cyclic_extends_raises(tmp_path: Path) -> None:
    harness = tmp_path / "harness"
    _write_profile(harness / "profiles", "a", extends="b", required_sections=["overview"])
    _write_profile(harness / "profiles", "b", extends="a", required_sections=["overview"])
    loader = ProfileLoader(harness_dir=harness)
    with pytest.raises(CyclicInheritanceError):
        loader.load("a")


def test_missing_extends_parent_falls_through_to_base(tmp_path: Path) -> None:
    """extends 가 존재하지 않는 부모를 가리키면 조용히 _base로 폴백."""
    harness = tmp_path / "harness"
    _write_base(harness / "profiles", runtime=["base_only"])
    _write_profile(
        harness / "profiles",
        "orphan",
        extends="ghost",
        required_sections=["overview"],
        runtime=["orphan_dep"],
    )
    loader = ProfileLoader(harness_dir=harness)
    p = loader.load("orphan")
    assert "base_only" in p.whitelist.runtime
    assert "orphan_dep" in p.whitelist.runtime


# ── components 병합 ───────────────────────────────────────────────────


def test_components_child_overrides_same_id(tmp_path: Path) -> None:
    """같은 component id 충돌 시 자식이 이긴다."""
    harness = tmp_path / "harness"
    _write_profile(
        harness / "profiles",
        "parent",
        required_sections=["overview"],
        components=[{"id": "core", "required": True, "skeleton_section": "core.logic"}],
    )
    _write_profile(
        harness / "profiles",
        "child",
        extends="parent",
        required_sections=["overview"],
        components=[{"id": "core", "required": False, "skeleton_section": "core.logic"}],
    )
    loader = ProfileLoader(harness_dir=harness)
    p = loader.load("child")
    cores = [c for c in p.components if c.id == "core"]
    assert len(cores) == 1
    assert cores[0].required is False  # 자식이 이김


# ── Detection ─────────────────────────────────────────────────────────


def test_detect_single_profile(tmp_path: Path) -> None:
    """code-hijack 같은 단일 backend/ CLI 프로젝트."""
    harness = tmp_path / "harness"
    project = tmp_path / "project"

    _write_profile(
        harness / "profiles",
        "python-cli",
        required_sections=["overview"],
    )
    _write_registry(
        harness,
        rules=[
            {
                "profile": "python-cli",
                "paths": [".", "backend/"],
                "detect": {
                    "files": ["pyproject.toml"],
                    "contains_any": {"pyproject.toml": ["[project.scripts]"]},
                },
            }
        ],
    )

    (project / "backend").mkdir(parents=True)
    (project / "backend" / "pyproject.toml").write_text(
        "[project.scripts]\nx = 'm:f'", encoding="utf-8"
    )

    loader = ProfileLoader(harness_dir=harness, project_dir=project)
    matches = loader.detect()
    assert len(matches) == 1
    assert matches[0].profile.id == "python-cli"
    assert matches[0].path == "backend/"


def test_detect_monorepo(tmp_path: Path) -> None:
    """backend/(fastapi) + frontend/(react-vite) 동시 매칭."""
    harness = tmp_path / "harness"
    project = tmp_path / "project"

    _write_profile(harness / "profiles", "fastapi", required_sections=["overview"])
    _write_profile(harness / "profiles", "react-vite", required_sections=["overview"])
    _write_registry(
        harness,
        rules=[
            {
                "profile": "fastapi",
                "paths": [".", "backend/"],
                "detect": {
                    "files": ["pyproject.toml"],
                    "contains": {"pyproject.toml": ["fastapi"]},
                },
            },
            {
                "profile": "react-vite",
                "paths": [".", "frontend/"],
                "detect": {
                    "files": ["package.json"],
                    "contains": {"package.json": ['"react"']},
                    "contains_any": {"package.json": ['"vite"']},
                },
            },
        ],
    )

    (project / "backend").mkdir(parents=True)
    (project / "backend" / "pyproject.toml").write_text("fastapi", encoding="utf-8")
    (project / "frontend").mkdir(parents=True)
    (project / "frontend" / "package.json").write_text(
        '{"dependencies": {"react": "*", "vite": "*"}}', encoding="utf-8"
    )

    loader = ProfileLoader(harness_dir=harness, project_dir=project)
    matches = {(m.profile.id, m.path) for m in loader.detect()}
    assert ("fastapi", "backend/") in matches
    assert ("react-vite", "frontend/") in matches


def test_detect_no_match_returns_empty(tmp_path: Path) -> None:
    harness = tmp_path / "harness"
    project = tmp_path / "project"
    project.mkdir()

    _write_profile(harness / "profiles", "x", required_sections=["overview"])
    _write_registry(
        harness,
        rules=[
            {
                "profile": "x",
                "paths": ["."],
                "detect": {"files": ["pyproject.toml"]},
            }
        ],
    )
    loader = ProfileLoader(harness_dir=harness, project_dir=project)
    assert loader.detect() == []


def test_detect_not_contains_excludes(tmp_path: Path) -> None:
    """not_contains 가 매칭을 막는다."""
    harness = tmp_path / "harness"
    project = tmp_path / "project"
    project.mkdir()

    _write_profile(harness / "profiles", "lib", required_sections=["overview"])
    _write_registry(
        harness,
        rules=[
            {
                "profile": "lib",
                "paths": ["."],
                "detect": {
                    "files": ["pyproject.toml"],
                    "not_contains": {"pyproject.toml": ["fastapi"]},
                },
            }
        ],
    )

    # case A: fastapi 포함 → 매칭 X
    (project / "pyproject.toml").write_text("fastapi", encoding="utf-8")
    loader = ProfileLoader(harness_dir=harness, project_dir=project)
    assert loader.detect() == []

    # case B: fastapi 없음 → 매칭 O
    (project / "pyproject.toml").write_text("just-a-lib", encoding="utf-8")
    loader2 = ProfileLoader(harness_dir=harness, project_dir=project)
    assert len(loader2.detect()) == 1


# ── Phase 2-b-3: 6축 답변 → 활성 섹션 결정 ─────────────────────────


def _make_profile(
    *,
    profile_id: str = "test",
    required: list[str] | None = None,
    optional: list[str] | None = None,
) -> Profile:
    """Profile 객체 직접 생성 — compute_has_keys 등 단위 테스트용."""
    req = tuple(required or [])
    opt = tuple(optional or [])
    return Profile(
        id=profile_id,
        name=profile_id.title(),
        status="confirmed",
        version=1,
        extends=None,
        paths=(),
        detect={},
        components=(),
        skeleton_sections=SkeletonSections(required=req, optional=opt, order=req + opt),
        toolchain=Toolchain(install=None, test=None, lint=None, type=None, format=None),
        whitelist=Whitelist(runtime=(), dev=(), prefix_allowed=()),
        file_structure="",
        gstack_mode="manual",
        gstack_recommended={},
        lessons_applied=(),
        body="",
        raw={},
    )


def _write_fragment(
    dir_: Path,
    frag_id: str,
    required_when: str,
    *,
    name: str | None = None,
) -> Path:
    """Fragment .md 파일 작성 — load_fragments_metadata 테스트용."""
    dir_.mkdir(parents=True, exist_ok=True)
    body = dedent(f"""\
        ---
        id: {frag_id}
        name: {name or frag_id}
        required_when: {required_when}
        description: test fragment
        ---

        ## {{{{section_number}}}}. {name or frag_id}
        """)
    path = dir_ / f"{frag_id}.md"
    path.write_text(body, encoding="utf-8")
    return path


# compute_has_keys


def test_compute_has_keys_persistence_to_storage() -> None:
    profile = _make_profile(required=["persistence"])
    loader = ProfileLoader()
    assert loader.compute_has_keys([profile]) == frozenset({"storage"})


def test_compute_has_keys_auth_to_users() -> None:
    profile = _make_profile(required=["auth"])
    loader = ProfileLoader()
    assert loader.compute_has_keys([profile]) == frozenset({"users"})


def test_compute_has_keys_multi_profile_union() -> None:
    p1 = _make_profile(profile_id="api", required=["interface.http", "persistence"])
    p2 = _make_profile(profile_id="cli", required=["interface.cli", "configuration"])
    loader = ProfileLoader()
    assert loader.compute_has_keys([p1, p2]) == frozenset(
        {"http_server", "storage", "cli_entrypoint", "env_config"}
    )


def test_compute_has_keys_unmapped_section_ignored() -> None:
    """매핑에 없는 섹션은 silently skip — has 키 추가 안 됨."""
    profile = _make_profile(required=["overview", "stack", "tasks", "notes"])
    loader = ProfileLoader()
    assert loader.compute_has_keys([profile]) == frozenset()


def test_compute_has_keys_optional_sections_also_count() -> None:
    profile = _make_profile(optional=["persistence", "auth"])
    loader = ProfileLoader()
    assert loader.compute_has_keys([profile]) == frozenset({"storage", "users"})


# compute_scale_tokens


def test_compute_scale_tokens_tiny_empty() -> None:
    loader = ProfileLoader()
    axes = ScaleAxes(user_scale="tiny")
    assert loader.compute_scale_tokens(axes) == frozenset()


def test_compute_scale_tokens_small() -> None:
    loader = ProfileLoader()
    axes = ScaleAxes(user_scale="small")
    assert loader.compute_scale_tokens(axes) == frozenset({"small_or_larger"})


def test_compute_scale_tokens_medium_includes_small() -> None:
    loader = ProfileLoader()
    axes = ScaleAxes(user_scale="medium")
    assert loader.compute_scale_tokens(axes) == frozenset({"small_or_larger", "medium_or_larger"})


def test_compute_scale_tokens_large_includes_all() -> None:
    loader = ProfileLoader()
    axes = ScaleAxes(user_scale="large")
    assert loader.compute_scale_tokens(axes) == frozenset(
        {"small_or_larger", "medium_or_larger", "large"}
    )


# load_fragments_metadata


def test_load_fragments_metadata_basic(tmp_path: Path) -> None:
    fragments_dir = tmp_path / "skeleton"
    _write_fragment(fragments_dir, "alpha", "always")
    _write_fragment(fragments_dir, "beta", "has.storage")
    loader = ProfileLoader()
    meta = loader.load_fragments_metadata(fragments_dir)
    assert meta == {"alpha": "always", "beta": "has.storage"}


def test_load_fragments_metadata_skips_files_without_frontmatter(tmp_path: Path) -> None:
    fragments_dir = tmp_path / "skeleton"
    fragments_dir.mkdir()
    (fragments_dir / "no_fm.md").write_text("# Just a heading\n", encoding="utf-8")
    _write_fragment(fragments_dir, "good", "always")
    loader = ProfileLoader()
    meta = loader.load_fragments_metadata(fragments_dir)
    assert meta == {"good": "always"}


def test_load_fragments_metadata_returns_empty_when_dir_missing(tmp_path: Path) -> None:
    loader = ProfileLoader()
    assert loader.load_fragments_metadata(tmp_path / "nonexistent") == {}


# compute_active_sections


def test_compute_active_sections_pii_activates_audit_log(tmp_path: Path) -> None:
    fragments_dir = tmp_path / "skeleton"
    _write_fragment(fragments_dir, "audit_log", "data_sensitivity in [pii, payment]")
    _write_fragment(fragments_dir, "overview", "always")
    loader = ProfileLoader()
    profile = _make_profile()
    axes = ScaleAxes(data_sensitivity="pii")
    active = loader.compute_active_sections(axes, [profile], fragments_dir)
    assert "audit_log" in active
    assert "overview" in active


def test_compute_active_sections_no_pii_excludes_audit_log(tmp_path: Path) -> None:
    fragments_dir = tmp_path / "skeleton"
    _write_fragment(fragments_dir, "audit_log", "data_sensitivity in [pii, payment]")
    _write_fragment(fragments_dir, "overview", "always")
    loader = ProfileLoader()
    profile = _make_profile()
    axes = ScaleAxes(data_sensitivity="none")
    active = loader.compute_active_sections(axes, [profile], fragments_dir)
    assert "audit_log" not in active
    assert "overview" in active


def test_compute_active_sections_lifecycle_poc_excludes_test_strategy(
    tmp_path: Path,
) -> None:
    fragments_dir = tmp_path / "skeleton"
    _write_fragment(fragments_dir, "test_strategy", "lifecycle in [mvp, ga]")
    _write_fragment(fragments_dir, "overview", "always")
    loader = ProfileLoader()
    axes = ScaleAxes(lifecycle="poc")
    active = loader.compute_active_sections(axes, [_make_profile()], fragments_dir)
    assert "test_strategy" not in active
    assert "overview" in active


def test_compute_active_sections_has_keys_from_profile(tmp_path: Path) -> None:
    """profile 의 declared persistence → has.storage atom 활성."""
    fragments_dir = tmp_path / "skeleton"
    _write_fragment(fragments_dir, "data_model", "has.storage")
    profile = _make_profile(required=["persistence"])
    loader = ProfileLoader()
    axes = ScaleAxes()
    active = loader.compute_active_sections(axes, [profile], fragments_dir)
    assert active == ["data_model"]


def test_compute_active_sections_invalid_expression_conservative_activate(
    tmp_path: Path,
) -> None:
    """invalid required_when → 보수적 활성화 (False positive)."""
    fragments_dir = tmp_path / "skeleton"
    _write_fragment(fragments_dir, "broken", "this is not a valid expression !!")
    loader = ProfileLoader()
    active = loader.compute_active_sections(ScaleAxes(), [_make_profile()], fragments_dir)
    assert "broken" in active


# ── files_any 매처 ───────────────────────────────────────────────────────


def test_detect_files_any_matches_when_one_exists(tmp_path: Path) -> None:
    """files_any: [a, b, c] — 하나라도 존재하면 매칭 (Android Gradle 케이스).

    Android Studio 프로젝트는 build.gradle.kts (Kotlin DSL) 또는 build.gradle
    (Groovy DSL) 둘 중 하나만 존재. 기존 files (AND 전용) 매처로는 표현 불가능.
    """
    harness = tmp_path / "harness"
    project = tmp_path / "project"
    project.mkdir()

    _write_profile(harness / "profiles", "android-kotlin", required_sections=["overview"])
    _write_registry(
        harness,
        rules=[
            {
                "profile": "android-kotlin",
                "paths": ["."],
                "detect": {
                    "files_any": ["build.gradle.kts", "build.gradle", "settings.gradle.kts"],
                },
            }
        ],
    )

    # case A: build.gradle.kts 만 존재 → 매칭
    (project / "build.gradle.kts").write_text("plugins {}", encoding="utf-8")
    loader = ProfileLoader(harness_dir=harness, project_dir=project)
    matches = loader.detect()
    assert len(matches) == 1
    assert matches[0].profile.id == "android-kotlin"


def test_detect_files_any_excludes_when_none_exist(tmp_path: Path) -> None:
    """files_any 의 모든 후보가 없으면 매칭 X."""
    harness = tmp_path / "harness"
    project = tmp_path / "project"
    project.mkdir()

    _write_profile(harness / "profiles", "android-kotlin", required_sections=["overview"])
    _write_registry(
        harness,
        rules=[
            {
                "profile": "android-kotlin",
                "paths": ["."],
                "detect": {
                    "files_any": ["build.gradle.kts", "build.gradle"],
                },
            }
        ],
    )

    # 후보 둘 다 없음 → 매칭 X
    (project / "README.md").write_text("not a gradle project", encoding="utf-8")
    loader = ProfileLoader(harness_dir=harness, project_dir=project)
    assert loader.detect() == []


# ── 모바일 has 키 매핑 ───────────────────────────────────────────────────


def test_compute_has_keys_includes_mobile_navigation(tmp_path: Path) -> None:
    """프로파일이 mobile.navigation 을 declared sections 에 포함 → has.navigation 활성.

    `_SECTION_TO_HAS_KEY` 에 mobile.navigation→navigation 매핑이 있으므로
    compute_has_keys 가 'navigation' 을 반환해야 함. fragment 의 `required_when:
    has.navigation` 이 정상 평가되는 전제.
    """
    profile = _make_profile(required=["overview", "mobile.navigation"])
    loader = ProfileLoader()
    keys = loader.compute_has_keys([profile])
    assert "navigation" in keys


def test_compute_has_keys_includes_mobile_build_config_and_lifecycle(tmp_path: Path) -> None:
    """mobile.build_config / mobile.lifecycle 도 매핑되어 has 키 생성."""
    profile = _make_profile(
        required=["overview", "mobile.build_config", "mobile.lifecycle"],
    )
    loader = ProfileLoader()
    keys = loader.compute_has_keys([profile])
    assert "build_config" in keys
    assert "lifecycle" in keys


def test_compute_has_keys_excludes_mobile_when_web_only_profile(tmp_path: Path) -> None:
    """Web 프로파일 (mobile.* 미선언) → mobile has 키 생성 X."""
    profile = _make_profile(required=["overview", "view.screens"])
    loader = ProfileLoader()
    keys = loader.compute_has_keys([profile])
    assert "navigation" not in keys
    assert "build_config" not in keys
    assert "lifecycle" not in keys


def test_compute_active_sections_mobile_navigation_activates_via_has_atom(
    tmp_path: Path,
) -> None:
    """End-to-end: profile 이 mobile.navigation 선언 → fragment(required_when:has.navigation)
    가 active 에 포함."""
    fragments_dir = tmp_path / "skeleton"
    _write_fragment(fragments_dir, "mobile.navigation", "has.navigation")
    profile = _make_profile(required=["overview", "mobile.navigation"])
    loader = ProfileLoader()
    active = loader.compute_active_sections(ScaleAxes(), [profile], fragments_dir)
    assert "mobile.navigation" in active


def test_compute_active_sections_mobile_navigation_excluded_for_web(
    tmp_path: Path,
) -> None:
    """Web 프로파일에서는 mobile.navigation 활성 X (잘못된 누수 방지)."""
    fragments_dir = tmp_path / "skeleton"
    _write_fragment(fragments_dir, "mobile.navigation", "has.navigation")
    profile = _make_profile(required=["overview", "view.screens"])
    loader = ProfileLoader()
    active = loader.compute_active_sections(ScaleAxes(), [profile], fragments_dir)
    assert "mobile.navigation" not in active


# ── _registry.yaml 모바일 4 룰 ──────────────────────────────────────────


def test_detect_react_native_expo_matches_with_expo_dependency(tmp_path: Path) -> None:
    """react-native-expo: package.json 에 expo 또는 react-native 포함 시 매칭."""
    harness = tmp_path / "harness"
    project = tmp_path / "project"
    project.mkdir()

    _write_profile(harness / "profiles", "react-native-expo", required_sections=["overview"])
    _write_registry(
        harness,
        rules=[
            {
                "profile": "react-native-expo",
                "paths": ["."],
                "detect": {
                    "files": ["package.json"],
                    "contains_any": {"package.json": ['"expo"', '"react-native"']},
                    "not_contains": {"package.json": ['"react-native-windows"']},
                },
            }
        ],
    )

    (project / "package.json").write_text(
        '{"dependencies": {"expo": "~52.0.0"}}', encoding="utf-8"
    )
    loader = ProfileLoader(harness_dir=harness, project_dir=project)
    matches = loader.detect()
    assert len(matches) == 1
    assert matches[0].profile.id == "react-native-expo"


def test_detect_react_native_expo_excludes_react_native_windows(tmp_path: Path) -> None:
    """RN-Windows 데스크톱 프로젝트는 react-native-expo 매칭 안 됨 (not_contains 가드)."""
    harness = tmp_path / "harness"
    project = tmp_path / "project"
    project.mkdir()

    _write_profile(harness / "profiles", "react-native-expo", required_sections=["overview"])
    _write_registry(
        harness,
        rules=[
            {
                "profile": "react-native-expo",
                "paths": ["."],
                "detect": {
                    "files": ["package.json"],
                    "contains_any": {"package.json": ['"expo"', '"react-native"']},
                    "not_contains": {"package.json": ['"react-native-windows"']},
                },
            }
        ],
    )

    (project / "package.json").write_text(
        '{"dependencies": {"react-native": "*", "react-native-windows": "*"}}',
        encoding="utf-8",
    )
    loader = ProfileLoader(harness_dir=harness, project_dir=project)
    assert loader.detect() == []


def test_detect_android_kotlin_matches_with_gradle_kts(tmp_path: Path) -> None:
    """android-kotlin: build.gradle.kts 만 있어도 매칭 (files_any OR)."""
    harness = tmp_path / "harness"
    project = tmp_path / "project"
    project.mkdir()

    _write_profile(harness / "profiles", "android-kotlin", required_sections=["overview"])
    _write_registry(
        harness,
        rules=[
            {
                "profile": "android-kotlin",
                "paths": ["."],
                "detect": {
                    "files_any": ["build.gradle.kts", "build.gradle", "settings.gradle.kts"],
                },
            }
        ],
    )

    (project / "build.gradle.kts").write_text("plugins {}", encoding="utf-8")
    loader = ProfileLoader(harness_dir=harness, project_dir=project)
    matches = loader.detect()
    assert len(matches) == 1
    assert matches[0].profile.id == "android-kotlin"


def test_detect_ios_swift_matches_with_package_swift(tmp_path: Path) -> None:
    """ios-swift: Package.swift 또는 Podfile 둘 중 하나로 매칭."""
    harness = tmp_path / "harness"
    project = tmp_path / "project"
    project.mkdir()

    _write_profile(harness / "profiles", "ios-swift", required_sections=["overview"])
    _write_registry(
        harness,
        rules=[
            {
                "profile": "ios-swift",
                "paths": ["."],
                "detect": {"files_any": ["Package.swift", "Podfile"]},
            }
        ],
    )

    (project / "Package.swift").write_text("// swift-tools-version:5.9", encoding="utf-8")
    loader = ProfileLoader(harness_dir=harness, project_dir=project)
    matches = loader.detect()
    assert len(matches) == 1
    assert matches[0].profile.id == "ios-swift"


# ── 실제 react-native-expo 프로파일 통합 ────────────────────────────────


def test_real_react_native_expo_profile_loads_with_full_schema() -> None:
    """실제 harness/profiles/react-native-expo.md 가 ProfileLoader 로 정상 로드.

    profile 파일의 frontmatter 가 schema 를 통과하고, _base 상속이 작동하며,
    whitelist / skeleton_sections / toolchain 모두 채워져 있어야 함.
    """
    repo_harness = Path(__file__).parent.parent.parent.parent / "harness"
    if not (repo_harness / "profiles" / "react-native-expo.md").exists():
        import pytest

        pytest.skip("react-native-expo profile not yet installed")
    loader = ProfileLoader(harness_dir=repo_harness)
    profile = loader.load("react-native-expo")
    assert profile.id == "react-native-expo"
    assert profile.status == "confirmed"
    # 핵심 whitelist 멤버
    assert "expo" in profile.whitelist.runtime
    assert "expo-router" in profile.whitelist.runtime
    assert "zustand" in profile.whitelist.runtime
    assert "expo-secure-store" in profile.whitelist.runtime
    # 모바일 fragment 들이 required 에 포함
    assert "mobile.navigation" in profile.skeleton_sections.required
    assert "mobile.build_config" in profile.skeleton_sections.required
    assert "mobile.lifecycle" in profile.skeleton_sections.required
    # toolchain 검증
    assert profile.toolchain.install == "bun install"
    assert profile.toolchain.test == "bun test"


def test_real_react_native_expo_detect_matches_expo_project(tmp_path: Path) -> None:
    """실제 _registry.yaml 의 react-native-expo 룰이 Expo 프로젝트와 매칭."""
    repo_harness = Path(__file__).parent.parent.parent.parent / "harness"
    if not (repo_harness / "profiles" / "react-native-expo.md").exists():
        import pytest

        pytest.skip("react-native-expo profile not yet installed")

    project = tmp_path / "expo-project"
    project.mkdir()
    (project / "package.json").write_text(
        '{"name": "test", "dependencies": {"expo": "~52.0.0", "react-native": "0.76.0"}}',
        encoding="utf-8",
    )

    loader = ProfileLoader(harness_dir=repo_harness, project_dir=project)
    matches = loader.detect()
    profile_ids = [m.profile.id for m in matches]
    assert "react-native-expo" in profile_ids


# ── 실제 flutter 프로파일 통합 ──────────────────────────────────────────


def test_real_flutter_profile_loads_with_full_schema() -> None:
    """실제 harness/profiles/flutter.md 가 ProfileLoader 로 정상 로드."""
    repo_harness = Path(__file__).parent.parent.parent.parent / "harness"
    if not (repo_harness / "profiles" / "flutter.md").exists():
        import pytest

        pytest.skip("flutter profile not yet installed")
    loader = ProfileLoader(harness_dir=repo_harness)
    profile = loader.load("flutter")
    assert profile.id == "flutter"
    assert profile.status == "confirmed"
    # 핵심 whitelist 멤버
    assert "flutter" in profile.whitelist.runtime
    assert "flutter_riverpod" in profile.whitelist.runtime
    assert "go_router" in profile.whitelist.runtime
    assert "flutter_secure_storage" in profile.whitelist.runtime
    assert "drift" in profile.whitelist.runtime
    # 모바일 fragment 들이 required 에 포함
    assert "mobile.navigation" in profile.skeleton_sections.required
    assert "mobile.build_config" in profile.skeleton_sections.required
    assert "mobile.lifecycle" in profile.skeleton_sections.required
    # toolchain 검증 — flutter analyze 가 type 검사 포함하므로 type=null
    assert profile.toolchain.install == "flutter pub get"
    assert profile.toolchain.test == "flutter test"
    assert profile.toolchain.lint == "flutter analyze"
    assert profile.toolchain.type is None


def test_real_flutter_detect_matches_pubspec_yaml(tmp_path: Path) -> None:
    """pubspec.yaml 에 flutter: 섹션 있으면 flutter 프로파일 매칭."""
    repo_harness = Path(__file__).parent.parent.parent.parent / "harness"
    if not (repo_harness / "profiles" / "flutter.md").exists():
        import pytest

        pytest.skip("flutter profile not yet installed")

    project = tmp_path / "flutter-project"
    project.mkdir()
    (project / "pubspec.yaml").write_text(
        "name: my_app\nflutter:\n  sdk: flutter\n",
        encoding="utf-8",
    )

    loader = ProfileLoader(harness_dir=repo_harness, project_dir=project)
    matches = loader.detect()
    profile_ids = [m.profile.id for m in matches]
    assert "flutter" in profile_ids


def test_real_flutter_does_not_match_dart_only_project(tmp_path: Path) -> None:
    """순수 Dart 라이브러리 (flutter: 섹션 없음) 는 flutter 프로파일 매칭 X."""
    repo_harness = Path(__file__).parent.parent.parent.parent / "harness"
    if not (repo_harness / "profiles" / "flutter.md").exists():
        import pytest

        pytest.skip("flutter profile not yet installed")

    project = tmp_path / "dart-only"
    project.mkdir()
    (project / "pubspec.yaml").write_text(
        "name: pure_dart\nenvironment:\n  sdk: '>=3.0.0 <4.0.0'\n",
        encoding="utf-8",
    )

    loader = ProfileLoader(harness_dir=repo_harness, project_dir=project)
    matches = loader.detect()
    profile_ids = [m.profile.id for m in matches]
    assert "flutter" not in profile_ids


# ── 실제 android-kotlin + ios-swift 프로파일 통합 ───────────────────────


def test_real_android_kotlin_profile_loads_with_full_schema() -> None:
    """실제 harness/profiles/android-kotlin.md 가 ProfileLoader 로 정상 로드."""
    repo_harness = Path(__file__).parent.parent.parent.parent / "harness"
    if not (repo_harness / "profiles" / "android-kotlin.md").exists():
        import pytest

        pytest.skip("android-kotlin profile not yet installed")
    loader = ProfileLoader(harness_dir=repo_harness)
    profile = loader.load("android-kotlin")
    assert profile.id == "android-kotlin"
    assert profile.status == "confirmed"
    # 핵심 whitelist 멤버
    assert "androidx.compose" in profile.whitelist.runtime
    assert "androidx.room" in profile.whitelist.runtime
    assert "com.squareup.retrofit2" in profile.whitelist.runtime
    assert "com.google.dagger" in profile.whitelist.runtime
    # mobile fragments required
    assert "mobile.navigation" in profile.skeleton_sections.required
    assert "mobile.build_config" in profile.skeleton_sections.required
    assert "mobile.lifecycle" in profile.skeleton_sections.required
    # toolchain
    assert profile.toolchain.install == "./gradlew --refresh-dependencies"
    assert profile.toolchain.test == "./gradlew test"
    assert profile.toolchain.lint == "./gradlew ktlintCheck"


def test_real_android_detect_matches_gradle_kts(tmp_path: Path) -> None:
    """build.gradle.kts 만 있어도 android-kotlin 매칭 (files_any OR)."""
    repo_harness = Path(__file__).parent.parent.parent.parent / "harness"
    if not (repo_harness / "profiles" / "android-kotlin.md").exists():
        import pytest

        pytest.skip("android-kotlin profile not yet installed")

    project = tmp_path / "android-app"
    project.mkdir()
    (project / "build.gradle.kts").write_text("plugins {}", encoding="utf-8")

    loader = ProfileLoader(harness_dir=repo_harness, project_dir=project)
    matches = loader.detect()
    profile_ids = [m.profile.id for m in matches]
    assert "android-kotlin" in profile_ids


def test_real_ios_swift_profile_loads_with_full_schema() -> None:
    """실제 harness/profiles/ios-swift.md 가 ProfileLoader 로 정상 로드.

    Windows 호스트 제약 — toolchain.test = null (macOS 에서만 xcodebuild test).
    """
    repo_harness = Path(__file__).parent.parent.parent.parent / "harness"
    if not (repo_harness / "profiles" / "ios-swift.md").exists():
        import pytest

        pytest.skip("ios-swift profile not yet installed")
    loader = ProfileLoader(harness_dir=repo_harness)
    profile = loader.load("ios-swift")
    assert profile.id == "ios-swift"
    assert profile.status == "confirmed"
    # 핵심 whitelist (Apple SPM packages)
    assert "swift-collections" in profile.whitelist.runtime
    assert "keychain-access" in profile.whitelist.runtime
    assert "swiftlint" in profile.whitelist.dev
    # mobile fragments required
    assert "mobile.navigation" in profile.skeleton_sections.required
    assert "mobile.build_config" in profile.skeleton_sections.required
    assert "mobile.lifecycle" in profile.skeleton_sections.required
    # toolchain — Windows host 제약: test=null, type=swift build
    assert profile.toolchain.install == "swift package resolve"
    assert profile.toolchain.test is None
    assert profile.toolchain.lint == "swiftlint lint --strict"
    assert profile.toolchain.type == "swift build"


def test_real_ios_swift_detect_matches_package_swift(tmp_path: Path) -> None:
    """Package.swift 만 있어도 ios-swift 매칭 (files_any OR)."""
    repo_harness = Path(__file__).parent.parent.parent.parent / "harness"
    if not (repo_harness / "profiles" / "ios-swift.md").exists():
        import pytest

        pytest.skip("ios-swift profile not yet installed")

    project = tmp_path / "ios-app"
    project.mkdir()
    (project / "Package.swift").write_text("// swift-tools-version:5.9", encoding="utf-8")

    loader = ProfileLoader(harness_dir=repo_harness, project_dir=project)
    matches = loader.detect()
    profile_ids = [m.profile.id for m in matches]
    assert "ios-swift" in profile_ids


def test_real_ios_swift_detect_matches_podfile(tmp_path: Path) -> None:
    """Podfile 도 ios-swift 매칭 (files_any 두번째 후보)."""
    repo_harness = Path(__file__).parent.parent.parent.parent / "harness"
    if not (repo_harness / "profiles" / "ios-swift.md").exists():
        import pytest

        pytest.skip("ios-swift profile not yet installed")

    project = tmp_path / "ios-app-pods"
    project.mkdir()
    (project / "Podfile").write_text("platform :ios, '16.0'", encoding="utf-8")

    loader = ProfileLoader(harness_dir=repo_harness, project_dir=project)
    matches = loader.detect()
    profile_ids = [m.profile.id for m in matches]
    assert "ios-swift" in profile_ids
