---
id: requirements
name: 기능 요구사항
required_when: scale.small_or_larger
description: MVP 기능, 추가 기능, 비즈니스 규칙
decision_points:
  - id: multi_user
    ask: "여러 사용자가 쓰나요? 데이터를 사용자끼리 공유/협업하나요, 각자 개인용인가요?"
    detect: [단일 사용자, 다중 사용자, 여러 사용자, 사용자별, 공유, 협업, 개인용, 1인]
    hint: "공유/협업이면 권한·소유 개념이 스키마·화면 전반에 퍼짐 — 지금 정해야 함"
  - id: unhappy_path
    ask: "핵심 기능이 실패하거나 데이터가 없을 때 사용자에게 무엇을 보여주나요?"
    detect: [실패, 오류, 에러, 없을 때, 비어, 빈 상태, empty, 권한 없]
    hint: "비전문가는 happy path 만 적음 — 빈/실패/권한거부 화면을 수용 기준에 포함"
---

<!-- placeholder/표기 컨벤션: 같은 디렉토리의 _README.md 참조 -->
<!-- HUMAN-LOCKED:requirements — 이 섹션은 사용자 인터뷰로만 채움. /ha-redesign 거쳐서만 변경 허용. -->

## {{section_number}}. 기능 요구사항

### AI 제안 후보 (사용자 선택 — /ha-design 단계에서 채워짐)
> AI 가 도메인 + 스택 + 페르소나 분석 후 3개 후보 제시. 사용자가 AskUserQuestion 으로 선택/수정.
> 사용자 미응답 시 `/ha-design --ai-draft` 옵트인 명시해야 진행 가능 (frontmatter `ai_drafted_sections` 에 기록).

<!-- AI-WRITABLE:requirements-candidates — /ha-design 이 후보 3 박는 영역. hook 통과. -->
| # | 후보 기능 | 사용자 가치 | 근거 (페르소나 / 시나리오) | 선택 |
|---|----------|-------------|---------------------------|:---:|
| 1 | `<AI 채움>` | `<AI 채움>` | `<페르소나 ID / 시나리오 N>` | ☐ |
| 2 | `<AI 채움>` | `<AI 채움>` | `<...>` | ☐ |
| 3 | `<AI 채움>` | `<AI 채움>` | `<...>` | ☐ |
<!-- /AI-WRITABLE -->

### 확정 기능 (사용자 선택 결과 — MVP Phase 1)

> 각 기능마다 **수용 기준(Given/When/Then) 2~3개를 사용자와 확정** — "작동한다" 가 아니라
> "의도대로 작동한다" 의 판정 기준. AI 초안 → 사용자 수정/승인 (/ha-design 인터뷰 Step D).
> 이 기준이 곧 QA/스모크의 체크리스트가 된다.

- [ ] <기능 1>
  - 수용 기준:
    - Given <전제 상태> / When <사용자 행동> / Then <기대 결과 — 화면에서 보이는 것까지>
    - Given <...> / When <...> / Then <...>
- [ ] <기능 2>
  - 수용 기준:
    - Given <...> / When <...> / Then <...>

### 추가 기능 (Phase 2+)
- [ ] `<기능>`

### 비즈니스 규칙
- <규칙 1 — 예: "완료 기록은 오늘 날짜만 가능">
- <규칙 2>

### 명시적 Out-of-scope
- <이 버전에서 하지 않는 것 — 혼선 방지>

<!-- /HUMAN-LOCKED:requirements -->

> 작성 가이드:
> - 각 기능은 사용자 관점 동사 문장으로. "사용자가 ~할 수 있다"
> - MVP는 5개 이하로 엄격 제한
> - 비즈니스 규칙은 나중에 엣지케이스 질문의 근거가 됨 — 빠짐없이
> - **HITL 규칙**: 이 섹션은 LOCKED. `/ha-design` 인터뷰 또는 `/ha-redesign` 거치지 않고 직접 편집 금지.
