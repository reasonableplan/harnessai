"""에이전트 출력 파서 — raw 문자열에서 구조화된 결과를 추출한다."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum


class ReviewVerdict(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class DesignVerdict(StrEnum):
    ACCEPT = "ACCEPT"
    CONFLICT = "CONFLICT"


@dataclass
class DesignNegotiationResult:
    """Designer의 설계 협의 결과."""

    verdict: DesignVerdict
    api_requests: list[str] = field(default_factory=list)
    raw: str = ""


@dataclass
class PRReviewResult:
    """Reviewer의 PR 리뷰 결과."""

    verdict: ReviewVerdict
    violations: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    raw: str = ""


@dataclass
class PhaseReviewResult:
    """Reviewer의 Phase 리뷰 결과."""

    phase: int
    verdict: ReviewVerdict
    missing_items: list[str] = field(default_factory=list)
    integration_errors: list[str] = field(default_factory=list)
    flow_results: list[str] = field(default_factory=list)
    can_proceed: bool = False
    raw: str = ""


@dataclass
class TaskItem:
    """Orchestrator가 분해한 태스크 하나."""

    id: str
    agent: str
    depends_on: list[str]
    description: str
    status: str


@dataclass
class SkeletonSection:
    """에이전트가 채운 skeleton 섹션."""

    section_num: str  # "6", "7", "17" 등
    content: str


# ---------------------------------------------------------------------------
# PR 리뷰 파싱
# ---------------------------------------------------------------------------

_VERDICT_PATTERN = re.compile(
    r"##\s+Review\s+Result\s*:\s*(APPROVE|REJECT)",
    re.IGNORECASE,
)
_VIOLATION_BLOCK = re.compile(
    r"###\s+위반\s*사항.*?\n(.*?)(?=###|\Z)",
    re.DOTALL | re.IGNORECASE,
)
_SUGGESTION_BLOCK = re.compile(
    r"###\s+권장\s*사항.*?\n(.*?)(?=###|\Z)",
    re.DOTALL | re.IGNORECASE,
)
_NUMBERED_LINE = re.compile(r"^\s*\d+\.\s+(.+)$", re.MULTILINE)


def parse_pr_review(output: str) -> PRReviewResult | None:
    """Reviewer PR 리뷰 출력을 파싱한다.

    Returns:
        PRReviewResult, 또는 리뷰 결과를 찾을 수 없으면 None.
    """
    verdict_match = _VERDICT_PATTERN.search(output)
    if not verdict_match:
        return None

    verdict = ReviewVerdict(verdict_match.group(1).upper())

    violations: list[str] = []
    violation_match = _VIOLATION_BLOCK.search(output)
    if violation_match:
        violations = _NUMBERED_LINE.findall(violation_match.group(1))

    suggestions: list[str] = []
    suggestion_match = _SUGGESTION_BLOCK.search(output)
    if suggestion_match:
        suggestions = _NUMBERED_LINE.findall(suggestion_match.group(1))

    return PRReviewResult(
        verdict=verdict,
        violations=violations,
        suggestions=suggestions,
        raw=output,
    )


# ---------------------------------------------------------------------------
# Phase 리뷰 파싱
# ---------------------------------------------------------------------------

_PHASE_VERDICT_PATTERN = re.compile(
    r"##\s+Phase\s+(\d+)\s+Review\s+Result\s*:\s*(APPROVE|REJECT)",
    re.IGNORECASE,
)
_MISSING_BLOCK = re.compile(
    r"###\s+미구현\s*항목.*?\n(.*?)(?=###|\Z)",
    re.DOTALL | re.IGNORECASE,
)
_INTEGRATION_BLOCK = re.compile(
    r"###\s+연동\s*오류.*?\n(.*?)(?=###|\Z)",
    re.DOTALL | re.IGNORECASE,
)
_FLOW_BLOCK = re.compile(
    r"###\s+흐름\s*검증.*?\n(.*?)(?=###|\Z)",
    re.DOTALL | re.IGNORECASE,
)
_PROCEED_PATTERN = re.compile(
    r"다음\s+Phase\s+진행\s+가능\s+여부.*?(불가능|불가|가능)",
    re.DOTALL | re.IGNORECASE,
)
_BULLET_LINE = re.compile(r"^\s*[-*]\s+(.+)$", re.MULTILINE)


def parse_phase_review(output: str) -> PhaseReviewResult | None:
    """Reviewer Phase 리뷰 출력을 파싱한다.

    Returns:
        PhaseReviewResult, 또는 Phase 리뷰 결과를 찾을 수 없으면 None.
    """
    verdict_match = _PHASE_VERDICT_PATTERN.search(output)
    if not verdict_match:
        return None

    phase = int(verdict_match.group(1))
    verdict = ReviewVerdict(verdict_match.group(2).upper())

    missing_items: list[str] = []
    missing_match = _MISSING_BLOCK.search(output)
    if missing_match:
        missing_items = _BULLET_LINE.findall(missing_match.group(1))

    integration_errors: list[str] = []
    integration_match = _INTEGRATION_BLOCK.search(output)
    if integration_match:
        integration_errors = _BULLET_LINE.findall(integration_match.group(1))

    flow_results: list[str] = []
    flow_match = _FLOW_BLOCK.search(output)
    if flow_match:
        flow_results = _BULLET_LINE.findall(flow_match.group(1))

    can_proceed = False
    proceed_match = _PROCEED_PATTERN.search(output)
    if proceed_match:
        can_proceed = proceed_match.group(1) == "가능"

    return PhaseReviewResult(
        phase=phase,
        verdict=verdict,
        missing_items=missing_items,
        integration_errors=integration_errors,
        flow_results=flow_results,
        can_proceed=can_proceed,
        raw=output,
    )


# ---------------------------------------------------------------------------
# 태스크 목록 파싱
# ---------------------------------------------------------------------------

# 마크다운 테이블 행 파싱 — | T-001 | backend_coder | T-000 | 설명 | 대기 |
_TASK_TABLE_ROW = re.compile(
    r"^\|\s*([A-Z0-9\-]+)\s*\|\s*(\w+)\s*\|\s*([^|]*?)\s*\|\s*(.+?)\s*\|\s*(\S+)\s*\|",
    re.MULTILINE,
)
_TASK_HEADER_ROW = re.compile(r"^\|\s*ID\s*\|", re.MULTILINE | re.IGNORECASE)
# Phase 헤더 — "### Phase 1", "## Phase 2 — 확장" 등
_PHASE_HEADER = re.compile(r"^#{1,4}\s+Phase\s+(\d+)", re.MULTILINE | re.IGNORECASE)
_TASK_SEPARATOR_ROW = re.compile(r"^\|[-| ]+\|", re.MULTILINE)


def parse_task_list(output: str) -> list[TaskItem]:
    """Orchestrator 출력에서 태스크 목록을 파싱한다.

    Returns:
        TaskItem 리스트. 없으면 빈 리스트.
    """
    tasks: list[TaskItem] = []

    for match in _TASK_TABLE_ROW.finditer(output):
        task_id = match.group(1).strip()
        agent = match.group(2).strip()
        depends_raw = match.group(3).strip()
        description = match.group(4).strip()
        status = match.group(5).strip()

        # 헤더/구분자 행 제외
        if task_id.upper() in ("ID", "----", "---"):
            continue
        if re.match(r"^-+$", task_id):
            continue

        depends_on = (
            [d.strip() for d in depends_raw.split(",") if d.strip() and d.strip() != "-"]
            if depends_raw
            else []
        )

        tasks.append(TaskItem(
            id=task_id,
            agent=agent,
            depends_on=depends_on,
            description=description,
            status=status,
        ))

    return tasks


def parse_phases(output: str) -> list[list[TaskItem]]:
    """Orchestrator 출력에서 Phase별 태스크 목록을 파싱한다.

    ``### Phase N`` 헤딩 아래 마크다운 테이블로 구성된 태스크를 읽는다.
    Phase 헤딩이 없으면 전체를 단일 Phase로 처리한다.

    Returns:
        Phase별 TaskItem 리스트. 태스크가 하나도 없으면 빈 리스트.
    """
    headers = list(_PHASE_HEADER.finditer(output))

    if not headers:
        tasks = parse_task_list(output)
        return [tasks] if tasks else []

    phases: list[list[TaskItem]] = []
    for i, header in enumerate(headers):
        start = header.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(output)
        tasks = parse_task_list(output[start:end])
        phases.append(tasks)  # 빈 Phase도 포함 — Phase 번호 일관성 유지

    return phases


# ---------------------------------------------------------------------------
# QA 리포트 파싱
# ---------------------------------------------------------------------------

_QA_HEALTH_SCORE = re.compile(
    r"###\s+Health\s+Score\s*:\s*(\d+)\s*/\s*10",
    re.IGNORECASE,
)
_QA_ISSUE_BLOCK = re.compile(
    r"###\s+발견된\s*이슈.*?\n(.*?)(?=###|\Z)",
    re.DOTALL | re.IGNORECASE,
)

# QA 통과 기준 — health score 이 값 이상이면 통과
QA_PASS_THRESHOLD = 7


@dataclass
class QaResult:
    """QA 에이전트 리포트 결과."""

    health_score: int  # 0-10
    passed: bool       # health_score >= QA_PASS_THRESHOLD
    issues: list[str] = field(default_factory=list)
    raw: str = ""


def parse_qa_report(output: str) -> QaResult | None:
    """QA 에이전트 리포트 출력을 파싱한다.

    Returns:
        QaResult, 또는 Health Score 헤딩을 찾을 수 없으면 None.
    """
    score_match = _QA_HEALTH_SCORE.search(output)
    if not score_match:
        return None

    health_score = int(score_match.group(1))

    issues: list[str] = []
    issue_match = _QA_ISSUE_BLOCK.search(output)
    if issue_match:
        issues = _NUMBERED_LINE.findall(issue_match.group(1))

    return QaResult(
        health_score=health_score,
        passed=health_score >= QA_PASS_THRESHOLD,
        issues=issues,
        raw=output,
    )


# ---------------------------------------------------------------------------
# 설계 협의 파싱
# ---------------------------------------------------------------------------

_DESIGN_VERDICT_PATTERN = re.compile(
    r"##\s+Design\s+Verdict\s*:\s*(ACCEPT|CONFLICT)",
    re.IGNORECASE,
)
_DESIGN_API_REQUEST_BLOCK = re.compile(
    r"###\s+API\s+요청사항.*?\n(.*?)(?=###|\Z)",
    re.DOTALL | re.IGNORECASE,
)


def parse_design_verdict(output: str) -> DesignNegotiationResult | None:
    """Designer 출력에서 설계 협의 결과를 파싱한다.

    Returns:
        DesignNegotiationResult, 또는 Verdict 마커가 없으면 None (ACCEPT로 처리).
    """
    verdict_match = _DESIGN_VERDICT_PATTERN.search(output)
    if not verdict_match:
        return None

    verdict = DesignVerdict(verdict_match.group(1).upper())

    api_requests: list[str] = []
    api_match = _DESIGN_API_REQUEST_BLOCK.search(output)
    if api_match:
        api_requests = _NUMBERED_LINE.findall(api_match.group(1))

    return DesignNegotiationResult(verdict=verdict, api_requests=api_requests, raw=output)


# ---------------------------------------------------------------------------
# Skeleton 섹션 파싱
# ---------------------------------------------------------------------------

_SECTION_HEADING = re.compile(
    r"^#{2,4}\s+(\d+(?:-\d+)?)[.\s]",
    re.MULTILINE,
)


def extract_filled_sections(output: str) -> list[SkeletonSection]:
    """에이전트 출력에서 skeleton 섹션 마크다운 블록을 추출한다.

    에이전트가 "## 6. DB 스키마" 같은 섹션 헤딩을 포함해서 출력하면
    해당 섹션 내용을 추출한다.

    Returns:
        SkeletonSection 리스트. 없으면 빈 리스트.
    """
    sections: list[SkeletonSection] = []
    lines = output.split("\n")
    i = 0

    while i < len(lines):
        heading_match = _SECTION_HEADING.match(lines[i])
        if heading_match:
            section_num = heading_match.group(1)
            heading_m = re.match(r"^(#+)", lines[i])
            if heading_m is None:
                i += 1
                continue
            heading_level = len(heading_m.group(1))
            start = i
            i += 1

            # 같은 레벨 이상의 다음 헤딩까지 수집
            while i < len(lines):
                next_heading = re.match(r"^(#+)\s+\d", lines[i])
                if next_heading and len(next_heading.group(1)) <= heading_level:
                    break
                i += 1

            content = "\n".join(lines[start:i]).strip()
            if content:
                sections.append(SkeletonSection(section_num=section_num, content=content))
        else:
            i += 1

    return sections
