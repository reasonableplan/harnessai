"""profile_loader 단위 테스트.

모든 픽스처는 tmp_path 기반 — 사용자 환경 ~/.claude/harness/ 비의존.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from src.orchestrator.capabilities import KNOWN_CAPABILITY_ATOMS as _KNOWN_CAPABILITY_ATOMS
from src.orchestrator.plan_manager import ScaleAxes
from src.orchestrator.profile_loader import (
    CyclicInheritanceError,
    Profile,
    ProfileLoader,
    ProfileNotFoundError,
    SkeletonSections,
    Toolchain,
    Whitelist,
    derive_axes_capabilities,
    extract_known_lessons,
    find_unknown_lesson_references,
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


def test_missing_extends_parent_falls_through_to_base(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """extends 가 존재하지 않는 부모를 가리키면 _base 로 폴백 + stderr 경고.

    폴백 자체는 유지하되 조용히 넘어가면 부모의 whitelist/toolchain 누락이
    다운스트림 보안 검사 false-negative 로 이어진다 (review H3) — 경고 필수.
    """
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
    err = capsys.readouterr().err
    assert "[WARN]" in err
    assert "ghost" in err


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
    provides_capabilities: list[str] | None = None,
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
        provides_capabilities=tuple(provides_capabilities) if provides_capabilities else (),
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
    """provides_capabilities 로 storage 선언 → has.storage 활성."""
    profile = _make_profile(provides_capabilities=["storage"])
    loader = ProfileLoader()
    assert loader.compute_has_keys([profile]) == frozenset({"storage"})


def test_compute_has_keys_auth_to_users() -> None:
    """provides_capabilities 로 users 선언 → has.users 활성."""
    profile = _make_profile(provides_capabilities=["users"])
    loader = ProfileLoader()
    assert loader.compute_has_keys([profile]) == frozenset({"users"})


def test_compute_has_keys_multi_profile_union() -> None:
    """여러 프로파일의 provides_capabilities 가 union 됨."""
    p1 = _make_profile(profile_id="api", provides_capabilities=["http_server", "storage"])
    p2 = _make_profile(profile_id="cli", provides_capabilities=["cli_entrypoint", "env_config"])
    loader = ProfileLoader()
    assert loader.compute_has_keys([p1, p2]) == frozenset(
        {"http_server", "storage", "cli_entrypoint", "env_config"}
    )


def test_compute_has_keys_unmapped_section_ignored() -> None:
    """매핑에 없는 섹션은 silently skip — has 키 추가 안 됨."""
    profile = _make_profile(required=["overview", "stack", "tasks", "notes"])
    loader = ProfileLoader()
    assert loader.compute_has_keys([profile]) == frozenset()


def test_compute_has_keys_optional_sections_not_counted() -> None:
    """optional 섹션은 has 키에 포함되지 않아야 함 — paired-mode 후보이지 활성 선언 아님.

    결함 #1 회귀 방지: optional 에 있는 interface.http 가 has.http_server 를
    트리거하면 mobile-only 프로젝트에 백엔드 섹션이 잘못 포함됨.
    """
    profile = _make_profile(optional=["persistence", "auth"])
    loader = ProfileLoader()
    assert loader.compute_has_keys([profile]) == frozenset()


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
    active, _trace = loader.compute_active_sections(axes, [profile], fragments_dir)
    assert "audit_log" in active
    assert "overview" in active


_ENV_EXPR = (
    "(has.http_server or has.cli_entrypoint) "
    "and (lifecycle in [mvp, ga] or availability in [standard, high])"
)


def test_environments_excluded_for_poc_casual_toy(tmp_path: Path) -> None:
    """dogfood #3: 진입점은 있으나 poc+casual 인 장난감 → environments 미활성."""
    fragments_dir = tmp_path / "skeleton"
    _write_fragment(fragments_dir, "environments", _ENV_EXPR)
    _write_fragment(fragments_dir, "overview", "always")
    loader = ProfileLoader()
    profile = _make_profile(provides_capabilities=["cli_entrypoint"])
    axes = ScaleAxes(lifecycle="poc", availability="casual")
    active, _trace = loader.compute_active_sections(axes, [profile], fragments_dir)
    assert "environments" not in active


def test_environments_included_for_mvp(tmp_path: Path) -> None:
    """진입점 + mvp → environments 활성 (dev/staging/prod 필요)."""
    fragments_dir = tmp_path / "skeleton"
    _write_fragment(fragments_dir, "environments", _ENV_EXPR)
    loader = ProfileLoader()
    profile = _make_profile(provides_capabilities=["cli_entrypoint"])
    axes = ScaleAxes(lifecycle="mvp", availability="casual")
    active, _trace = loader.compute_active_sections(axes, [profile], fragments_dir)
    assert "environments" in active


def test_environments_included_for_poc_but_standard_availability(tmp_path: Path) -> None:
    """poc 라도 availability=standard 면 environments 활성 (운영 관심사)."""
    fragments_dir = tmp_path / "skeleton"
    _write_fragment(fragments_dir, "environments", _ENV_EXPR)
    loader = ProfileLoader()
    profile = _make_profile(provides_capabilities=["cli_entrypoint"])
    axes = ScaleAxes(lifecycle="poc", availability="standard")
    active, _trace = loader.compute_active_sections(axes, [profile], fragments_dir)
    assert "environments" in active


def test_environments_excluded_for_serverless_mobile(tmp_path: Path) -> None:
    """dogfood 운동앱: 서버 없는 모바일(ui+navigation, http_server/cli 없음) → environments 미활성.

    CORS/보안헤더/서버 배포 환경은 HTTP 서버 전제 개념 — 모바일 환경 분리는
    mobile.build_config 가 전담한다.
    """
    fragments_dir = tmp_path / "skeleton"
    _write_fragment(fragments_dir, "environments", _ENV_EXPR)
    loader = ProfileLoader()
    profile = _make_profile(provides_capabilities=["ui", "navigation", "build_config"])
    axes = ScaleAxes(lifecycle="mvp", availability="standard")
    active, _trace = loader.compute_active_sections(axes, [profile], fragments_dir)
    assert "environments" not in active


def test_environments_included_for_http_server(tmp_path: Path) -> None:
    """풀스택(http_server) → environments 활성 (CORS/보안헤더/env 분리 유효)."""
    fragments_dir = tmp_path / "skeleton"
    _write_fragment(fragments_dir, "environments", _ENV_EXPR)
    loader = ProfileLoader()
    profile = _make_profile(provides_capabilities=["http_server", "ui"])
    axes = ScaleAxes(lifecycle="mvp", availability="casual")
    active, _trace = loader.compute_active_sections(axes, [profile], fragments_dir)
    assert "environments" in active


def test_compute_active_sections_no_pii_excludes_audit_log(tmp_path: Path) -> None:
    fragments_dir = tmp_path / "skeleton"
    _write_fragment(fragments_dir, "audit_log", "data_sensitivity in [pii, payment]")
    _write_fragment(fragments_dir, "overview", "always")
    loader = ProfileLoader()
    profile = _make_profile()
    axes = ScaleAxes(data_sensitivity="none")
    active, _trace = loader.compute_active_sections(axes, [profile], fragments_dir)
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
    active, _trace = loader.compute_active_sections(axes, [_make_profile()], fragments_dir)
    assert "test_strategy" not in active
    assert "overview" in active


