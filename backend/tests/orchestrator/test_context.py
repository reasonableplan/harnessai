"""Skeleton 섹션 ID 기반 컨텍스트 주입 테스트 (Harness v2)."""

from pathlib import Path

from src.orchestrator.context import (
    AGENT_SECTIONS_BY_ID,
    SECTION_TITLES,
    build_context,
    extract_section_by_id,
)

# Harness v2 조각 형식 (skeleton_assembler 출력 모방). 헤딩 제목은
# SECTION_TITLES 와 정확히 일치해야 함.
SAMPLE_SKELETON = """\
# Project Skeleton — Sample

## 1. 프로젝트 개요
- **프로젝트명**: Sample App
- **한 줄 설명**: 테스트 프로젝트

## 2. 기술 스택
### 런타임 / 언어
- Python 3.12

## 3. 에러 핸들링
### 에러 분류 체계
| 코드 | 의미 |
|------|------|
| `PARSE_001` | 파싱 실패 |

## 4. HTTP API
### 엔드포인트
| Method | Path |
|--------|------|
| GET    | /api |

## 5. CLI 커맨드
### 엔트리포인트
- 실행: `sample`

## 6. 도메인 로직
### 핵심 비즈니스 규칙
1. 입력 검증

## 7. 태스크 분해
| ID | Component |
|----|-----------|
"""


class TestSectionTitlesMap:
    def test_all_36_standard_sections_present(self) -> None:
        """SECTION_TITLES 36개 전부 존재 (기본 20 + auto-fit 10 + 운영/환경/UX 3 + 모바일 3)."""
        expected_ids = {
            # 기본 20
            "overview",
            "requirements",
            "stack",
            "configuration",
            "errors",
            "auth",
            "persistence",
            "integrations",
            "interface.http",
            "interface.cli",
            "interface.ipc",
            "interface.sdk",
            "view.screens",
            "view.components",
            "state.flow",
            "core.logic",
            "observability",
            "deployment",
            "tasks",
            "notes",
            # auto-fit skeleton (10)
            "data_model",
            "threat_model",
            "audit_log",
            "slo",
            "runbook",
            "test_strategy",
            "user_journey",
            "authorization_matrix",
            "ci_cd",
            "external_deps",
            # 운영 / 환경 / UX (3) — required_when 으로 활성
            "environments",
            "error_ux",
            "rate_limiting",
            # 모바일 (3)
            "mobile.navigation",
            "mobile.build_config",
            "mobile.lifecycle",
        }
        assert set(SECTION_TITLES.keys()) == expected_ids


class TestAgentSectionsById:
    def test_all_agents_have_id_mapping(self) -> None:
        """11 agents (7 기본 + 4 mobile_coder_*) 전부 AGENT_SECTIONS_BY_ID 에 존재."""
        expected = {
            "architect",
            "designer",
            "orchestrator",
            "backend_coder",
            "frontend_coder",
            "mobile_coder_rn",
            "mobile_coder_flutter",
            "mobile_coder_android",
            "mobile_coder_ios",
            "reviewer",
            "qa",
        }
        assert set(AGENT_SECTIONS_BY_ID.keys()) == expected

    def test_architect_gets_all(self) -> None:
        assert AGENT_SECTIONS_BY_ID["architect"] == ["*"]

    def test_referenced_ids_are_standard(self) -> None:
        """모든 참조된 섹션 ID 는 SECTION_TITLES 에 존재."""
        for agent, sections in AGENT_SECTIONS_BY_ID.items():
            for sid in sections:
                if sid == "*":
                    continue
                assert sid in SECTION_TITLES, f"{agent} → unknown section_id '{sid}'"


class TestExtractSectionById:
    def test_wildcard_returns_full(self) -> None:
        assert extract_section_by_id(SAMPLE_SKELETON, "*") == SAMPLE_SKELETON

    def test_extract_overview(self) -> None:
        result = extract_section_by_id(SAMPLE_SKELETON, "overview")
        assert "Sample App" in result
        assert "테스트 프로젝트" in result

    def test_extract_interface_cli(self) -> None:
        result = extract_section_by_id(SAMPLE_SKELETON, "interface.cli")
        assert "엔트리포인트" in result
        assert "sample" in result

    def test_extract_errors(self) -> None:
        result = extract_section_by_id(SAMPLE_SKELETON, "errors")
        assert "PARSE_001" in result

    def test_section_boundary_respected(self) -> None:
        result = extract_section_by_id(SAMPLE_SKELETON, "stack")
        assert "Python 3.12" in result
        # 다음 섹션 (errors) 내용이 새지 않아야
        assert "PARSE_001" not in result

    def test_unknown_id_returns_empty(self) -> None:
        assert extract_section_by_id(SAMPLE_SKELETON, "totally-fake") == ""

    def test_id_not_in_skeleton_returns_empty(self) -> None:
        # auth 는 표준 ID 이지만 SAMPLE 에 헤딩 없음
        assert extract_section_by_id(SAMPLE_SKELETON, "auth") == ""


