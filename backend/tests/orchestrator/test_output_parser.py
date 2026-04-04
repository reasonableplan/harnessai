"""output_parser 테스트."""

import pytest

from src.orchestrator.output_parser import (
    PhaseReviewResult,
    PRReviewResult,
    ReviewVerdict,
    SkeletonSection,
    TaskItem,
    extract_filled_sections,
    parse_phase_review,
    parse_phases,
    parse_pr_review,
    parse_task_list,
)


# ---------------------------------------------------------------------------
# PR 리뷰 파싱
# ---------------------------------------------------------------------------

class TestParsePRReview:
    def test_approve(self) -> None:
        output = """
## Review Result: APPROVE

### 권장 사항
1. api.py:42 — 에러 메시지를 더 구체적으로

### shared-lessons 확인
- 패턴 반복 여부: 없음
"""
        result = parse_pr_review(output)
        assert result is not None
        assert result.verdict == ReviewVerdict.APPROVE
        assert result.violations == []
        assert "api.py:42" in result.suggestions[0]

    def test_reject_with_violations(self) -> None:
        output = """
## Review Result: REJECT

### 위반 사항
1. [골든 원칙 1번 위반] models.py:10 — skeleton에 없는 테이블 추가 — 제거하라
2. [골든 원칙 7번 위반] service.py:55 — raw SQL 사용 — ORM으로 교체

### 권장 사항
1. 타입 힌트 추가 권장
"""
        result = parse_pr_review(output)
        assert result is not None
        assert result.verdict == ReviewVerdict.REJECT
        assert len(result.violations) == 2
        assert "models.py:10" in result.violations[0]
        assert "service.py:55" in result.violations[1]
        assert len(result.suggestions) == 1

    def test_case_insensitive_verdict(self) -> None:
        output = "## Review Result: approve\n"
        result = parse_pr_review(output)
        assert result is not None
        assert result.verdict == ReviewVerdict.APPROVE

    def test_no_review_result_returns_none(self) -> None:
        output = "에이전트가 작업 중입니다..."
        result = parse_pr_review(output)
        assert result is None

    def test_raw_output_preserved(self) -> None:
        output = "## Review Result: APPROVE\n\n내용"
        result = parse_pr_review(output)
        assert result is not None
        assert result.raw == output

    def test_empty_violations_on_approve(self) -> None:
        output = "## Review Result: APPROVE\n"
        result = parse_pr_review(output)
        assert result is not None
        assert result.violations == []
        assert result.suggestions == []


# ---------------------------------------------------------------------------
# Phase 리뷰 파싱
# ---------------------------------------------------------------------------

class TestParsePhaseReview:
    def test_approve_can_proceed(self) -> None:
        output = """
## Phase 1 Review Result: APPROVE

### 미구현 항목
없음

### 연동 오류
없음

### 흐름 검증
- 이슈 생성 흐름 — 통과
- 로그인 흐름 — 통과

### 다음 Phase 진행 가능 여부
- 가능
"""
        result = parse_phase_review(output)
        assert result is not None
        assert result.phase == 1
        assert result.verdict == ReviewVerdict.APPROVE
        assert result.can_proceed is True
        assert len(result.flow_results) == 2

    def test_reject_with_missing_items(self) -> None:
        output = """
## Phase 1 Review Result: REJECT

### 미구현 항목
- API: POST /issues — 구현 없음
- 화면: IssueCreateModal — 구현 없음

### 연동 오류
- IssueResponse.projectId vs Issue.project_id — 불일치

### 흐름 검증
- 이슈 생성 흐름 — 막힘 (CreateModal 없음)

### 다음 Phase 진행 가능 여부
- 불가 (재작업 필요 태스크: T-003, T-004)
"""
        result = parse_phase_review(output)
        assert result is not None
        assert result.phase == 1
        assert result.verdict == ReviewVerdict.REJECT
        assert result.can_proceed is False
        assert len(result.missing_items) == 2
        assert "POST /issues" in result.missing_items[0]
        assert len(result.integration_errors) == 1
        assert len(result.flow_results) == 1

    def test_phase_number_extracted(self) -> None:
        output = "## Phase 3 Review Result: APPROVE\n"
        result = parse_phase_review(output)
        assert result is not None
        assert result.phase == 3

    def test_no_phase_review_returns_none(self) -> None:
        output = "## Review Result: APPROVE\n"  # PR 리뷰 형식
        result = parse_phase_review(output)
        assert result is None

    def test_case_insensitive(self) -> None:
        output = "## Phase 2 Review Result: reject\n"
        result = parse_phase_review(output)
        assert result is not None
        assert result.verdict == ReviewVerdict.REJECT