def test_compute_active_sections_has_keys_from_profile(tmp_path: Path) -> None:
    """profile 의 provides_capabilities=["storage"] → has.storage atom 활성."""
    fragments_dir = tmp_path / "skeleton"
    _write_fragment(fragments_dir, "data_model", "has.storage")
    profile = _make_profile(provides_capabilities=["storage"])
    loader = ProfileLoader()
    axes = ScaleAxes()
    active, _trace = loader.compute_active_sections(axes, [profile], fragments_dir)
    assert active == ["data_model"]


def test_compute_active_sections_invalid_expression_raises(
    tmp_path: Path,
) -> None:
    """Group 5 Step 3 — invalid required_when 은 fail-fast (raise).

    이전 동작 (보수적 활성화 + stderr 경고) 은 typo 를 silently 숨기는 결함.
    이제 ExpressionParseError 를 raise 하여 fragment 작성 버그를 즉시 노출.
    """
    from src.orchestrator.scale_expression import ExpressionParseError as _PE

    fragments_dir = tmp_path / "skeleton"
    _write_fragment(fragments_dir, "broken", "this is not a valid expression !!")
    loader = ProfileLoader()
    with pytest.raises(_PE, match="broken"):
        loader.compute_active_sections(ScaleAxes(), [_make_profile()], fragments_dir)


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
    """모바일 프로파일이 provides_capabilities 에 navigation 선언 → has.navigation 활성.

    legacy _SECTION_TO_HAS_KEY 제거 후에는 provides_capabilities 가 단일 출처.
    fragment 의 `required_when: has.navigation` 이 정상 평가되는 전제.
    """
    profile = _make_profile(
        provides_capabilities=["ui", "navigation", "lifecycle", "build_config"],
    )
    loader = ProfileLoader()
    keys = loader.compute_has_keys([profile])
    assert "navigation" in keys


def test_compute_has_keys_includes_mobile_build_config_and_lifecycle(tmp_path: Path) -> None:
    """build_config / lifecycle 도 provides_capabilities 로 선언 → has 키 생성."""
    profile = _make_profile(
        provides_capabilities=["ui", "build_config", "lifecycle"],
    )
    loader = ProfileLoader()
    keys = loader.compute_has_keys([profile])
    assert "build_config" in keys
    assert "lifecycle" in keys


def test_compute_has_keys_excludes_mobile_when_web_only_profile(tmp_path: Path) -> None:
    """Web 프로파일은 navigation/build_config/lifecycle 미선언 → mobile has 키 생성 X."""
    profile = _make_profile(provides_capabilities=["ui", "http_server"])
    loader = ProfileLoader()
    keys = loader.compute_has_keys([profile])
    assert "navigation" not in keys
    assert "build_config" not in keys
    assert "lifecycle" not in keys


def test_compute_active_sections_mobile_navigation_activates_via_has_atom(
    tmp_path: Path,
) -> None:
    """End-to-end: profile 이 provides_capabilities=["navigation"] 선언 →
    fragment(required_when:has.navigation) 가 active 에 포함."""
    fragments_dir = tmp_path / "skeleton"
    _write_fragment(fragments_dir, "mobile.navigation", "has.navigation")
    profile = _make_profile(provides_capabilities=["ui", "navigation"])
    loader = ProfileLoader()
    active, _trace = loader.compute_active_sections(ScaleAxes(), [profile], fragments_dir)
    assert "mobile.navigation" in active


def test_compute_active_sections_mobile_navigation_excluded_for_web(
    tmp_path: Path,
) -> None:
    """Web 프로파일에서는 mobile.navigation 활성 X (잘못된 누수 방지)."""
    fragments_dir = tmp_path / "skeleton"
    _write_fragment(fragments_dir, "mobile.navigation", "has.navigation")
    profile = _make_profile(required=["overview", "view.screens"])
    loader = ProfileLoader()
    active, _trace = loader.compute_active_sections(ScaleAxes(), [profile], fragments_dir)
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

    (project / "package.json").write_text('{"dependencies": {"expo": "~52.0.0"}}', encoding="utf-8")
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
    # bun test ≠ bun run test: bun's built-in runner vs package.json scripts.test (jest)
    assert profile.toolchain.test == "bun run test"


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


# ── 결함 #1 / #3 회귀 테스트 ────────────────────────────────────────────


def test_compute_has_keys_excludes_optional_interface_http() -> None:
    """결함 #1 회귀 방지 — react-native-expo 의 optional interface.http 가
    has.http_server 를 트리거해서는 안 됨.

    실제 react-native-expo.md 프로파일을 로드해 검증. optional 에 interface.http 가
    있더라도 compute_has_keys 결과에 'http_server' 가 없어야 mobile-only 프로젝트에서
    백엔드 전용 섹션(rate_limiting, slo 등)이 잘못 포함되지 않음.
    """
    repo_harness = Path(__file__).parent.parent.parent.parent / "harness"
    if not (repo_harness / "profiles" / "react-native-expo.md").exists():
        import pytest

        pytest.skip("react-native-expo profile not yet installed")

    loader = ProfileLoader(harness_dir=repo_harness)
    profile = loader.load("react-native-expo")
    # Confirm the profile actually has interface.http in optional (precondition)
    assert "interface.http" in profile.skeleton_sections.optional, (
        "precondition: react-native-expo should list interface.http in optional"
    )
    keys = loader.compute_has_keys([profile])
    assert "http_server" not in keys, (
        "optional interface.http must not trigger has.http_server — "
        "this would activate backend-only fragments in mobile-only projects"
    )


def test_compute_has_keys_required_triggers_for_backend() -> None:
    """결함 #1 정상 동작 보장 — fastapi 의 required interface.http 가
    has.http_server 를 포함해야 함.

    실제 fastapi.md 프로파일을 로드해 검증. required 에 interface.http 가 있으므로
    compute_has_keys 결과에 'http_server' 가 있어야 백엔드 전용 섹션이 정상 활성됨.
    """
    repo_harness = Path(__file__).parent.parent.parent.parent / "harness"
    if not (repo_harness / "profiles" / "fastapi.md").exists():
        import pytest

        pytest.skip("fastapi profile not yet installed")

    loader = ProfileLoader(harness_dir=repo_harness)
    profile = loader.load("fastapi")
    # Confirm the profile has interface.http in required (precondition)
    assert "interface.http" in profile.skeleton_sections.required, (
        "precondition: fastapi should list interface.http in required"
    )
    keys = loader.compute_has_keys([profile])
    assert "http_server" in keys, "fastapi required interface.http must trigger has.http_server"


