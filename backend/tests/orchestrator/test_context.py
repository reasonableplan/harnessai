"""Skeleton 컨텍스트 주입 테스트."""

from pathlib import Path

from src.orchestrator.context import (
    AGENT_SECTIONS_BY_ID,
    SECTION_MAP,
    SECTION_TITLES,
    build_context,
    extract_section,
    extract_section_by_id,
    fill_skeleton_template,
)

SAMPLE_SKELETON = """\
# Project Skeleton

## 1. Overview
- **프로젝트명**: Test
- **한 줄 설명**: 테스트 프로젝트

## 2. 기능 요구사항
### 핵심 기능 (MVP)
- [ ] 기능 A
- [ ] 기능 B

## 3. 기술 스택
### 프론트엔드
- React

### 백엔드
- FastAPI

## 7. API 스키마
### 엔드포인트
| Method | Path |
|--------|------|
| GET    | /api |

## 8. UI/UX
### 화면 목록
- 대시보드
- 설정

## 14. 하네스 설계
### 14-1. 에이전트 역할 정의표
| 에이전트 | 모델 |
|---------|------|
| Architect | Opus |

### 14-4. 골든 원칙
1. 계약 우선
2. 화이트리스트 강제

## 18. 규칙
- 금지 패턴
"""


class TestExtractSection:
    def test_extract_existing_section(self) -> None:
        result = extract_section(SAMPLE_SKELETON, 1)
        assert "프로젝트명" in result
        assert "Test" in result

    def test_extract_section_with_content(self) -> None:
        result = extract_section(SAMPLE_SKELETON, 7)
        assert "API 스키마" in result
        assert "/api" in result

    def test_extract_nonexistent_section(self) -> None:
        result = extract_section(SAMPLE_SKELETON, 99)
        assert result == ""

    def test_extract_subsection(self) -> None:
        result = extract_section(SAMPLE_SKELETON, "14-1")
        assert "에이전트 역할 정의표" in result
        assert "Opus" in result

    def test_extract_subsection_14_4(self) -> None:
        result = extract_section(SAMPLE_SKELETON, "14-4")
        assert "골든 원칙" in result
        assert "계약 우선" in result

    def test_extract_with_frontend_suffix(self) -> None:
        # "3-frontend"는 섹션 3 전체를 반환
        result = extract_section(SAMPLE_SKELETON, "3-frontend")
        assert "기술 스택" in result

    def test_extract_wildcard(self) -> None:
        result = extract_section(SAMPLE_SKELETON, "*")
        assert result == SAMPLE_SKELETON

    def test_section_boundary(self) -> None:
        """섹션이 다음 섹션 직전에서 끝나는지 확인."""
        result = extract_section(SAMPLE_SKELETON, 1)
        assert "기능 요구사항" not in result  # 섹션 2 내용이 포함되면 안 됨


class TestSectionMap:
    def test_all_agents_have_mapping(self) -> None:
        expected = {"architect", "designer", "orchestrator", "backend_coder",
                    "frontend_coder", "reviewer", "qa"}
        assert set(SECTION_MAP.keys()) == expected

    def test_architect_gets_all(self) -> None:
        assert SECTION_MAP["architect"] == ["*"]

    def test_coder_gets_limited_sections(self) -> None:
        backend_sections = SECTION_MAP["backend_coder"]
        assert "*" not in backend_sections
        assert 8 not in backend_sections  # UI/UX는 백엔드 코더에 불필요


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

    def test_backend_coder_gets_limited_context(self, tmp_path: Path) -> None:
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "skeleton.md").write_text(SAMPLE_SKELETON, encoding="utf-8")

        result = build_context(
            agent="backend_coder",
            skeleton_path=docs_dir / "skeleton.md",
            docs_dir=docs_dir,
        )

        assert "API 스키마" in result  # 섹션 7 포함
        assert "관련 섹션" in result   # 전체가 아닌 필터링 버전

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


# ── fill_skeleton_template() ─────────────────────────────────────────────────

SAMPLE_TEMPLATE = """\
## 1. 개요
- 프로젝트명: _미정_

## 6. DB 스키마
_미작성_

## 7. API 스키마
_미작성_
"""


class TestFillSkeletonTemplate:
    def test_replaces_matching_section(self) -> None:
        sections = [{"section_num": "6", "content": "## 6. DB 스키마\n| 컬럼 | 타입 |\n|------|------|\n| id | UUID |"}]
        result = fill_skeleton_template(SAMPLE_TEMPLATE, sections)

        assert "| id | UUID |" in result
        assert "_미작성_" not in result.split("## 7.")[0]  # 섹션 6의 _미작성_ 교체됨

    def test_untouched_sections_preserved(self) -> None:
        sections = [{"section_num": "6", "content": "## 6. DB 스키마\n채워짐"}]
        result = fill_skeleton_template(SAMPLE_TEMPLATE, sections)

        assert "## 7. API 스키마" in result
        assert "_미작성_" in result  # 섹션 7은 그대로

    def test_empty_sections_returns_template(self) -> None:
        result = fill_skeleton_template(SAMPLE_TEMPLATE, [])
        assert result == SAMPLE_TEMPLATE

    def test_later_section_overwrites_earlier(self) -> None:
        sections = [
            {"section_num": "6", "content": "## 6. DB 스키마\n첫 번째"},
            {"section_num": "6", "content": "## 6. DB 스키마\n두 번째"},
        ]
        result = fill_skeleton_template(SAMPLE_TEMPLATE, sections)
        assert "두 번째" in result
        assert "첫 번째" not in result

    def test_unknown_section_ignored(self) -> None:
        sections = [{"section_num": "99", "content": "## 99. 없는 섹션\n내용"}]
        result = fill_skeleton_template(SAMPLE_TEMPLATE, sections)
        assert result == SAMPLE_TEMPLATE