class TestBuildContext:
    def test_with_all_files(self, tmp_path: Path) -> None:
        # 에이전트 프롬프트
        prompt_path = tmp_path / "agents" / "architect" / "CLAUDE.md"
        prompt_path.parent.mkdir(parents=True)
        prompt_path.write_text("You are an architect.", encoding="utf-8")

        # skeleton
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "skeleton.md").write_text(SAMPLE_SKELETON, encoding="utf-8")

        # 추가 문서
        (docs_dir / "conventions.md").write_text("# Conventions\n- snake_case", encoding="utf-8")
        (docs_dir / "shared-lessons.md").write_text("# Lessons\n- LESSON-001", encoding="utf-8")

        result = build_context(
            agent="architect",
            skeleton_path=docs_dir / "skeleton.md",
            docs_dir=docs_dir,
            prompt_path=prompt_path,
        )

        assert "You are an architect." in result
        assert "Skeleton" in result
        assert "snake_case" in result
        assert "LESSON-001" in result

    def test_with_no_files(self, tmp_path: Path) -> None:
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        result = build_context(
            agent="architect",
            skeleton_path=docs_dir / "skeleton.md",
            docs_dir=docs_dir,
        )

        assert result == ""

    def test_backend_coder_gets_filtered_context(self, tmp_path: Path) -> None:
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "skeleton.md").write_text(SAMPLE_SKELETON, encoding="utf-8")

        result = build_context(
            agent="backend_coder",
            skeleton_path=docs_dir / "skeleton.md",
            docs_dir=docs_dir,
        )

        # backend_coder 는 errors, core.logic 포함. 관련 섹션 마커 있음 (전체 아님).
        assert "PARSE_001" in result
        assert "relevant sections" in result

    def test_architect_gets_all_skeleton(self, tmp_path: Path) -> None:
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "skeleton.md").write_text(SAMPLE_SKELETON, encoding="utf-8")

        result = build_context(
            agent="architect",
            skeleton_path=docs_dir / "skeleton.md",
            docs_dir=docs_dir,
        )

        assert "Sample App" in result
        # architect 는 전체이므로 "relevant sections" 마커 없음
        assert "relevant sections" not in result

    def test_adr_directory(self, tmp_path: Path) -> None:
        docs_dir = tmp_path / "docs"
        adr_dir = docs_dir / "adr"
        adr_dir.mkdir(parents=True)
        (adr_dir / "001-auth-jwt.md").write_text("# JWT 선택 사유", encoding="utf-8")

        result = build_context(
            agent="architect",
            skeleton_path=docs_dir / "skeleton.md",
            docs_dir=docs_dir,
        )

        assert "JWT 선택 사유" in result

    def test_project_root_claude_md_injected_before_extra_docs(self, tmp_path: Path) -> None:
        """프로젝트 루트 CLAUDE.md 가 있으면 모든 에이전트 컨텍스트에 포함된다."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "skeleton.md").write_text(SAMPLE_SKELETON, encoding="utf-8")
        (tmp_path / "CLAUDE.md").write_text(
            "# Root CLAUDE.md\n- snake_case 필수\n- 테스트 먼저",
            encoding="utf-8",
        )

        for agent in ("architect", "backend_coder", "frontend_coder", "qa"):
            result = build_context(
                agent=agent,
                skeleton_path=docs_dir / "skeleton.md",
                docs_dir=docs_dir,
                project_root=tmp_path,
            )
            assert "Root CLAUDE.md" in result, f"{agent}: root CLAUDE.md 누락"
            assert "snake_case 필수" in result, f"{agent}: root CLAUDE.md 내용 누락"

    def test_project_root_claude_md_absent_does_not_error(self, tmp_path: Path) -> None:
        """프로젝트 루트에 CLAUDE.md 가 없으면 조용히 건너뛴다."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "skeleton.md").write_text(SAMPLE_SKELETON, encoding="utf-8")

        result = build_context(
            agent="architect",
            skeleton_path=docs_dir / "skeleton.md",
            docs_dir=docs_dir,
            project_root=tmp_path,  # CLAUDE.md 없는 루트
        )

        assert "Root CLAUDE.md" not in result
        # skeleton 은 여전히 포함
        assert "Sample App" in result

    def test_project_root_none_behaves_as_before(self, tmp_path: Path) -> None:
        """project_root=None (기본값) 이면 기존 동작과 동일."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "skeleton.md").write_text(SAMPLE_SKELETON, encoding="utf-8")

        result = build_context(
            agent="architect",
            skeleton_path=docs_dir / "skeleton.md",
            docs_dir=docs_dir,
            # project_root 생략
        )

        assert "Sample App" in result

    def test_project_root_claude_md_precedes_extra_docs(self, tmp_path: Path) -> None:
        """루트 CLAUDE.md 가 EXTRA_DOCS conventions.md 보다 앞에 위치한다."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "conventions.md").write_text("# Conventions\n- tabsize 4", encoding="utf-8")
        (tmp_path / "CLAUDE.md").write_text("# Root Rules\n- 최우선 규칙", encoding="utf-8")

        result = build_context(
            agent="architect",
            skeleton_path=docs_dir / "skeleton.md",
            docs_dir=docs_dir,
            project_root=tmp_path,
        )

        root_pos = result.index("Root Rules")
        conv_pos = result.index("Conventions")
        assert root_pos < conv_pos, "루트 CLAUDE.md 가 conventions.md 보다 먼저 나와야 함"


