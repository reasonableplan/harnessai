"""Cross-section consistency checks for skeleton.md / tasks.md.

Used by /ha-redesign (after applied) and (eventually) /ha-review to surface drift
where re-derivation or task additions break the implicit reference graph between
sections — the structural defect that the v0.7.0 mutation-propagation track was
created to address.

Findings are advisory (severity="info"|"warn"|"critical") — never blocking. The
point is to give the next agent or reviewer a concrete checklist, not to gate
progress with heuristic rules. A blocker would need stronger guarantees than regex
can provide.

severity levels:
    "info":     informational — likely benign drift, surface for review.
    "warn":     probable issue — re-derivation may have missed a section.
    "critical": principle/constraint violation — NFR or architectural rule broken.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.orchestrator.context import split_sections_by_id
from src.orchestrator.task_id import SKELETON_REF_LINE_RE, SPEC_BLOCK_RE, TASK_ROW_RE

# JSX component token: <ComponentName />, <ComponentName>, <ComponentName prop=…>.
# Captures the PascalCase name (length ≥4 enforced at call site).
# Matches <Header />, <DomainList>, <HomeContainer />, <Button> etc.
# Used for *definition* extraction from view.components — prose text such as
# "JetBrains", "PascalCase", "UnsupportedInfo" is intentionally excluded.
_COMPONENT_TOKEN_RE = re.compile(r"<([A-Z][A-Za-z0-9]*)\b[^>]*/?>")

# CamelCase token of length ≥4 — used for *reference* extraction from
# state.flow / core.logic / task descriptions, which are prose/pseudocode and
# may name components without angle brackets (e.g. "GameScreen 상태 전이").
_CAMELCASE_RE = re.compile(r"\b([A-Z][a-z]+(?:[A-Z][a-z]*)+)\b")

# Section reference inside text: "§13" or "§ 13".
_SECTION_REF_RE = re.compile(r"§\s*\d+")

# Component-bearing sections, keyed by fragment ID — NOT heading number.
# Heading numbers are assigned dynamically at assembly time (skeleton_assembler
# enumerates the active fragment set), so which section lands at §13 varies per
# project's 6-axis activation. view.components holds the canonical component
# tree; state.flow and core.logic are where each component must be wired in.
_COMPONENT_DEFINITION_IDS = ("view.components",)
_COMPONENT_REFERENCE_IDS = ("state.flow", "core.logic")


@dataclass(frozen=True)
class ConsistencyFinding:
    """Single consistency check result.

    severity:
        - "info":     informational — likely benign drift, surface for review.
        - "warn":     probable issue — re-derivation may have missed a section.
        - "critical": principle/constraint violation — NFR or architectural rule broken.
    """

    severity: str
    pattern: str  # short label: "isolated-component" | "task-no-reference" | "offline-constraint-violation"
    message: str
    target: str  # the identifier (component name, T-XXX, etc.) the finding is about


def _defined_components(body: str) -> set[str]:
    """Extract JSX component names (length ≥ 4) from a *definition* section body.

    Only angle-bracket JSX tokens (<Name />, <Name>, <Name prop=…>) count.
    Bare CamelCase prose (JetBrains, PascalCase, UnsupportedInfo) is excluded
    to prevent false positives from design-guide text in view.components.
    """
    return {m.group(1) for m in _COMPONENT_TOKEN_RE.finditer(body) if len(m.group(1)) >= 4}


def _referenced_components(body: str) -> set[str]:
    """Extract component name candidates (length ≥ 4) from a *reference* section body.

    Accepts both JSX tokens (<Name />) and bare CamelCase identifiers because
    state.flow, core.logic, and task descriptions are prose/pseudocode that
    typically name components without angle brackets (e.g. "GameScreen 상태 전이").
    """
    jsx = {m.group(1) for m in _COMPONENT_TOKEN_RE.finditer(body) if len(m.group(1)) >= 4}
    camel = {m.group(1) for m in _CAMELCASE_RE.finditer(body) if len(m.group(1)) >= 4}
    return jsx | camel


def check_isolated_components(skel_text: str) -> list[ConsistencyFinding]:
    """Components defined in view.components that never appear in state.flow/core.logic.

    A defined-but-unreferenced component is the canonical drift symptom:
    re-derivation added a UI piece without wiring its trigger or behavior.

    Definition extraction uses JSX tokens only (<Name />) to avoid false
    positives from prose text (font names, type names, naming-convention
    explanations) that happens to be PascalCase. Reference extraction accepts
    both JSX tokens and bare CamelCase because state.flow and core.logic are
    prose/pseudocode that names components without angle brackets.
    """
    sections = split_sections_by_id(skel_text)
    defined: set[str] = set()
    for sid in _COMPONENT_DEFINITION_IDS:
        if sid in sections:
            defined |= _defined_components(sections[sid])

    referenced: set[str] = set()
    for sid in _COMPONENT_REFERENCE_IDS:
        if sid in sections:
            referenced |= _referenced_components(sections[sid])

    findings: list[ConsistencyFinding] = []
    for name in sorted(defined - referenced):
        findings.append(
            ConsistencyFinding(
                severity="info",
                pattern="isolated-component",
                target=name,
                message=(
                    f"Component '{name}' defined in '{_COMPONENT_DEFINITION_IDS[0]}' "
                    f"but not referenced in {'/'.join(_COMPONENT_REFERENCE_IDS)} — "
                    "possible state-machine or pseudo-code wiring miss."
                ),
            )
        )
    return findings


def check_task_skeleton_references(tasks_text: str, skel_text: str) -> list[ConsistencyFinding]:
    """Tasks with no §N reference, no view.components-component reference, and no spec-block skeleton ref.

    A task is considered anchored when ANY of the following is true:
    1. Phase-table description contains a §N section reference.
    2. Phase-table description mentions a known view.components component name.
    3. The task's spec block (### T-NNN …) contains a "**skeleton 참조**" line.

    Only when all three are absent is a "task-no-reference" warn emitted.
    """
    sections = split_sections_by_id(skel_text)
    known_components: set[str] = set()
    for sid in _COMPONENT_DEFINITION_IDS:
        if sid in sections:
            known_components |= _defined_components(sections[sid])

    # Build task_id → spec-block-body mapping once for O(n) lookup.
    spec_block_bodies: dict[str, str] = {
        m.group(1): m.group(0) for m in SPEC_BLOCK_RE.finditer(tasks_text)
    }

    findings: list[ConsistencyFinding] = []
    for m in TASK_ROW_RE.finditer(tasks_text):
        task_id = m.group(1)
        description = m.group(4)

        has_section_ref = bool(_SECTION_REF_RE.search(description))
        # Task descriptions are prose — use _referenced_components (CamelCase + JSX).
        mentioned_components = _referenced_components(description)
        has_component_ref = bool(mentioned_components & known_components)

        # Check spec block for skeleton 참조 line (third anchor path).
        spec_body = spec_block_bodies.get(task_id, "")
        has_spec_block_ref = bool(spec_body and SKELETON_REF_LINE_RE.search(spec_body))

        if not has_section_ref and not has_component_ref and not has_spec_block_ref:
            findings.append(
                ConsistencyFinding(
                    severity="warn",
                    pattern="task-no-reference",
                    target=task_id,
                    message=(
                        f"Task '{task_id}' description has no §N reference and no "
                        "known view.components component name — implementer may lack anchor."
                    ),
                )
            )
    return findings


# ── 설계-시점 cross-section 검증 (design backlog A) ──────────────────
# ha-design commit / ha-redesign applied 에서 advisory 로 보고. 섹션 간 참조가
# 어긋난 채 freeze 되는 것을 표면화한다 — §4 충돌 검토(LLM 절차)의 기계 보강.

_ERROR_CODE_RE = re.compile(r"\b([A-Z][A-Z0-9]*_\d{3})\b")
_ENDPOINT_TOKEN_RE = re.compile(r"`(GET|POST|PUT|PATCH|DELETE)\s+(/[^\s`]+)`")


def check_error_ux_codes_defined(skel_text: str) -> list[ConsistencyFinding]:
    """error_ux 매핑이 참조하는 에러 코드가 errors 섹션에 정의돼 있는가."""
    sections = split_sections_by_id(skel_text)
    ux_body = sections.get("error_ux")
    errors_body = sections.get("errors")
    if ux_body is None or errors_body is None:
        return []
    defined = set(_ERROR_CODE_RE.findall(errors_body))
    findings: list[ConsistencyFinding] = []
    for code in sorted(set(_ERROR_CODE_RE.findall(ux_body)) - defined):
        findings.append(
            ConsistencyFinding(
                severity="warn",
                pattern="error-code-undefined",
                target=code,
                message=(
                    f"error_ux 가 '{code}' 를 매핑하지만 errors 섹션에 정의 없음 — "
                    "코더가 추정 구현하게 됨."
                ),
            )
        )
    return findings


def check_screen_api_references(skel_text: str) -> list[ConsistencyFinding]:
    """view.screens 가 참조하는 엔드포인트가 interface.http 에 선언돼 있는가."""
    sections = split_sections_by_id(skel_text)
    screens_body = sections.get("view.screens")
    http_body = sections.get("interface.http")
    if screens_body is None or http_body is None:
        return []
    declared = set(_ENDPOINT_TOKEN_RE.findall(http_body))
    findings: list[ConsistencyFinding] = []
    used = set(_ENDPOINT_TOKEN_RE.findall(screens_body))
    for method, path in sorted(used - declared):
        findings.append(
            ConsistencyFinding(
                severity="warn",
                pattern="screen-api-missing",
                target=f"{method} {path}",
                message=(
                    f"화면이 '{method} {path}' 를 참조하지만 interface.http 에 "
                    "선언 없음 — 계약 밖 API."
                ),
            )
        )
    return findings


def check_screen_auth_column(skel_text: str) -> list[ConsistencyFinding]:
    """auth 활성 프로젝트에서 화면 표의 Auth 칸이 비어 있지 않은가."""
    sections = split_sections_by_id(skel_text)
    screens_body = sections.get("view.screens")
    if screens_body is None or "auth" not in sections:
        return []
    findings: list[ConsistencyFinding] = []
    auth_idx: int | None = None
    for line in screens_body.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            auth_idx = None  # 표 종료 — 다음 표를 위해 리셋
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if auth_idx is None:
            if "Auth" in cells and any("경로" in c for c in cells):
                auth_idx = cells.index("Auth")
            continue
        if set("".join(cells)) <= set("-: "):  # separator row
            continue
        if len(cells) > auth_idx and not cells[auth_idx]:
            findings.append(
                ConsistencyFinding(
                    severity="warn",
                    pattern="screen-auth-unspecified",
                    target=cells[0].strip("`"),
                    message=(
                        f"화면 '{cells[0]}' 의 Auth 칸이 비어 있음 — "
                        "보호 여부 미정인 채 freeze 되는 화면."
                    ),
                )
            )
    return findings


# ── 오프라인/네트워크 제약 위반 검사 (NFR #10) ──────────────────────
# skeleton 에 오프라인 제약이 선언됐음에도 비-루프백 외부 URL 이나
# 다운로드/원격 fetch 동사가 등장하면 critical finding 을 발행한다.
# 제약이 없는 프로젝트에는 적용하지 않는다(조건부 검사).

# 오프라인/네트워크 금지 제약 선언을 탐지하는 정규식.
_OFFLINE_CONSTRAINT_RE = re.compile(
    r"오프라인|외부\s*(?:인터넷\s*)?호출\s*없|네트워크\s*(?:호출\s*)?없"
    r"|로컬\s*(?:루프백|loopback)\s*만|no\s*network|offline\s*only"
    r"|air-?gapped|key-?free|시크릿\s*없",
    re.IGNORECASE,
)

# 루프백/플레이스홀더 호스트 — 이 패턴은 비-위반으로 제외한다.
_LOOPBACK_HOST_RE = re.compile(
    r"^(?:localhost|127\.0\.0\.1|0\.0\.0\.0|::1|example\.|<|\{)",
    re.IGNORECASE,
)

# 비-루프백 외부 URL: http(s):// 뒤 호스트 추출.
_EXTERNAL_URL_RE = re.compile(r"https?://([^\s/\"'`>]+)")

# 다운로드/원격 fetch 동사 — URL 없이도 선언 위반.
_DOWNLOAD_VERB_RE = re.compile(
    r"다운로드|download|원격\s*(?:에서\s*)?(?:가져|fetch|받)"
    r"|fetch(?:es|ing)?\s+from\s+https?"
    r"|CDN|S3|업로드|upload",
    re.IGNORECASE,
)

# 코드펜스 내용 제거 — 예시 URL FP 방지.
_CODEFENCE_RE = re.compile(r"```.*?```", re.DOTALL)
# 인라인 백틱 제거.
_INLINE_TICK_RE = re.compile(r"`[^`\n]+`")


def check_offline_network_violation(skel_text: str) -> list[ConsistencyFinding]:
    """오프라인/네트워크 제약이 선언된 skeleton 에서 모순 마커를 탐지한다.

    1. skeleton 전체 텍스트에서 오프라인 제약 선언을 탐지한다.
    2. 제약이 없으면 즉시 [] 반환 — 이 검사는 제약을 선언한 프로젝트에만 적용.
    3. 제약이 있으면 코드펜스·인라인 백틱을 제거한 텍스트에서 모순 마커를 스캔:
       - 비-루프백 외부 URL (루프백/플레이스홀더 제외)
       - 다운로드/원격 fetch 동사
    4. 매칭된 마커마다 critical finding 을 생성하고, 동일 target 은 dedup 한다.
    """
    if not skel_text:
        return []

    if not _OFFLINE_CONSTRAINT_RE.search(skel_text):
        return []

    # 코드펜스 및 인라인 백틱 제거 — 예시 코드 내 URL/동사 FP 방지.
    stripped = _CODEFENCE_RE.sub("", skel_text)
    stripped = _INLINE_TICK_RE.sub("", stripped)

    # 섹션 ID 맵 — target 메시지에 섹션 정보 포함용.
    sections = split_sections_by_id(skel_text)
    # 섹션별 줄 범위를 미리 계산하지 않고, 섹션 ID 목록만 참조한다.
    # (split_sections_by_id 는 섹션 본문만 반환하므로 줄 번호 대신 섹션 ID 활용)
    section_ids = list(sections.keys())

    _VIOLATION_MSG = (
        "오프라인/네트워크 제약 선언됨에도 외부 네트워크 마커 발견 — "
        "NFR(#10) 위반 가능, 검증 필요"
    )

    seen: set[str] = set()
    findings: list[ConsistencyFinding] = []

    def _add(marker: str) -> None:
        truncated = marker[:60]
        if truncated in seen:
            return
        seen.add(truncated)
        # 어느 섹션인지 확인 — 섹션 본문에 마커가 포함된 첫 섹션.
        section_hint = ""
        for sid in section_ids:
            if marker in sections.get(sid, ""):
                section_hint = f" [섹션: {sid}]"
                break
        findings.append(
            ConsistencyFinding(
                severity="critical",
                pattern="offline-constraint-violation",
                target=truncated,
                message=_VIOLATION_MSG + section_hint,
            )
        )

    # 비-루프백 외부 URL 스캔.
    for m in _EXTERNAL_URL_RE.finditer(stripped):
        host = m.group(1).split("/")[0].split(":")[0]
        if not _LOOPBACK_HOST_RE.match(host):
            _add(m.group(0))

    # 다운로드/원격 fetch 동사 스캔.
    for m in _DOWNLOAD_VERB_RE.finditer(stripped):
        _add(m.group(0))

    return findings


def run_all_checks(
    *, skeleton_text: str, tasks_text: str | None = None
) -> list[ConsistencyFinding]:
    """Run every cross-section consistency check and return aggregated findings.

    tasks_text is optional — task-level checks are skipped if absent (e.g. when
    the project has not reached the "planned" pipeline state yet).
    """
    findings: list[ConsistencyFinding] = []
    findings.extend(check_isolated_components(skeleton_text))
    findings.extend(check_error_ux_codes_defined(skeleton_text))
    findings.extend(check_screen_api_references(skeleton_text))
    findings.extend(check_screen_auth_column(skeleton_text))
    findings.extend(check_offline_network_violation(skeleton_text))
    # Distinguish "no tasks file" (None) from "empty tasks file" (""). The empty
    # case yields zero findings naturally, but running the check preserves the
    # type contract that callers expect.
    if tasks_text is not None:
        findings.extend(check_task_skeleton_references(tasks_text, skeleton_text))
    return findings