# ── Harness v2 ── 섹션 ID 기반 ─────────────────────────────────────────

# Harness v2 조각 형식 (skeleton_assembler 출력 모방). 헤딩 제목은
# SECTION_TITLES 와 정확히 일치해야 함.
SAMPLE_SKELETON_V2 = """\
# Project Skeleton — Sample

## 1. 프로젝트 개요
- **프로젝트명**: Sample CLI
- **한 줄 설명**: 테스트 도구

## 2. 기술 스택
### 런타임 / 언어
- Python 3.12

## 3. 에러 핸들링
### 에러 분류 체계
| 코드 | 의미 |
|------|------|
| `PARSE_001` | 파싱 실패 |

## 4. CLI 커맨드
### 엔트리포인트
- 실행: `sample`

## 5. 도메인 로직
### 핵심 비즈니스 규칙
1. 입력 검증

## 6. 태스크 분해
| ID | Component |
|----|-----------|
"""


class TestSectionTitlesMap:
    def test_all_20_standard_sections_present(self) -> None:
        expected_ids = {
            "overview", "requirements", "stack", "configuration", "errors",
            "auth", "persistence", "integrations",
            "interface.http", "interface.cli", "interface.ipc", "interface.sdk",
            "view.screens", "view.components", "state.flow", "core.logic",
            "observability", "deployment", "tasks", "notes",
        }
        assert set(SECTION_TITLES.keys()) == expected_ids


class TestAgentSectionsById:
    def test_all_agents_have_id_mapping(self) -> None:
        expected = {"architect", "designer", "orchestrator", "backend_coder",
                    "frontend_coder", "reviewer", "qa"}
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
        assert extract_section_by_id(SAMPLE_SKELETON_V2, "*") == SAMPLE_SKELETON_V2

    def test_extract_overview(self) -> None:
        result = extract_section_by_id(SAMPLE_SKELETON_V2, "overview")
        assert "Sample CLI" in result
        assert "테스트 도구" in result

    def test_extract_interface_cli(self) -> None:
        result = extract_section_by_id(SAMPLE_SKELETON_V2, "interface.cli")
        assert "엔트리포인트" in result
        assert "sample" in result

    def test_extract_errors(self) -> None:
        result = extract_section_by_id(SAMPLE_SKELETON_V2, "errors")
        assert "PARSE_001" in result

    def test_section_boundary_respected(self) -> None:
        result = extract_section_by_id(SAMPLE_SKELETON_V2, "stack")
        assert "Python 3.12" in result
        # 다음 섹션 (errors) 내용이 새지 않아야
        assert "PARSE_001" not in result

    def test_unknown_id_returns_empty(self) -> None:
        assert extract_section_by_id(SAMPLE_SKELETON_V2, "totally-fake") == ""

    def test_id_not_in_skeleton_returns_empty(self) -> None:
        # auth 는 표준 ID 이지만 SAMPLE 에 헤딩 없음
        assert extract_section_by_id(SAMPLE_SKELETON_V2, "auth") == ""


class TestBuildContextWithSectionIds:
    def test_use_section_ids_filters_for_backend_coder(self, tmp_path: Path) -> None:
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "skeleton.md").write_text(SAMPLE_SKELETON_V2, encoding="utf-8")

        result = build_context(
            agent="backend_coder",
            skeleton_path=docs_dir / "skeleton.md",
            docs_dir=docs_dir,
            use_section_ids=True,
        )

        # backend_coder 는 errors, core.logic 포함, view.screens 미포함 (SAMPLE에 없음)
        assert "PARSE_001" in result
        assert "관련 섹션" in result

    def test_use_section_ids_architect_gets_all(self, tmp_path: Path) -> None:
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "skeleton.md").write_text(SAMPLE_SKELETON_V2, encoding="utf-8")

        result = build_context(
            agent="architect",
            skeleton_path=docs_dir / "skeleton.md",
            docs_dir=docs_dir,
            use_section_ids=True,
        )

        assert "Sample CLI" in result
        # architect 는 전체이므로 "관련 섹션" 마커 없음
        assert "관련 섹션" not in result

    def test_legacy_default_unchanged(self, tmp_path: Path) -> None:
        """use_section_ids=False (기본) 면 기존 SECTION_MAP 사용."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "skeleton.md").write_text(SAMPLE_SKELETON, encoding="utf-8")

        result = build_context(
            agent="backend_coder",
            skeleton_path=docs_dir / "skeleton.md",
            docs_dir=docs_dir,
        )
        # 레거시 매핑 — API 스키마 (섹션 7) 포함
        assert "API 스키마" in result