# ── harness-global guidelines 직접 로드 ───────────────────────────────────


class TestHarnessGlobalDocs:
    """mobile_coder 가 harness/templates/guidelines/<framework>/ 를 직접 로드.

    docs/guidelines/ 가 비어 있어도 외부 사용자가 즉시 production-grade 컨벤션을 받음.
    """

    def test_mobile_coder_rn_loads_harness_guidelines(self, tmp_path: Path) -> None:
        """mobile_coder_rn 이 templates/guidelines/react-native-expo/*.md 4개를 context 에 포함."""
        # Harness dir mock — templates/guidelines/react-native-expo/ 4 파일 작성
        harness = tmp_path / "harness"
        rn_guidelines = harness / "templates" / "guidelines" / "react-native-expo"
        rn_guidelines.mkdir(parents=True)
        (rn_guidelines / "navigation.md").write_text(
            "# RN Nav\nExpo Router rules.", encoding="utf-8"
        )
        (rn_guidelines / "state.md").write_text("# RN State\nZustand rules.", encoding="utf-8")
        (rn_guidelines / "storage.md").write_text(
            "# RN Storage\nSecureStore rules.", encoding="utf-8"
        )
        (rn_guidelines / "style.md").write_text("# RN Style\nNativeWind rules.", encoding="utf-8")

        # Project dir mock — empty docs/
        project = tmp_path / "project"
        project.mkdir()
        (project / "docs").mkdir()

        result = build_context(
            agent="mobile_coder_rn",
            skeleton_path=project / "docs" / "skeleton.md",
            docs_dir=project / "docs",
            project_root=project,
            harness_dir=harness,
        )

        # 4개 guidelines 본문이 모두 context 에 포함
        assert "Expo Router rules" in result
        assert "Zustand rules" in result
        assert "SecureStore rules" in result
        assert "NativeWind rules" in result

    def test_mobile_coder_flutter_loads_harness_guidelines(self, tmp_path: Path) -> None:
        """mobile_coder_flutter 가 templates/guidelines/flutter/*.md 4개를 받음."""
        harness = tmp_path / "harness"
        flutter_guidelines = harness / "templates" / "guidelines" / "flutter"
        flutter_guidelines.mkdir(parents=True)
        (flutter_guidelines / "navigation.md").write_text(
            "# Flutter Nav\ngo_router rules.", encoding="utf-8"
        )
        (flutter_guidelines / "state.md").write_text(
            "# Flutter State\nRiverpod rules.", encoding="utf-8"
        )
        (flutter_guidelines / "storage.md").write_text(
            "# Flutter Storage\ndrift rules.", encoding="utf-8"
        )
        (flutter_guidelines / "style.md").write_text(
            "# Flutter Style\nThemeData rules.", encoding="utf-8"
        )

        project = tmp_path / "project"
        project.mkdir()
        (project / "docs").mkdir()

        result = build_context(
            agent="mobile_coder_flutter",
            skeleton_path=project / "docs" / "skeleton.md",
            docs_dir=project / "docs",
            project_root=project,
            harness_dir=harness,
        )

        assert "go_router rules" in result
        assert "Riverpod rules" in result
        assert "drift rules" in result
        assert "ThemeData rules" in result

    def test_harness_dir_none_skips_global_docs(self, tmp_path: Path) -> None:
        """harness_dir=None (legacy 호환) 시 EXTRA_HARNESS_DOCS 로딩 안 됨."""
        # mobile_coder_rn 이지만 harness_dir 미지정
        project = tmp_path / "project"
        project.mkdir()
        (project / "docs").mkdir()

        result = build_context(
            agent="mobile_coder_rn",
            skeleton_path=project / "docs" / "skeleton.md",
            docs_dir=project / "docs",
            project_root=project,
            harness_dir=None,
        )

        # harness 본문 키워드 없음 (loading skipped)
        assert "Expo Router" not in result
        assert "Zustand" not in result

    def test_non_mobile_agent_unaffected_by_harness_dir(self, tmp_path: Path) -> None:
        """backend_coder 는 EXTRA_HARNESS_DOCS 에 없으므로 harness_dir 영향 X."""
        harness = tmp_path / "harness"
        # 가상의 backend guidelines 파일 — backend_coder 매핑에 없으니 무시되어야
        backend_guidelines = harness / "templates" / "guidelines" / "should-not-load"
        backend_guidelines.mkdir(parents=True)
        (backend_guidelines / "ghost.md").write_text("SECRET_GHOST", encoding="utf-8")

        project = tmp_path / "project"
        project.mkdir()
        (project / "docs").mkdir()

        result = build_context(
            agent="backend_coder",
            skeleton_path=project / "docs" / "skeleton.md",
            docs_dir=project / "docs",
            project_root=project,
            harness_dir=harness,
        )

        assert "SECRET_GHOST" not in result
