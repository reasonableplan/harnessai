"""Skeleton 컨텍스트 주입 테스트."""

from pathlib import Path

from src.orchestrator.context import SECTION_MAP, build_context, extract_section

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