def test_compute_active_sections_mobile_only_excludes_rate_limiting(tmp_path: Path) -> None:
    """챙겼니 회귀 케이스 — react-native-expo 단독, 6축 medium/pii/small/standard/none/mvp.

    mobile-only 프로젝트에서 rate_limiting / slo fragment 가 활성되어서는 안 됨.
    결함 #1 (optional interface.http → has.http_server 오판) 수정이 실제로
    이 케이스를 막는지 검증.
    """
    repo_harness = Path(__file__).parent.parent.parent.parent / "harness"
    fragments_dir = repo_harness / "templates" / "skeleton"
    if not (repo_harness / "profiles" / "react-native-expo.md").exists():
        import pytest

        pytest.skip("react-native-expo profile not yet installed")
    if not fragments_dir.exists():
        import pytest

        pytest.skip("harness skeleton fragments not yet installed")

    loader = ProfileLoader(harness_dir=repo_harness)
    profile = loader.load("react-native-expo")
    axes = ScaleAxes(
        user_scale="medium",
        data_sensitivity="pii",
        team_size="small",
        availability="standard",
        monetization="none",
        lifecycle="mvp",
    )
    active, _trace = loader.compute_active_sections(axes, [profile], fragments_dir)
    assert "rate_limiting" not in active, (
        "rate_limiting must not activate for mobile-only react-native-expo — "
        "it requires has.http_server which optional interface.http must not trigger"
    )
    # Note: slo activates on scale.medium_or_larger regardless of profile type —
    # that is correct behavior. Only http_server-gated fragments (rate_limiting)
    # must be absent in mobile-only mode.


def test_compute_active_sections_paired_includes_rate_limiting(tmp_path: Path) -> None:
    """paired 모드 (fastapi + react-native-expo) 에서 rate_limiting 이 활성되어야 함.

    fastapi 의 required interface.http → has.http_server → rate_limiting 트리거.
    결함 #1 수정이 paired 모드의 정상 동작을 깨지 않았는지 검증.
    """
    repo_harness = Path(__file__).parent.parent.parent.parent / "harness"
    fragments_dir = repo_harness / "templates" / "skeleton"
    for fname in ("fastapi.md", "react-native-expo.md"):
        if not (repo_harness / "profiles" / fname).exists():
            import pytest

            pytest.skip(f"{fname} profile not yet installed")
    if not fragments_dir.exists():
        import pytest

        pytest.skip("harness skeleton fragments not yet installed")

    loader = ProfileLoader(harness_dir=repo_harness)
    fastapi_profile = loader.load("fastapi")
    rne_profile = loader.load("react-native-expo")
    axes = ScaleAxes(
        user_scale="medium",
        data_sensitivity="pii",
        team_size="small",
        availability="standard",
        monetization="none",
        lifecycle="mvp",
    )
    active, _trace = loader.compute_active_sections(
        axes, [fastapi_profile, rne_profile], fragments_dir
    )
    assert "rate_limiting" in active, (
        "rate_limiting must activate in paired fastapi+react-native-expo mode — "
        "fastapi required interface.http triggers has.http_server"
    )


def test_compute_active_sections_parse_error_raises_with_frag_id(
    tmp_path: Path,
) -> None:
    """Group 5 Step 3 — fail-fast: invalid required_when 시 ExpressionParseError raise.

    이전엔 stderr 경고 + 보수적 활성화 (silent activation). 이제는 fragment 작성
    버그를 즉시 노출하기 위해 fail-fast. 에러 메시지에 frag_id 포함되어
    실제 어느 fragment 가 문제인지 즉시 파악 가능.
    """
    from src.orchestrator.scale_expression import ExpressionParseError as _PE

    fragments_dir = tmp_path / "skeleton"
    frag_id = "broken_fragment"
    _write_fragment(fragments_dir, frag_id, "this is not valid syntax @#$")
    _write_fragment(fragments_dir, "normal", "always")

    loader = ProfileLoader()
    with pytest.raises(_PE, match=frag_id):
        loader.compute_active_sections(ScaleAxes(), [_make_profile()], fragments_dir)


# ── 결함 #2 회귀 테스트: activation_trace ───────────────────────────────────


def test_compute_active_sections_returns_trace(tmp_path: Path) -> None:
    """compute_active_sections 가 (list, dict) 튜플을 반환하는지 검증.

    trace dict 의 key 가 active list 와 동일하고,
    각 value 가 fragment 의 원본 required_when 문자열인지 확인.
    """
    fragments_dir = tmp_path / "skeleton"
    _write_fragment(fragments_dir, "core.logic", "always")
    _write_fragment(fragments_dir, "overview", "always")
    _write_fragment(fragments_dir, "data_model", "has.storage")  # inactive — no storage profile
    loader = ProfileLoader()
    profile = _make_profile()  # no required sections → no has keys
    axes = ScaleAxes()

    result = loader.compute_active_sections(axes, [profile], fragments_dir)

    assert isinstance(result, tuple), "반환값이 tuple 이어야 함"
    assert len(result) == 2, "tuple 길이가 2 이어야 함"
    active, trace = result
    assert isinstance(active, list)
    assert isinstance(trace, dict)

    # trace keys == active set
    assert set(trace.keys()) == set(active), "trace 의 key 가 active list 와 동일해야 함"

    # active fragments have correct required_when values in trace
    assert trace.get("core.logic") == "always"
    assert trace.get("overview") == "always"
    # inactive fragment must not appear in trace
    assert "data_model" not in trace


# Group 5 Step 3: parse-error trace 테스트 제거됨 — fail-fast 정책으로 trace 자체가
# 안 만들어짐. raise 동작은 test_compute_active_sections_parse_error_raises_with_frag_id
# 가 보호.


def test_compute_active_sections_paired_trace_has_both_triggers(tmp_path: Path) -> None:
    """fastapi + react-native-expo paired 모드에서 rate_limiting trace 가 올바른 표현식을 담는지.

    실제 harness skeleton fragments 가 없는 환경에서는 fake fragments 로 검증.
    rate_limiting fragment 의 required_when 이 trace 에 기록되어야 함.
    """
    fragments_dir = tmp_path / "skeleton"
    rate_limiting_expr = "has.http_server"
    _write_fragment(fragments_dir, "rate_limiting", rate_limiting_expr)
    _write_fragment(fragments_dir, "overview", "always")

    # fastapi profile provides http_server capability
    fastapi_profile = _make_profile(profile_id="fastapi", provides_capabilities=["http_server"])
    # mobile profile — no http_server capability
    rne_profile = _make_profile(
        profile_id="react-native-expo", provides_capabilities=["ui", "navigation"]
    )
    loader = ProfileLoader()
    axes = ScaleAxes(user_scale="medium")

    active, trace = loader.compute_active_sections(
        axes, [fastapi_profile, rne_profile], fragments_dir
    )

    assert "rate_limiting" in active, (
        "has.http_server 조건이 충족되어 rate_limiting 이 활성되어야 함"
    )
    assert trace["rate_limiting"] == rate_limiting_expr, (
        f"trace['rate_limiting'] == {rate_limiting_expr!r} 이어야 함, 실제: {trace['rate_limiting']!r}"
    )


# ── find_consistency_violations 테스트 ────────────────────────────────


from src.orchestrator.profile_loader import (  # noqa: E402
    find_consistency_violations,
)


