"""skeleton_checklist 단위 테스트.

대상: `src/orchestrator/skeleton_checklist.py`
전략: 인메모리 skeleton 텍스트 fixture 로 finding 검증 (TDD).
"""

from __future__ import annotations

from src.orchestrator.skeleton_checklist import (
    ChecklistFinding,
    check_skeleton_quality,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _skel(*sections: tuple[str, str]) -> str:
    """Build a minimal skeleton text from (title, body) pairs."""
    parts: list[str] = []
    for i, (title, body) in enumerate(sections, start=1):
        parts.append(f"## {i}. {title}\n{body}")
    return "\n\n".join(parts)


def _findings_by_category(text: str, category: str) -> list[ChecklistFinding]:
    return [f for f in check_skeleton_quality(text) if f.category == category]


# ---------------------------------------------------------------------------
# Check 1: clarity — vague unquantified terms
# ---------------------------------------------------------------------------


def test_vague_word_produces_clarity_finding() -> None:
    """'빠르게' 단독 등장 -> clarity finding 1개."""
    skel = _skel(("HTTP API", "API는 빠르게 응답해야 한다."))
    findings = _findings_by_category(skel, "clarity")
    assert len(findings) == 1
    assert findings[0].severity == "warn"
    assert "빠르게" in findings[0].message
    assert findings[0].section_id == "HTTP API"


def test_quantified_expression_no_clarity_finding() -> None:
    """'p95 < 200ms 응답' 처럼 수치가 있으면 clarity finding 0개."""
    skel = _skel(("HTTP API", "API p95 < 200ms 응답 보장."))
    findings = _findings_by_category(skel, "clarity")
    assert findings == []


def test_vague_english_word_flagged() -> None:
    """영문 vague 단어(fast, simple, scalable)도 clarity finding."""
    skel = _skel(("기술 스택", "simple and scalable architecture."))
    findings = _findings_by_category(skel, "clarity")
    assert len(findings) >= 1


def test_hyphenated_library_name_not_flagged() -> None:
    """dogfood #19: 'fast-check' 라이브러리명의 substring 'fast' 는 clarity 오탐 금지."""
    skel = _skel(("테스트 전략", "property-based 테스트는 hypothesis 와 fast-check 로 작성한다."))
    findings = _findings_by_category(skel, "clarity")
    assert findings == []


def test_bare_english_vague_word_still_flagged() -> None:
    """단독 'fast' 는 여전히 clarity finding (TP 보존)."""
    skel = _skel(("성능 목표", "The API should be fast."))
    findings = _findings_by_category(skel, "clarity")
    assert len(findings) == 1


def test_task_decomposition_section_ignored_for_clarity() -> None:
    """'태스크 분해' 섹션의 '빠르게'는 무시(도구 산출물 섹션)."""
    skel = _skel(("태스크 분해", "빠르게 구현한다."))
    findings = _findings_by_category(skel, "clarity")
    assert findings == []


def test_implementation_notes_section_ignored_for_clarity() -> None:
    """'구현 노트' 섹션의 vague 단어는 무시."""
    skel = _skel(("구현 노트", "간단히 처리한다."))
    findings = _findings_by_category(skel, "clarity")
    assert findings == []


def test_code_block_vague_word_ignored() -> None:
    """코드블록(``` 펜스 안)의 vague 단어는 무시."""
    body = "```python\n# simple implementation\nsimple_flag = True\n```"
    skel = _skel(("HTTP API", body))
    findings = _findings_by_category(skel, "clarity")
    assert findings == []


def test_inline_backtick_vague_word_ignored() -> None:
    """인라인 백틱 내의 vague 단어는 무시."""
    body = "설정값 `simple=True` 사용."
    skel = _skel(("HTTP API", body))
    findings = _findings_by_category(skel, "clarity")
    assert findings == []


def test_vague_word_with_unit_on_same_line_no_finding() -> None:
    """같은 줄에 숫자+단위가 있으면 finding 없음."""
    body = "빠른 응답: p99 < 500ms"
    skel = _skel(("성능 목표", body))
    findings = _findings_by_category(skel, "clarity")
    assert findings == []


# ---------------------------------------------------------------------------
# Check 2: edge_case — I/O boundary sections missing failure paths
# ---------------------------------------------------------------------------


def test_io_section_without_failure_path_flagged() -> None:
    """I/O 경계 섹션('외부 연동')에 실패경로 문장 없으면 edge_case finding."""
    skel = _skel(("외부 연동", "카카오 로그인 API 호출. 응답 파싱 후 사용자 저장."))
    findings = _findings_by_category(skel, "edge_case")
    assert len(findings) == 1
    assert findings[0].severity == "warn"
    assert "외부 연동" in findings[0].section_id


def test_io_section_with_error_keyword_no_finding() -> None:
    """I/O 경계 섹션에 '에러 시 재시도' 있으면 edge_case finding 0."""
    body = "카카오 로그인 API 호출. 에러 시 재시도 3회."
    skel = _skel(("외부 연동", body))
    findings = _findings_by_category(skel, "edge_case")
    assert findings == []


def test_http_interface_section_without_failure_flagged() -> None:
    """'HTTP API' 제목 섹션도 I/O 경계로 인식."""
    skel = _skel(("HTTP API", "POST /api/users 사용자 생성. 200 OK 반환."))
    findings = _findings_by_category(skel, "edge_case")
    assert len(findings) == 1


def test_persistence_section_without_failure_flagged() -> None:
    """'저장소' 제목 섹션도 I/O 경계로 인식."""
    skel = _skel(("저장소 / 스키마", "PostgreSQL users 테이블. id, email, created_at."))
    findings = _findings_by_category(skel, "edge_case")
    assert len(findings) == 1


def test_auth_section_without_failure_flagged() -> None:
    """'인증' 포함 섹션도 I/O 경계로 인식."""
    skel = _skel(("인증 / 권한", "JWT 발급. access_token 30분."))
    findings = _findings_by_category(skel, "edge_case")
    assert len(findings) == 1


def test_non_io_section_without_failure_no_finding() -> None:
    """I/O 경계 아닌 섹션('프로젝트 개요')은 실패경로 없어도 finding 없음."""
    skel = _skel(("프로젝트 개요", "개인 태스크 관리 앱. 단일 사용자."))
    findings = _findings_by_category(skel, "edge_case")
    assert findings == []


def test_io_section_with_timeout_keyword_no_finding() -> None:
    """'timeout' 키워드가 있으면 edge_case finding 없음."""
    body = "외부 결제 API 호출. timeout 5s 설정."
    skel = _skel(("외부 연동", body))
    findings = _findings_by_category(skel, "edge_case")
    assert findings == []


def test_io_section_with_fallback_keyword_no_finding() -> None:
    """'fallback' 키워드가 있으면 edge_case finding 없음."""
    body = "S3 업로드. 실패시 fallback to local."
    skel = _skel(("저장소 / 스키마", body))
    findings = _findings_by_category(skel, "edge_case")
    assert findings == []


# ---------------------------------------------------------------------------
# Edge cases — robustness
# ---------------------------------------------------------------------------


def test_empty_string_returns_empty_list() -> None:
    """빈 문자열 -> [] (크래시 없음)."""
    assert check_skeleton_quality("") == []


def test_whitespace_only_returns_empty_list() -> None:
    """공백만 있는 텍스트 -> []."""
    assert check_skeleton_quality("   \n  \t  ") == []


def test_skeleton_with_no_sections_returns_empty_list() -> None:
    """## 섹션 없는 텍스트 -> []."""
    assert check_skeleton_quality("# 제목만 있는 문서\n내용 없음") == []


def test_finding_dataclass_fields() -> None:
    """ChecklistFinding 의 필수 필드 4개 모두 채워짐."""
    skel = _skel(("외부 연동", "카카오 로그인 API."))
    findings = check_skeleton_quality(skel)
    assert len(findings) >= 1
    f = findings[0]
    assert isinstance(f, ChecklistFinding)
    assert f.severity == "warn"
    assert f.category in ("clarity", "edge_case")
    assert f.section_id
    assert f.message


def test_multiple_sections_findings_aggregated() -> None:
    """여러 섹션에서 finding 이 aggregate 됨."""
    skel = _skel(
        ("HTTP API", "API는 빠르게 응답."),  # clarity + edge_case
        ("프로젝트 개요", "간단한 앱."),  # clarity only
    )
    all_findings = check_skeleton_quality(skel)
    categories = {f.category for f in all_findings}
    assert "clarity" in categories
    assert "edge_case" in categories


def test_section_id_is_title_not_number() -> None:
    """section_id 는 번호가 아닌 제목 문자열."""
    skel = "## 7. 외부 연동\n카카오 로그인."
    findings = check_skeleton_quality(skel)
    for f in findings:
        assert not f.section_id.startswith("7"), (
            f"section_id should be title, not '7': {f.section_id}"
        )
        assert "외부 연동" in f.section_id


# ---------------------------------------------------------------------------
# build_clarification_candidates (A3)
# ---------------------------------------------------------------------------

from src.orchestrator.skeleton_checklist import (  # noqa: E402
    build_clarification_candidates,
)


def _clarity_finding(section_id: str = "성능 목표") -> ChecklistFinding:
    return ChecklistFinding(
        severity="warn",
        category="clarity",
        section_id=section_id,
        message="'빠르게' 미정량 - 목표치(예: ms, 건수) 명시 권장",
    )


def _edge_finding(section_id: str = "외부 연동") -> ChecklistFinding:
    return ChecklistFinding(
        severity="warn",
        category="edge_case",
        section_id=section_id,
        message=f"'{section_id}' I/O 경계인데 실패/에러 경로 미기술",
    )


def test_clarity_finding_produces_clarity_candidate() -> None:
    """clarity finding → ClarificationCandidate with category='clarity', non-empty question/hint."""
    candidates = build_clarification_candidates([_clarity_finding()])
    assert len(candidates) == 1
    c = candidates[0]
    assert c.category == "clarity"
    assert c.section_id == "성능 목표"
    assert c.question  # non-empty
    assert c.hint  # non-empty


def test_edge_case_finding_produces_edge_case_candidate() -> None:
    """edge_case finding → ClarificationCandidate with category='edge_case', non-empty question/hint."""
    candidates = build_clarification_candidates([_edge_finding()])
    assert len(candidates) == 1
    c = candidates[0]
    assert c.category == "edge_case"
    assert c.section_id == "외부 연동"
    assert c.question
    assert c.hint


def test_empty_findings_returns_empty_list() -> None:
    """빈 findings → []."""
    assert build_clarification_candidates([]) == []


def test_max_n_cap_limits_output() -> None:
    """후보될 finding 7개 → max_n=5 → 5개."""
    findings = [_clarity_finding(f"섹션{i}") for i in range(7)]
    candidates = build_clarification_candidates(findings, max_n=5)
    assert len(candidates) == 5


def test_max_n_zero_returns_empty() -> None:
    """max_n=0 → []."""
    candidates = build_clarification_candidates([_clarity_finding()], max_n=0)
    assert candidates == []


def test_max_n_negative_returns_empty() -> None:
    """max_n <= 0 → []."""
    candidates = build_clarification_candidates([_clarity_finding()], max_n=-3)
    assert candidates == []


def test_duplicate_section_id_category_deduped() -> None:
    """동일 (section_id, category) 중복 finding → 후보 1개만."""
    dup = [_clarity_finding("중복섹션"), _clarity_finding("중복섹션")]
    candidates = build_clarification_candidates(dup)
    assert len(candidates) == 1


def test_order_preserved() -> None:
    """findings 순서 보존 — 첫 번째 finding 의 section_id 가 첫 번째 candidate."""
    findings = [_edge_finding("외부 연동"), _clarity_finding("성능 목표")]
    candidates = build_clarification_candidates(findings)
    assert candidates[0].section_id == "외부 연동"
    assert candidates[1].section_id == "성능 목표"


def test_candidate_dataclass_fields() -> None:
    """ClarificationCandidate 필드 4개 모두 채워짐."""
    from src.orchestrator.skeleton_checklist import ClarificationCandidate

    c = build_clarification_candidates([_clarity_finding()])[0]
    assert isinstance(c, ClarificationCandidate)
    assert c.section_id
    assert c.category in ("clarity", "edge_case")
    assert c.question
    assert c.hint
