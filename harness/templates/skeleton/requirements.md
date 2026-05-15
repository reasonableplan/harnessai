---
id: requirements
name: 기능 요구사항
required_when: scale.small_or_larger
description: MVP 기능, 추가 기능, 비즈니스 규칙
---

<!-- placeholder 컨벤션: HITL <AI 채움> / <기능 1> 등은 uppercase/Korean 으로 박음 (assembler _ANGLE_PLACEHOLDER_RE 는 lowercase snake_case 만 잡음). -->
<!-- HUMAN-LOCKED:requirements — 이 섹션은 사용자 인터뷰로만 채움. /ha-redesign 거쳐서만 변경 허용. -->

## {{section_number}}. 기능 요구사항

### AI 제안 후보 (사용자 선택 — /ha-design 단계에서 채워짐)
> AI 가 도메인 + 스택 + 페르소나 분석 후 5개 후보 제시. 사용자가 AskUserQuestion 으로 선택/수정.
> 사용자 미응답 시 `/ha-design --ai-draft` 옵트인 명시해야 진행 가능 (frontmatter `ai_drafted_sections` 에 기록).

| # | 후보 기능 | 사용자 가치 | 근거 (페르소나 / 시나리오) | 선택 |
|---|----------|-------------|---------------------------|:---:|
| 1 | `<AI 채움>` | `<AI 채움>` | `<페르소나 ID / 시나리오 N>` | ☐ |
| 2 | `<AI 채움>` | `<AI 채움>` | `<...>` | ☐ |
| 3 | `<AI 채움>` | `<AI 채움>` | `<...>` | ☐ |
| 4 | `<AI 채움>` | `<AI 채움>` | `<...>` | ☐ |
| 5 | `<AI 채움>` | `<AI 채움>` | `<...>` | ☐ |

### 확정 기능 (사용자 선택 결과 — MVP Phase 1)
- [ ] <기능 1>
- [ ] <기능 2>

### 추가 기능 (Phase 2+)
- [ ] <기능>

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