def test_find_violations_mobile_only_with_interface_http() -> None:
    """챙겼니 케이스: react-native-expo 단독 + interface.http 활성 → violation 1개."""
    trace = {
        "interface.http": "has.http_server",
        "overview": "always",
    }
    rne_profile = _make_profile(profile_id="react-native-expo", required=["mobile.navigation"])

    violations = find_consistency_violations(trace, [rne_profile])

    assert len(violations) == 1, f"violation 1개 기대, 실제: {violations}"
    v = violations[0]
    assert v.section_id == "interface.http"
    assert v.missing_atom == "http_server"
    assert set(v.expected_providers) == {"fastapi", "nestjs", "nextjs"}


def test_find_violations_paired_no_violations() -> None:
    """fastapi + react-native-expo paired — http_server 제공됨, violation 없음."""
    trace = {
        "interface.http": "has.http_server",
        "overview": "always",
    }
    fastapi_profile = _make_profile(profile_id="fastapi", required=["interface.http"])
    rne_profile = _make_profile(profile_id="react-native-expo", required=["mobile.navigation"])

    violations = find_consistency_violations(trace, [fastapi_profile, rne_profile])

    assert violations == [], f"violation 없어야 함, 실제: {violations}"


def test_find_violations_unmapped_atom_skipped() -> None:
    """has.ui 는 _HAS_KEY_PROVIDERS 에 매핑 없음 — signal 아님, violation 없음."""
    trace = {"view.screens": "has.ui"}
    rne_profile = _make_profile(profile_id="react-native-expo", required=["mobile.navigation"])

    violations = find_consistency_violations(trace, [rne_profile])

    assert violations == [], (
        f"unmapped atom 은 signal 아님 — violation 없어야 함, 실제: {violations}"
    )


def test_find_violations_multiple_atoms_or_expression() -> None:
    """OR 표현식: has.http_server or has.ui or has.navigation or has.cli_entrypoint.

    has.ui / has.navigation 은 _HAS_KEY_PROVIDERS 에 매핑 없음 (unmapped) →
    always True 로 처리 → 표현식 True → violation 없음.
    (has.http_server, has.cli_entrypoint 누락이지만 OR 이므로 만족)
    """
    expr = "has.http_server or has.ui or has.navigation or has.cli_entrypoint"
    trace = {"environments": expr}
    rne_profile = _make_profile(profile_id="react-native-expo")

    violations = find_consistency_violations(trace, [rne_profile])

    assert violations == [], (
        f"OR 표현식에서 unmapped atom(ui/navigation) 만족 시 violation 없어야 함, 실제: {violations}"
    )


def test_find_violations_sorted_output() -> None:
    """violations 결과가 (section_id, missing_atom) 기준으로 정렬됨."""
    trace = {
        "interface.http": "has.http_server",
        "interface.cli": "has.cli_entrypoint",
    }
    # 프로파일 없음 — 둘 다 위반
    violations = find_consistency_violations(trace, [])

    assert len(violations) == 2, f"2개 violation 기대, 실제: {violations}"
    # (section_id, missing_atom) 기준 정렬 확인
    keys = [(v.section_id, v.missing_atom) for v in violations]
    assert keys == sorted(keys), f"정렬 안 됨: {keys}"


# ── _HAS_KEY_PROVIDERS 갱신 회귀 테스트 (Step 3) ─────────────────────────────


def test_find_violations_nextjs_provides_http_server() -> None:
    """nextjs 가 _HAS_KEY_PROVIDERS["http_server"] 에 포함됨 — violation 없음.

    nextjs: RSC + Server Actions + Route Handlers 가 HTTP 표면 제공.
    Step 3 에서 nextjs 추가; 이 테스트가 제거되면 회귀 발생.
    """
    trace = {"interface.http": "has.http_server"}
    nextjs_profile = _make_profile(profile_id="nextjs")

    violations = find_consistency_violations(trace, [nextjs_profile])

    assert violations == [], (
        f"nextjs 는 http_server 제공자 — violation 없어야 함, 실제: {violations}"
    )


def test_find_violations_nextjs_in_expected_providers() -> None:
    """react-vite 단독 (http_server 미제공) → violation 의 expected_providers 에 nextjs 포함."""
    trace = {"interface.http": "has.http_server"}
    react_vite_profile = _make_profile(profile_id="react-vite")

    violations = find_consistency_violations(trace, [react_vite_profile])

    assert len(violations) == 1, f"violation 1개 기대, 실제: {violations}"
    assert "nextjs" in set(violations[0].expected_providers), (
        f"nextjs 가 expected_providers 에 없음: {violations[0].expected_providers}"
    )


def test_find_violations_electron_provides_ipc() -> None:
    """electron 이 _HAS_KEY_PROVIDERS["ipc"] 에 포함됨 — violation 없음.

    electron: main-process IPC bridge (contextBridge / ipcMain) 가 ipc 표면 제공.
    Step 3 에서 electron 추가 (이전: frozenset() → 빈 셋이라 항상 satisfied).
    """
    trace = {"interface.ipc": "has.ipc"}
    electron_profile = _make_profile(profile_id="electron")

    violations = find_consistency_violations(trace, [electron_profile])

    assert violations == [], f"electron 은 ipc 제공자 — violation 없어야 함, 실제: {violations}"


def test_find_violations_electron_in_expected_providers_for_ipc() -> None:
    """react-vite 단독 (ipc 미제공) → violation 의 expected_providers 에 electron 포함."""
    trace = {"interface.ipc": "has.ipc"}
    react_vite_profile = _make_profile(profile_id="react-vite")

    violations = find_consistency_violations(trace, [react_vite_profile])

    assert len(violations) == 1, f"violation 1개 기대, 실제: {violations}"
    assert "electron" in set(violations[0].expected_providers), (
        f"electron 이 expected_providers 에 없음: {violations[0].expected_providers}"
    )


def test_find_violations_external_capabilities_excludes_violation() -> None:
    """external_capabilities 에 http_server 선언 → interface.http violation 제거.

    Group 1-D 핵심 케이스: react-native-expo 만 있는 프로젝트가 Firebase 사용 시
    http_server 를 external_capabilities 로 명시하면 violation 이 사라져야 한다.
    """
    trace = {"interface.http": "has.http_server"}
    rne_profile = _make_profile(profile_id="react-native-expo", required=["mobile.navigation"])

    # Without external_capabilities — violation expected
    violations_without = find_consistency_violations(trace, [rne_profile])
    assert len(violations_without) == 1, (
        f"사전 조건 실패: violation 1개 기대, 실제: {violations_without}"
    )

    # With external_capabilities=[http_server] — violation should disappear
    violations_with = find_consistency_violations(
        trace, [rne_profile], external_capabilities=frozenset({"http_server"})
    )
    assert violations_with == [], (
        f"external_capabilities 명시 시 violation 없어야 함, 실제: {violations_with}"
    )


def test_find_violations_external_subset_does_not_satisfy() -> None:
    """external_capabilities 에 users 만 명시 — http_server 위반은 그대로.

    external 이 다른 atom 을 명시해도 http_server 누락은 해결되지 않는다.
    """
    trace = {"interface.http": "has.http_server"}
    rne_profile = _make_profile(profile_id="react-native-expo", required=["mobile.navigation"])

    violations = find_consistency_violations(
        trace, [rne_profile], external_capabilities=frozenset({"users"})
    )
    assert len(violations) == 1, (
        f"users 만 외부 선언 시 http_server violation 은 그대로여야 함, 실제: {violations}"
    )
    assert violations[0].missing_atom == "http_server"