# ---------------------------------------------------------------------------
# 태스크 목록 파싱
# ---------------------------------------------------------------------------

class TestParseTaskList:
    def test_basic_task_table(self) -> None:
        output = """
### Phase 1 태스크 (MVP)
| ID | 담당 | 의존성 | 설명 | 상태 |
|----|------|--------|------|------|
| T-001 | backend_coder |  | 이슈 모델 생성 | 대기 |
| T-002 | backend_coder | T-001 | 이슈 CRUD API | 대기 |
| T-003 | frontend_coder | T-002 | IssueList 컴포넌트 | 대기 |
"""
        tasks = parse_task_list(output)
        assert len(tasks) == 3
        assert tasks[0].id == "T-001"
        assert tasks[0].agent == "backend_coder"
        assert tasks[0].depends_on == []
        assert tasks[1].id == "T-002"
        assert tasks[1].depends_on == ["T-001"]
        assert tasks[2].id == "T-003"
        assert tasks[2].agent == "frontend_coder"

    def test_multiple_dependencies(self) -> None:
        output = """
| ID | 담당 | 의존성 | 설명 | 상태 |
|----|------|--------|------|------|
| T-004 | frontend_coder | T-002, T-003 | 페이지 조합 | 대기 |
"""
        tasks = parse_task_list(output)
        assert len(tasks) == 1
        assert tasks[0].depends_on == ["T-002", "T-003"]

    def test_phase_review_task(self) -> None:
        output = """
| ID | 담당 | 의존성 | 설명 | 상태 |
|----|------|--------|------|------|
| P1-REVIEW | Reviewer | Phase 1 전체 | Phase 1 리뷰 | 대기 |
"""
        tasks = parse_task_list(output)
        assert len(tasks) == 1
        assert tasks[0].id == "P1-REVIEW"
        assert tasks[0].agent == "Reviewer"

    def test_empty_output_returns_empty(self) -> None:
        tasks = parse_task_list("태스크가 없습니다.")
        assert tasks == []

    def test_status_preserved(self) -> None:
        output = """
| ID | 담당 | 의존성 | 설명 | 상태 |
|----|------|--------|------|------|
| T-001 | backend_coder |  | 설명 | 완료 |
"""
        tasks = parse_task_list(output)
        assert tasks[0].status == "완료"


# ---------------------------------------------------------------------------
# Skeleton 섹션 추출
# ---------------------------------------------------------------------------

class TestExtractFilledSections:
    def test_single_section(self) -> None:
        output = """
에이전트 분석 완료. 아래 섹션을 작성했습니다.

## 6. DB 스키마

### 테이블: issues
| 컬럼 | 타입 | 제약 |
|------|------|------|
| id | Integer | PK |
| title | String(200) | NOT NULL |
"""
        sections = extract_filled_sections(output)
        assert len(sections) == 1
        assert sections[0].section_num == "6"
        assert "issues" in sections[0].content

    def test_multiple_sections(self) -> None:
        output = """
## 6. DB 스키마

테이블 정의...

## 7. API 스키마

엔드포인트 정의...
"""
        sections = extract_filled_sections(output)
        assert len(sections) == 2
        assert sections[0].section_num == "6"
        assert sections[1].section_num == "7"

    def test_subsection(self) -> None:
        output = """
### 14-1. 하네스 원칙

원칙 내용...
"""
        sections = extract_filled_sections(output)
        assert len(sections) == 1
        assert sections[0].section_num == "14-1"

    def test_no_sections_returns_empty(self) -> None:
        output = "단순 텍스트 출력입니다."
        sections = extract_filled_sections(output)
        assert sections == []

    def test_content_does_not_bleed_into_next_section(self) -> None:
        output = """
## 6. DB 스키마

섹션 6 내용

## 7. API 스키마

섹션 7 내용
"""
        sections = extract_filled_sections(output)
        assert "섹션 7" not in sections[0].content
        assert "섹션 6" not in sections[1].content


# ---------------------------------------------------------------------------
# parse_phases()
# ---------------------------------------------------------------------------

