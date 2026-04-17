"""HarnessAI v2 통합 (E2E) 테스트.

전체 v2 흐름:
  ProfileLoader.detect()
  → Orchestra.assemble_skeleton_for_profiles()
  → 빈 skeleton.md 생성
  → context.build_context(use_section_ids=True) 가 정상 발췌
  → SecurityHooks.from_profile() 이 프로파일 whitelist 적용

이 테스트는 Phase 2 의 모듈들이 실제로 함께 동작하는지 확인.
모든 픽스처는 tmp_path 기반.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from src.orchestrator.context import build_context
from src.orchestrator.orchestrate import Orchestra
from src.orchestrator.profile_loader import ProfileLoader
from src.orchestrator.security_hooks import SecurityHooks


def _setup_minimal_harness(harness_dir: Path) -> None:
    """프로파일 1개 + 조각 4개 + registry 1개로 최소 v2 환경."""
    profiles = harness_dir / "profiles"
    fragments = harness_dir / "templates" / "skeleton"
    profiles.mkdir(parents=True)
    fragments.mkdir(parents=True)

    (profiles / "_registry.yaml").write_text(
        dedent("""\
            version: 1
            rules:
              - profile: testpy
                paths: ["."]
                detect:
                  files: [pyproject.toml]
                  contains: {pyproject.toml: ["click"]}
            fallback:
              action: prompt_user
        """),
        encoding="utf-8",
    )

    (profiles / "testpy.md").write_text(
        dedent("""\
            ---
            id: testpy
            name: TestPy
            status: confirmed
            version: 1
            paths: ["."]
            detect:
              files: [pyproject.toml]
              contains: {pyproject.toml: ["click"]}
            components: []
            skeleton_sections:
              required: [overview, stack, errors]
              optional: []
              order: [overview, stack, errors]
            toolchain: {install: null, test: null, lint: null, type: null, format: null}
            whitelist:
              runtime: [click, pydantic]
              dev: [pytest, ruff]
              prefix_allowed: []
            file_structure: "x"
            gstack_mode: manual
            ---
        """),
        encoding="utf-8",
    )

    # 조각: SECTION_TITLES 와 일치하는 name 필수 (context.extract_section_by_id 가 매칭)
    fragment_specs = [
        ("overview", "프로젝트 개요"),
        ("stack", "기술 스택"),
        ("errors", "에러 핸들링"),
    ]
    for sid, title in fragment_specs:
        (fragments / f"{sid}.md").write_text(
            dedent(f"""\
                ---
                id: {sid}
                name: {title}
                required_when: always
                description: e2e test
                ---

                ## {{{{section_number}}}}. {title}

                Body for {sid}.
            """),
            encoding="utf-8",
        )


def _setup_project(project_dir: Path) -> None:
    project_dir.mkdir(parents=True)
    (project_dir / "pyproject.toml").write_text(
        '[project]\nname="x"\ndependencies=["click"]\n',
        encoding="utf-8",
    )
    backend_dir = Path(__file__).parent.parent.parent
    (project_dir / "agents.yaml").write_text(
        (backend_dir / "agents.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def test_e2e_detect_assemble_extract(tmp_path: Path) -> None:
    """전체 흐름 — detect → assemble → build_context (ID 기반) 가 정합."""
    harness = tmp_path / "harness"
    project = tmp_path / "project"
    _setup_minimal_harness(harness)
    _setup_project(project)

    # 1. ProfileLoader 가 프로파일 감지
    loader = ProfileLoader(harness_dir=harness, project_dir=project)
    matches = loader.detect()
    assert len(matches) == 1
    assert matches[0].profile.id == "testpy"
    assert matches[0].path == "."

    # 2. Orchestra 가 프로파일 기반 skeleton 조립
    orchestra = Orchestra(project_dir=project)
    skeleton_path = orchestra.assemble_skeleton_for_profiles(
        ["testpy"], harness_dir=harness, title="E2E Test"
    )
    assert skeleton_path.exists()
    skeleton_text = skeleton_path.read_text(encoding="utf-8")
    assert "# E2E Test" in skeleton_text
    assert "## 1. 프로젝트 개요" in skeleton_text
    assert "## 2. 기술 스택" in skeleton_text
    assert "## 3. 에러 핸들링" in skeleton_text

    # 3. build_context (use_section_ids=True) 가 v2 매핑으로 발췌
    context = build_context(
        agent="backend_coder",
        skeleton_path=skeleton_path,
        docs_dir=project / "docs",
        use_section_ids=True,
    )
    # backend_coder 는 overview/stack/errors 포함
    assert "프로젝트 개요" in context
    assert "에러 핸들링" in context
    assert "관련 섹션" in context  # 필터링된 버전이라는 마커


def test_e2e_security_hooks_from_profile(tmp_path: Path) -> None:
    """SecurityHooks.from_profile 이 프로파일 whitelist 정확 적용."""
    harness = tmp_path / "harness"
    project = tmp_path / "project"
    _setup_minimal_harness(harness)
    _setup_project(project)

    loader = ProfileLoader(harness_dir=harness, project_dir=project)
    profile = loader.load("testpy")

    hooks = SecurityHooks.from_profile(profile)

    # click 은 화이트리스트 — 통과
    result_ok = hooks.run_all("import click\n")
    assert not any("click" in f.message for f in result_ok.findings)

    # fastapi 는 화이트리스트 외 (testpy 프로파일에 없음) → WARN
    result_warn = hooks.run_all("import fastapi\n")
    assert any("fastapi" in f.message for f in result_warn.findings)


def test_e2e_monorepo_two_profiles_assemble_independent_skeletons(
    tmp_path: Path,
) -> None:
    """모노레포: 두 프로파일이 detect 후 각각 skeleton 조립 가능."""
    harness = tmp_path / "harness"
    project = tmp_path / "project"

    profiles = harness / "profiles"
    fragments = harness / "templates" / "skeleton"
    profiles.mkdir(parents=True)
    fragments.mkdir(parents=True)

    (profiles / "_registry.yaml").write_text(
        dedent("""\
            version: 1
            rules:
              - profile: backend
                paths: ["backend/"]
                detect:
                  files: [pyproject.toml]
              - profile: frontend
                paths: ["frontend/"]
                detect:
                  files: [package.json]
            fallback:
              action: prompt_user
        """),
        encoding="utf-8",
    )

    for pid, sections in [
        ("backend", ["overview", "errors"]),
        ("frontend", ["overview", "stack"]),
    ]:
        (profiles / f"{pid}.md").write_text(
            dedent(f"""\
                ---
                id: {pid}
                name: {pid}
                status: confirmed
                version: 1
                paths: []
                detect: {{}}
                components: []
                skeleton_sections:
                  required: {sections}
                  optional: []
                  order: {sections}
                toolchain: {{install: null, test: null, lint: null, type: null, format: null}}
                whitelist: {{runtime: [], dev: [], prefix_allowed: []}}
                file_structure: "x"
                gstack_mode: manual
                ---
            """),
            encoding="utf-8",
        )

    for sid, title in [
        ("overview", "프로젝트 개요"),
        ("stack", "기술 스택"),
        ("errors", "에러 핸들링"),
    ]:
        (fragments / f"{sid}.md").write_text(
            dedent(f"""\
                ---
                id: {sid}
                name: {title}
                required_when: always
                description: x
                ---

                ## {{{{section_number}}}}. {title}

                body
            """),
            encoding="utf-8",
        )

    project.mkdir()
    (project / "backend").mkdir()
    (project / "backend" / "pyproject.toml").write_text("x", encoding="utf-8")
    (project / "frontend").mkdir()
    (project / "frontend" / "package.json").write_text("{}", encoding="utf-8")
    backend_dir = Path(__file__).parent.parent.parent
    (project / "agents.yaml").write_text(
        (backend_dir / "agents.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    loader = ProfileLoader(harness_dir=harness, project_dir=project)
    matches = loader.detect()
    matched_ids = {m.profile.id for m in matches}
    assert matched_ids == {"backend", "frontend"}