# ── LESSON 검증 ──────────────────────────────────────────────────────────────


def test_extract_known_lessons_parses_actual_file() -> None:
    """실제 shared-lessons.md 에서 LESSON ID 를 추출한다.

    결과가 빈 셋이 아니고 알려진 ID 가 포함돼야 함.
    결함 #D 회귀 방지: 파싱 패턴이 실제 파일 형식과 맞아야 false-negative 없음.
    """
    lessons_path = Path(__file__).resolve().parents[2] / "docs" / "shared-lessons.md"
    assert lessons_path.exists(), f"shared-lessons.md 없음: {lessons_path}"

    known = extract_known_lessons(lessons_path)

    assert len(known) > 0, "LESSON ID 가 하나도 추출되지 않음 — 파싱 패턴 확인 필요"
    # 실제 파일에 정의된 ID 샘플 확인
    assert "LESSON-022" in known, f"LESSON-022 누락. 추출된 ID: {sorted(known)}"
    assert "LESSON-027" in known, f"LESSON-027 누락. 추출된 ID: {sorted(known)}"


def test_extract_known_lessons_missing_file_returns_empty(tmp_path: Path) -> None:
    """존재하지 않는 경로 → 빈 frozenset (예외 발생 X)."""
    result = extract_known_lessons(tmp_path / "nonexistent.md")
    assert result == frozenset()


def test_find_unknown_references_typo_detected() -> None:
    """zero-padded 안 된 LESSON-22, 존재하지 않는 LESSON-999 모두 감지."""
    body = "설계 시 LESSON-22 와 LESSON-999 를 참고했다."
    known: frozenset[str] = frozenset({"LESSON-022", "LESSON-027"})

    result = find_unknown_lesson_references(body, known)

    assert len(result) == 2
    ids = [r.lesson_id for r in result]
    assert "LESSON-22" in ids
    assert "LESSON-999" in ids
    # 정렬 확인
    assert ids == sorted(ids)


def test_find_unknown_references_count_occurrences() -> None:
    """같은 미정의 ID 가 3회 등장 → occurrences=3."""
    body = "LESSON-999 참고. 그리고 LESSON-999 도 참고. 마지막으로 LESSON-999."
    known: frozenset[str] = frozenset({"LESSON-022"})

    result = find_unknown_lesson_references(body, known)

    assert len(result) == 1
    assert result[0].lesson_id == "LESSON-999"
    assert result[0].occurrences == 3


def test_find_unknown_references_case_sensitive() -> None:
    """소문자 lesson-022 는 매칭하지 않는다 (대소문자 구분)."""
    body = "lesson-022 를 참고했다."
    known: frozenset[str] = frozenset()  # 어떤 ID 도 known 에 없음

    result = find_unknown_lesson_references(body, known)

    assert result == [], f"소문자 lesson-022 가 감지됨 (대소문자 구분 실패): {result}"


def test_find_unknown_references_with_dashes_known() -> None:
    """LESSON-STYLE-001 이 known 에 포함되면 unknown 으로 감지되지 않는다."""
    body = "스타일 가이드라인은 LESSON-STYLE-001 참고."
    known: frozenset[str] = frozenset({"LESSON-STYLE-001"})

    result = find_unknown_lesson_references(body, known)

    assert result == [], f"알려진 LESSON-STYLE-001 이 unknown 으로 잘못 감지됨: {result}"


# ── 그룹 1 단계 1: has.* source 의미론 인프라 ─────────────────────────────────


def test_profile_provides_capabilities_parsed_when_present(tmp_path: Path) -> None:
    """frontmatter 에 provides_capabilities 가 있으면 Profile.provides_capabilities 로 파싱됨."""
    profiles_dir = tmp_path / "profiles"
    _write_profile(
        profiles_dir,
        "test-caps",
        extra_frontmatter={"provides_capabilities": ["ui", "navigation"]},
    )
    loader = ProfileLoader(harness_dir=tmp_path)
    profile = loader.load("test-caps")
    assert profile.provides_capabilities == ("ui", "navigation")


def test_profile_provides_capabilities_defaults_empty_when_absent(tmp_path: Path) -> None:
    """frontmatter 에 provides_capabilities 키가 없으면 빈 tuple (legacy 호환)."""
    profiles_dir = tmp_path / "profiles"
    _write_profile(profiles_dir, "legacy-profile")
    loader = ProfileLoader(harness_dir=tmp_path)
    profile = loader.load("legacy-profile")
    assert profile.provides_capabilities == ()


def test_derive_axes_capabilities_pii_adds_users() -> None:
    """data_sensitivity=pii → frozenset({'users'})."""
    axes = ScaleAxes(data_sensitivity="pii")
    result = derive_axes_capabilities(axes)
    assert result == frozenset({"users"})


def test_derive_axes_capabilities_payment_monetization_adds_users() -> None:
    """monetization=payment → frozenset({'users'}). data_sensitivity=none 은 무관."""
    axes = ScaleAxes(monetization="payment", data_sensitivity="none")
    result = derive_axes_capabilities(axes)
    assert result == frozenset({"users"})


def test_derive_axes_capabilities_no_signals_empty() -> None:
    """기본값 (data_sensitivity=none, monetization=none) → 빈 frozenset."""
    axes = ScaleAxes()
    result = derive_axes_capabilities(axes)
    assert result == frozenset()


def test_compute_has_keys_uses_provides_capabilities_when_present() -> None:
    """provides_capabilities 가 명시된 프로파일은 capability 만 사용 — declared sections 무시."""
    # skeleton_sections.required 에 auth/persistence 가 있어도 무시되어야 함
    profile = _make_profile(
        profile_id="mock-api",
        required=["auth", "persistence"],  # legacy 매핑에 있는 섹션이지만 무시되어야 함
        provides_capabilities=["ui", "http_server"],
    )
    loader = ProfileLoader()
    result = loader.compute_has_keys([profile])
    assert result == frozenset({"ui", "http_server"})
    # legacy 매핑으로 나올 수 있는 users/storage 는 없어야 함
    assert "users" not in result
    assert "storage" not in result


def test_compute_has_keys_no_legacy_fallback() -> None:
    """legacy _SECTION_TO_HAS_KEY fallback 제거 확인.

    provides_capabilities=[] 인 프로파일은 required 섹션 목록과 무관하게
    has.* atom 을 생성하지 않는다. (Step 3: fallback 제거)

    이전 동작: required=["view.screens"] → legacy 매핑으로 has.ui 활성.
    현재 동작: provides_capabilities=[] → 빈 frozenset (strict).
    """
    profile = _make_profile(
        profile_id="no-capabilities",
        required=["view.screens", "auth", "persistence"],  # legacy 라면 ui/users/storage 활성
        provides_capabilities=[],
    )
    loader = ProfileLoader()
    result = loader.compute_has_keys([profile])
    assert result == frozenset(), (
        "provides_capabilities=[] 인 프로파일은 required 섹션 무시 — legacy fallback 없음"
    )