_SINGLE_PHASE_OUTPUT = """\
### Phase 1 — MVP
| ID | 에이전트 | 의존성 | 설명 | 상태 |
|---|---|---|---|---|
| T-001 | backend_coder | - | DB 모델 구현 | 대기 |
| T-002 | backend_coder | T-001 | API 엔드포인트 구현 | 대기 |
"""

_TWO_PHASE_OUTPUT = """\
### Phase 1 — MVP
| ID | 에이전트 | 의존성 | 설명 | 상태 |
|---|---|---|---|---|
| T-001 | backend_coder | - | DB 모델 구현 | 대기 |

### Phase 2 — 확장
| ID | 에이전트 | 의존성 | 설명 | 상태 |
|---|---|---|---|---|
| T-010 | frontend_coder | - | 프론트엔드 구현 | 대기 |
"""


class TestParsePhases:
    def test_single_phase(self) -> None:
        phases = parse_phases(_SINGLE_PHASE_OUTPUT)
        assert len(phases) == 1
        assert len(phases[0]) == 2
        assert phases[0][0].id == "T-001"
        assert phases[0][0].agent == "backend_coder"

    def test_two_phases(self) -> None:
        phases = parse_phases(_TWO_PHASE_OUTPUT)
        assert len(phases) == 2
        assert phases[0][0].id == "T-001"
        assert phases[1][0].id == "T-010"
        assert phases[1][0].agent == "frontend_coder"

    def test_no_phase_header_fallback_to_single(self) -> None:
        """Phase 헤더 없으면 전체를 단일 Phase로 처리."""
        output = """\
| ID | 에이전트 | 의존성 | 설명 | 상태 |
|---|---|---|---|---|
| T-001 | backend_coder | - | DB 모델 | 대기 |
"""
        phases = parse_phases(output)
        assert len(phases) == 1
        assert phases[0][0].id == "T-001"

    def test_empty_output_returns_empty(self) -> None:
        assert parse_phases("") == []
        assert parse_phases("관련 없는 텍스트") == []

    def test_phase_header_with_no_tasks_excluded(self) -> None:
        """태스크 없는 Phase는 결과에서 제외."""
        output = """\
### Phase 1 — MVP
설명만 있고 테이블 없음

### Phase 2 — 확장
| ID | 에이전트 | 의존성 | 설명 | 상태 |
|---|---|---|---|---|
| T-010 | frontend_coder | - | 구현 | 대기 |
"""
        phases = parse_phases(output)
        assert len(phases) == 1
        assert phases[0][0].id == "T-010"

    def test_depends_on_parsed(self) -> None:
        output = """\
### Phase 1 — MVP
| ID | 에이전트 | 의존성 | 설명 | 상태 |
|---|---|---|---|---|
| T-002 | backend_coder | T-001 | API 구현 | 대기 |
"""
        phases = parse_phases(output)
        assert phases[0][0].depends_on == ["T-001"]

    def test_depends_on_dash_is_empty(self) -> None:
        """`-`는 의존성 없음을 의미 — 빈 리스트여야 함."""
        output = """\
### Phase 1 — MVP
| ID | 에이전트 | 의존성 | 설명 | 상태 |
|---|---|---|---|---|
| T-001 | backend_coder | - | DB 모델 | 대기 |
"""
        phases = parse_phases(output)
        assert phases[0][0].depends_on == []

    def test_preamble_text_before_phase_header(self) -> None:
        """Phase 헤더 앞 설명 텍스트가 있어도 올바르게 파싱."""
        output = (
            "태스크를 다음과 같이 분해합니다:\n\n"
            "### Phase 1 — MVP\n"
            "| ID | 에이전트 | 의존성 | 설명 | 상태 |\n"
            "|---|---|---|---|---|\n"
            "| T-001 | backend_coder | - | DB 모델 | 대기 |\n"
        )
        phases = parse_phases(output)
        assert len(phases) == 1
        assert phases[0][0].id == "T-001"

    def test_phase_header_case_insensitive(self) -> None:
        output = """\
### phase 1 — MVP
| ID | 에이전트 | 의존성 | 설명 | 상태 |
|---|---|---|---|---|
| T-001 | backend_coder | - | 구현 | 대기 |
"""
        phases = parse_phases(output)
        assert len(phases) == 1