def test_compute_has_keys_unions_profile_and_axes() -> None:
    """프로파일 provides_capabilities + axes 추론 → union."""
    profile = _make_profile(
        profile_id="mock-rne",
        provides_capabilities=["ui"],
    )
    axes = ScaleAxes(data_sensitivity="pii")
    loader = ProfileLoader()
    result = loader.compute_has_keys([profile], axes)
    assert result == frozenset({"ui", "users"})


def test_compute_has_keys_axes_optional_for_backward_compat() -> None:
    """axes 미전달 시 에러 없이 동작 (backward compat).

    provides_capabilities 로 명시된 atom 은 axes 없이도 정상 반환.
    """
    profile = _make_profile(provides_capabilities=["users"])
    loader = ProfileLoader()
    # axes 없이 호출 — should not raise
    result = loader.compute_has_keys([profile])
    assert isinstance(result, frozenset)
    assert "users" in result


def test_compute_active_sections_chamberlain_case_mobile_only_with_pii(
    tmp_path: Path,
) -> None:
    """챙겼니 회복 기준선 — mock-react-native-expo + pii axes.

    provides_capabilities 로 storage/users 를 올바르게 활성화하고
    http_server 는 없어야 함.
    """
    fragments_dir = tmp_path / "skeleton"
    # auth: has.users, persistence: has.storage, data_model: has.storage,
    # interface.http: has.http_server (비활성 기대), rate_limiting: has.http_server (비활성)
    # authorization_matrix: has.users (활성 기대)
    _write_fragment(fragments_dir, "auth", "has.users")
    _write_fragment(fragments_dir, "persistence", "has.storage")
    _write_fragment(fragments_dir, "data_model", "has.storage")
    _write_fragment(fragments_dir, "interface.http", "has.http_server")
    _write_fragment(fragments_dir, "rate_limiting", "has.http_server")
    _write_fragment(fragments_dir, "authorization_matrix", "has.users")
    _write_fragment(fragments_dir, "overview", "always")

    mock_rne = _make_profile(
        profile_id="mock-react-native-expo",
        provides_capabilities=[
            "ui",
            "navigation",
            "lifecycle",
            "build_config",
            "storage",
            "complex_state",
            "env_config",
        ],
    )
    axes = ScaleAxes(
        user_scale="medium",
        data_sensitivity="pii",
        team_size="small",
        availability="standard",
        monetization="none",
        lifecycle="mvp",
    )
    loader = ProfileLoader()
    active, _trace = loader.compute_active_sections(axes, [mock_rne], fragments_dir)

    assert "auth" in active, "has.users (PII axes) → auth 활성"
    assert "persistence" in active, "has.storage (provides) → persistence 활성"
    assert "data_model" in active, "has.storage (provides) → data_model 활성"
    assert "authorization_matrix" in active, "has.users (PII axes) → authorization_matrix 활성"
    assert "interface.http" not in active, "has.http_server 없음 → interface.http 비활성"
    assert "rate_limiting" not in active, "has.http_server 없음 → rate_limiting 비활성"


def test_compute_active_sections_paired_backend_mobile(tmp_path: Path) -> None:
    """paired 모드 — mock-fastapi + mock-rne → http_server + storage + users 모두 활성."""
    fragments_dir = tmp_path / "skeleton"
    _write_fragment(fragments_dir, "interface.http", "has.http_server")
    _write_fragment(fragments_dir, "rate_limiting", "has.http_server")
    _write_fragment(fragments_dir, "auth", "has.users")
    _write_fragment(fragments_dir, "persistence", "has.storage")
    _write_fragment(fragments_dir, "overview", "always")

    mock_fastapi = _make_profile(
        profile_id="mock-fastapi",
        provides_capabilities=["http_server", "env_config", "production_concerns"],
    )
    mock_rne = _make_profile(
        profile_id="mock-rne",
        provides_capabilities=[
            "ui",
            "navigation",
            "lifecycle",
            "build_config",
            "storage",
            "complex_state",
            "env_config",
        ],
    )
    axes = ScaleAxes(
        user_scale="medium",
        data_sensitivity="pii",
        team_size="small",
        availability="standard",
        monetization="none",
        lifecycle="mvp",
    )
    loader = ProfileLoader()
    active, _trace = loader.compute_active_sections(axes, [mock_fastapi, mock_rne], fragments_dir)

    assert "interface.http" in active, "has.http_server (fastapi provides) → interface.http 활성"
    assert "rate_limiting" in active, "has.http_server → rate_limiting 활성"
    assert "auth" in active, "has.users (PII axes) → auth 활성"
    assert "persistence" in active, "has.storage (rne provides) → persistence 활성"


# ── 그룹 1 단계 2: 실제 프로파일 provides_capabilities 검증 ──────────────────


_CONFIRMED_PROFILE_IDS: tuple[str, ...] = (
    "fastapi",
    "nestjs",
    "python-cli",
    "python-lib",
    "nextjs",
    "react-vite",
    "electron",
    "react-native-expo",
    "flutter",
    "android-kotlin",
    "ios-swift",
    "claude-skill",
)


def test_all_confirmed_profiles_declare_capabilities() -> None:
    """실제 harness/profiles/ 의 12개 confirmed 프로파일 모두 provides_capabilities 를 명시.

    claude-skill 은 빈 리스트 허용 (의도된 없음 표시). 나머지는 비어있으면 안 됨.
    capability 값이 알려진 atom 셋 안에 있는지 검증 (typo 방지).
    """
    repo_harness = Path(__file__).parent.parent.parent.parent / "harness"
    loader = ProfileLoader(harness_dir=repo_harness)

    for profile_id in _CONFIRMED_PROFILE_IDS:
        profile_path = repo_harness / "profiles" / f"{profile_id}.md"
        if not profile_path.exists():
            import pytest

            pytest.skip(f"{profile_id}.md profile not yet installed")

        profile = loader.load(profile_id)

        # claude-skill: 빈 리스트 명시 허용 (의도된 없음)
        if profile_id == "claude-skill":
            assert isinstance(profile.provides_capabilities, tuple), (
                f"{profile_id}: provides_capabilities 가 tuple 이어야 함"
            )
            # 빈 tuple 허용 — 그냥 통과
        else:
            assert len(profile.provides_capabilities) > 0, (
                f"{profile_id}: provides_capabilities 가 비어있음 — "
                "모든 confirmed 프로파일은 capability 를 명시해야 함"
            )

        # 모든 capability 값이 알려진 atom 셋 안에 있어야 함
        for cap in profile.provides_capabilities:
            assert cap in _KNOWN_CAPABILITY_ATOMS, (
                f"{profile_id}: 알 수 없는 capability atom '{cap}' — "
                f"알려진 atoms: {sorted(_KNOWN_CAPABILITY_ATOMS)}"
            )


def test_fastapi_provides_http_server() -> None:
    """fastapi 프로파일 로드 → provides_capabilities 에 'http_server' 포함."""
    repo_harness = Path(__file__).parent.parent.parent.parent / "harness"
    if not (repo_harness / "profiles" / "fastapi.md").exists():
        import pytest

        pytest.skip("fastapi profile not yet installed")

    loader = ProfileLoader(harness_dir=repo_harness)
    profile = loader.load("fastapi")

    assert "http_server" in profile.provides_capabilities, (
        f"fastapi.provides_capabilities = {profile.provides_capabilities!r} — 'http_server' 누락"
    )


def test_react_native_expo_provides_mobile_capabilities() -> None:
    """react-native-expo 프로파일 → 필수 모바일 capabilities 5종 모두 포함."""
    repo_harness = Path(__file__).parent.parent.parent.parent / "harness"
    if not (repo_harness / "profiles" / "react-native-expo.md").exists():
        import pytest

        pytest.skip("react-native-expo profile not yet installed")

    loader = ProfileLoader(harness_dir=repo_harness)
    profile = loader.load("react-native-expo")

    required_mobile_caps = {"ui", "navigation", "lifecycle", "build_config", "storage"}
    caps_set = set(profile.provides_capabilities)
    missing = required_mobile_caps - caps_set
    assert not missing, (
        f"react-native-expo.provides_capabilities = {profile.provides_capabilities!r} — "
        f"누락된 모바일 capabilities: {missing}"
    )


def test_chamberlain_case_end_to_end_with_real_profiles() -> None:
    """챙겼니 회귀 기준선 — 실제 react-native-expo + 실제 fragments.

    6축: medium / pii / small / standard / none / mvp
    활성 기대: mobile 관련 섹션들, auth/authorization_matrix (PII), persistence/data_model
    비활성 기대: interface.http, rate_limiting (http_server 없음)
    """
    repo_harness = Path(__file__).parent.parent.parent.parent / "harness"
    fragments_dir = repo_harness / "templates" / "skeleton"

    if not (repo_harness / "profiles" / "react-native-expo.md").exists():
        import pytest

        pytest.skip("react-native-expo profile not yet installed")
    if not fragments_dir.exists():
        import pytest

        pytest.skip("harness skeleton fragments not yet installed")

    loader = ProfileLoader(harness_dir=repo_harness)
    profile = loader.load("react-native-expo")
    axes = ScaleAxes(
        user_scale="medium",
        data_sensitivity="pii",
        team_size="small",
        availability="standard",
        monetization="none",
        lifecycle="mvp",
    )
    active, trace = loader.compute_active_sections(axes, [profile], fragments_dir)
    active_set = set(active)

    # 비활성 기대: http_server 전용 섹션
    assert "interface.http" not in active_set, (
        f"mobile-only 에서 interface.http 비활성 기대 — 활성된 섹션: {sorted(active_set)}"
    )
    assert "rate_limiting" not in active_set, "mobile-only 에서 rate_limiting 비활성 기대"

    # 활성 기대: 모바일 코어 섹션
    for expected in ("mobile.navigation", "mobile.build_config", "mobile.lifecycle"):
        assert expected in active_set, (
            f"{expected} 활성 기대 — react-native-expo provides navigation/build_config/lifecycle"
        )

    # 활성 기대: PII 축 → users 관련 섹션
    assert "auth" in active_set, "PII axes → has.users → auth 활성"
    assert "authorization_matrix" in active_set, "PII axes → has.users → authorization_matrix 활성"

    # 활성 기대: storage capability → persistence/data_model
    assert "persistence" in active_set, "storage capability → persistence 활성"
    assert "data_model" in active_set, "storage capability → data_model 활성"


def test_paired_fastapi_rne_includes_backend_sections() -> None:
    """paired 모드 (fastapi + react-native-expo) — 실제 프로파일 + 실제 fragments.

    6축: medium / pii / small / standard / none / mvp
    활성 기대: interface.http, rate_limiting (fastapi 의 http_server capability)
    """
    repo_harness = Path(__file__).parent.parent.parent.parent / "harness"
    fragments_dir = repo_harness / "templates" / "skeleton"

    for fname in ("fastapi.md", "react-native-expo.md"):
        if not (repo_harness / "profiles" / fname).exists():
            import pytest

            pytest.skip(f"{fname} profile not yet installed")
    if not fragments_dir.exists():
        import pytest

        pytest.skip("harness skeleton fragments not yet installed")

    loader = ProfileLoader(harness_dir=repo_harness)
    fastapi_profile = loader.load("fastapi")
    rne_profile = loader.load("react-native-expo")
    axes = ScaleAxes(
        user_scale="medium",
        data_sensitivity="pii",
        team_size="small",
        availability="standard",
        monetization="none",
        lifecycle="mvp",
    )
    active, trace = loader.compute_active_sections(
        axes, [fastapi_profile, rne_profile], fragments_dir
    )
    active_set = set(active)

    assert "interface.http" in active_set, (
        f"fastapi http_server → interface.http 활성 기대 — 활성된 섹션: {sorted(active_set)}"
    )
    assert "rate_limiting" in active_set, "fastapi http_server → rate_limiting 활성 기대"


# ── Group 5 Step 1: SRP split backward-compat 회귀 ───────────────────────────


def test_backward_compat_reexports_remain_available() -> None:
    """Group 5 Step 1 SRP split — old import paths still work."""
    # These should not raise ImportError
    from src.orchestrator import capabilities as cap

    # Identity — re-export must point to the same function (not a copy)
    from src.orchestrator import profile_loader as pl

    # And the new direct imports
    from src.orchestrator.capabilities import derive_axes_capabilities as direct_d  # noqa: F401
    from src.orchestrator.consistency import find_consistency_violations as direct_c  # noqa: F401
    from src.orchestrator.lessons import extract_known_lessons as direct_l  # noqa: F401
    from src.orchestrator.profile_loader import (  # noqa: F401
        derive_axes_capabilities,
        extract_known_lessons,
        find_consistency_violations,
        find_unknown_lesson_references,
    )

    assert pl.derive_axes_capabilities is cap.derive_axes_capabilities


# ── Group 5 Step 2: slo / runbook 의 production_concerns 컨텍스트 ──────


def test_slo_inactive_for_mobile_only_no_production_concerns() -> None:
    """react-native-expo 단독 + medium → slo 비활성 (production_concerns 없음).

    Group 5 Step 2 — slo fragment trigger 가 `(scale.medium_or_larger or
    availability == high) and has.production_concerns` 로 강화됐는지 검증.
    """
    repo_harness = Path(__file__).parent.parent.parent.parent / "harness"
    fragments_dir = repo_harness / "templates" / "skeleton"
    if not (repo_harness / "profiles" / "react-native-expo.md").exists():
        import pytest

        pytest.skip("react-native-expo profile not yet installed")

    loader = ProfileLoader(harness_dir=repo_harness)
    profile = loader.load("react-native-expo")
    axes = ScaleAxes(
        user_scale="medium",
        data_sensitivity="pii",
        team_size="small",
        availability="standard",
        monetization="none",
        lifecycle="mvp",
    )
    active, _trace = loader.compute_active_sections(axes, [profile], fragments_dir)
    assert "slo" not in active, (
        "mobile-only 에 production_concerns 없으면 slo 비활성 기대 — "
        f"활성된 섹션: {sorted(set(active))}"
    )


def test_slo_active_for_backend_with_production_concerns() -> None:
    """fastapi (provides production_concerns) + medium → slo 활성.

    Mirror test 로 trigger 강화 후에도 정당한 활성 케이스 보존 검증.
    """
    repo_harness = Path(__file__).parent.parent.parent.parent / "harness"
    fragments_dir = repo_harness / "templates" / "skeleton"
    if not (repo_harness / "profiles" / "fastapi.md").exists():
        import pytest

        pytest.skip("fastapi profile not yet installed")

    loader = ProfileLoader(harness_dir=repo_harness)
    profile = loader.load("fastapi")
    axes = ScaleAxes(
        user_scale="medium",
        data_sensitivity="pii",
        team_size="small",
        availability="standard",
        monetization="none",
        lifecycle="mvp",
    )
    active, _trace = loader.compute_active_sections(axes, [profile], fragments_dir)
    assert "slo" in active, "fastapi (production_concerns) + medium → slo 활성 기대"


def test_runbook_inactive_for_mobile_only_even_high_availability() -> None:
    """react-native-expo + availability=high → runbook 비활성 (production_concerns 없음)."""
    repo_harness = Path(__file__).parent.parent.parent.parent / "harness"
    fragments_dir = repo_harness / "templates" / "skeleton"
    if not (repo_harness / "profiles" / "react-native-expo.md").exists():
        import pytest

        pytest.skip("react-native-expo profile not yet installed")

    loader = ProfileLoader(harness_dir=repo_harness)
    profile = loader.load("react-native-expo")
    axes = ScaleAxes(
        user_scale="medium",
        data_sensitivity="pii",
        team_size="small",
        availability="high",  # 트리거 조건 충족
        monetization="none",
        lifecycle="mvp",
    )
    active, _trace = loader.compute_active_sections(axes, [profile], fragments_dir)
    assert "runbook" not in active, (
        "mobile-only 에 production_concerns 없으면 runbook 비활성 기대 — "
        f"활성된 섹션: {sorted(set(active))}"
    )


# ── external_capabilities (Group 1-D) ────────────────────────────────


def test_compute_has_keys_includes_external_capabilities(tmp_path: Path) -> None:
    """profile(ui) + axes(none) + external=[http_server, storage] → 세 atom 모두 포함."""
    profile = _make_profile(provides_capabilities=["ui"])
    loader = ProfileLoader()
    axes = ScaleAxes(data_sensitivity="none")
    result = loader.compute_has_keys(
        [profile],
        axes,
        external_capabilities=frozenset({"http_server", "storage"}),
    )
    assert "ui" in result
    assert "http_server" in result
    assert "storage" in result


def test_compute_active_sections_baas_case_activates_interface_http(tmp_path: Path) -> None:
    """BaaS 케이스: react-native-expo + external=[http_server] → interface.http 활성.

    backend profile 없이도 external_capabilities 에 http_server 선언하면
    has.http_server 조건의 fragment 가 활성화되어야 한다.
    """
    fragments_dir = tmp_path / "skeleton"
    _write_fragment(fragments_dir, "interface.http", "has.http_server")
    _write_fragment(fragments_dir, "overview", "always")
    profile = _make_profile(profile_id="react-native-expo", provides_capabilities=["ui"])
    loader = ProfileLoader()
    axes = ScaleAxes(
        user_scale="small",
        data_sensitivity="none",
        team_size="solo",
        availability="standard",
        monetization="none",
        lifecycle="mvp",
    )
    # Without external_capabilities — interface.http should be inactive
    active_without, _ = loader.compute_active_sections(axes, [profile], fragments_dir)
    assert "interface.http" not in active_without

    # With external_capabilities=[http_server] — interface.http should be active
    active_with, trace = loader.compute_active_sections(
        axes,
        [profile],
        fragments_dir,
        external_capabilities=frozenset({"http_server"}),
    )
    assert "interface.http" in active_with
    assert "overview" in active_with


# ── toolchain.smoke (ha-smoke 런타임 게이트) ───────────────────────────────


def test_toolchain_smoke_field_parsed(tmp_path: Path) -> None:
    """toolchain.smoke 명령이 Toolchain.smoke 로 매핑된다."""
    harness = tmp_path / "harness"
    _write_profile(
        harness / "profiles",
        "smokeprof",
        required_sections=["overview"],
        extra_frontmatter={
            "toolchain": {
                "install": "i",
                "test": "t",
                "lint": "l",
                "smoke": "python -m app --help",
            }
        },
    )
    loader = ProfileLoader(harness_dir=harness)
    assert loader.load("smokeprof").toolchain.smoke == "python -m app --help"


def test_toolchain_smoke_defaults_to_none(tmp_path: Path) -> None:
    """smoke 미지정 프로파일은 None (기존 프로파일 비파괴)."""
    harness = tmp_path / "harness"
    _write_profile(harness / "profiles", "nosmoke", required_sections=["overview"])
    loader = ProfileLoader(harness_dir=harness)
    assert loader.load("nosmoke").toolchain.smoke is None


# ── toolchain.scaffold (T-000 결정론 스캐폴드 부트스트랩, scaffolding-design.md) ──


def test_toolchain_scaffold_field_parsed(tmp_path: Path) -> None:
    """toolchain.scaffold 명령이 Toolchain.scaffold 로 매핑된다."""
    harness = tmp_path / "harness"
    _write_profile(
        harness / "profiles",
        "scaffoldprof",
        required_sections=["overview"],
        extra_frontmatter={
            "toolchain": {
                "install": "i",
                "test": "t",
                "lint": "l",
                "scaffold": "pnpm create next-app@16 .",
            }
        },
    )
    loader = ProfileLoader(harness_dir=harness)
    assert loader.load("scaffoldprof").toolchain.scaffold == "pnpm create next-app@16 ."


def test_toolchain_scaffold_defaults_to_none(tmp_path: Path) -> None:
    """scaffold 미지정 프로파일은 None (fastapi 등 공식 스캐폴더 없는 프로파일 — 기존 비파괴)."""
    harness = tmp_path / "harness"
    _write_profile(harness / "profiles", "noscaffold", required_sections=["overview"])
    loader = ProfileLoader(harness_dir=harness)
    assert loader.load("noscaffold").toolchain.scaffold is None


def test_toolchain_scaffold_child_overrides_parent(tmp_path: Path) -> None:
    """extends 상속 시 자식의 toolchain.scaffold 가 부모 값을 override 한다."""
    harness = tmp_path / "harness"
    _write_profile(
        harness / "profiles",
        "parent",
        required_sections=["overview"],
        extra_frontmatter={
            "toolchain": {
                "install": "i",
                "test": "t",
                "lint": "l",
                "scaffold": "parent-scaffold-cmd",
            }
        },
    )
    _write_profile(
        harness / "profiles",
        "child",
        extends="parent",
        required_sections=["overview"],
        extra_frontmatter={
            "toolchain": {
                "install": "i2",
                "test": "t2",
                "lint": "l2",
                "scaffold": "child-scaffold-cmd",
            }
        },
    )
    loader = ProfileLoader(harness_dir=harness)
    assert loader.load("child").toolchain.scaffold == "child-scaffold-cmd"
