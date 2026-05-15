---
id: user_journey
name: 사용자 시나리오 (User Journey)
required_when: has.users and lifecycle in [mvp, ga]
description: 페르소나 + 핵심 시나리오 + 화면 전이. view.flow 가 컴포넌트 상태라면 user_journey 는 비즈니스 가치 흐름.
---

<!-- placeholder 컨벤션: HITL <AI> / <Primary> 등은 uppercase/Korean 으로 박음 (assembler _ANGLE_PLACEHOLDER_RE 는 lowercase snake_case 만 잡음). -->
<!-- HUMAN-LOCKED:user_journey — 이 섹션은 사용자 인터뷰로만 채움. /ha-redesign 거쳐서만 변경 허용. -->

## {{section_number}}. 사용자 시나리오 (User Journey)

### AI 제안 페르소나 후보 (사용자 선택 — /ha-design 단계)
> AI 가 도메인 + 사용자 설명 분석 후 3-5개 *구체적* 페르소나 후보 제시.
> 구체성 기준: "30대 직장인" 금지 → "주 2회 야근하는 30대 IT 기획자, 독서 시간 부족" 처럼.
> 사용자가 선택/수정/추가. 미응답 시 `--ai-draft` 옵트인 필수.

<!-- AI-WRITABLE:user-journey-persona-candidates — /ha-design 이 페르소나 후보 5 박는 영역. hook 통과. -->
| # | 후보 페르소나 (한 줄 구체) | 역할 | 동기 | 좌절 | 선택 |
|---|---------------------------|------|------|------|:---:|
| 1 | `<AI: 구체적 한 줄 — 직업/상황/현재 행동>` | `<AI>` | `<AI>` | `<AI>` | ☐ |
| 2 | `<AI>` | `<AI>` | `<AI>` | `<AI>` | ☐ |
| 3 | `<AI>` | `<AI>` | `<AI>` | `<AI>` | ☐ |
| 4 | `<AI>` | `<AI>` | `<AI>` | `<AI>` | ☐ |
| 5 | `<AI>` | `<AI>` | `<AI>` | `<AI>` | ☐ |
<!-- /AI-WRITABLE -->

### 확정 페르소나 (사용자 선택 결과)

| 페르소나 | 역할 | 동기 (왜 우리 서비스를 쓰는가) | 좌절 (현재 어떻게 풀고 있나) |
|---------|------|-------------------------------|------------------------------|
| `<Primary>` | <역할 / 직군> | <달성하려는 가치> | <기존 방식의 한계> |
| `<Secondary>` | <역할> | <부수 가치> | <한계> |

페르소나는 **구체적**으로 — "30대 직장인" 보다 "주 2회 야근하는 30대 IT 기획자, 독서 시간 부족" 처럼.

> 시나리오는 *확정 페르소나* 기반. 페르소나 미확정 시 시나리오 작성 금지.

### 핵심 시나리오 (Happy Path)

#### 시나리오 1: `<예: 신규 사용자 첫 결제>`

```mermaid
sequenceDiagram
    actor User
    participant Web
    participant API
    participant Auth
    participant Stripe
    participant DB

    User->>Web: 가입 페이지 접속
    Web->>API: POST /signup
    API->>Auth: 검증 + 토큰 발급
    Auth-->>API: token
    API->>DB: INSERT user
    API-->>Web: 200 + token
    Web-->>User: 환영 페이지

    User->>Web: 플랜 선택
    Web->>API: POST /subscribe
    API->>Stripe: createCheckoutSession
    Stripe-->>API: session_url
    API-->>Web: 결제 페이지 리다이렉트
    User->>Stripe: 카드 정보 입력
    Stripe-->>Web: success callback
    Web->>API: POST /confirm-subscribe
    API->>DB: INSERT subscription
    API-->>Web: 200
    Web-->>User: 구독 완료
```

**가치 도착점**: <이 시나리오 끝에서 사용자가 얻는 것 — 구독 활성화 / 첫 기능 사용 가능>

**측정 지표** (analytics — Phase 3):
- 시작 → 완료 conversion: <목표 N%>
- 단계별 drop-off: <어디서 가장 많이 이탈하는가>

#### 시나리오 2: `<예: 일상 사용 — 핵심 액션>`

(같은 형식으로 작성)

#### 시나리오 3: `<예: 핵심 가치 재방문>`

(같은 형식으로)

### 화면 전이 (State Diagram)

```mermaid
stateDiagram-v2
    [*] --> Landing
    Landing --> SignUp: "가입" 클릭
    SignUp --> EmailVerify
    EmailVerify --> Onboarding
    Onboarding --> Dashboard
    Dashboard --> CoreFeature1
    Dashboard --> CoreFeature2
    CoreFeature1 --> Dashboard
    Dashboard --> Settings
    Settings --> Dashboard
    Dashboard --> [*]: 로그아웃
```

### Edge Case / Unhappy Path

| 시나리오 | 발생 빈도 | 처리 | UX |
|---------|----------|------|-----|
| 결제 카드 거부 | 자주 | 다른 카드 안내 | 명확한 에러 + 재시도 버튼 |
| 외부 의존 다운 (Stripe / OAuth) | 드물지만 치명 | `external_deps` 폴백 | 상태 페이지 링크 + 재시도 안내 |
| 권한 부족 | 가끔 | `authorization_matrix` 의 거부 응답 | 어떤 권한이 필요한지 안내 |
| 데이터 미존재 (404) | 자주 | 빈 상태 화면 | "없음" + 다음 액션 제안 |
| 네트워크 오류 | 자주 | retry / offline 안내 | optimistic update + rollback 또는 명확한 실패 |

### 접근성 (a11y) 핵심 흐름 (Phase 3 의 a11y 와 결합)

- 키보드만으로 핵심 시나리오 1 완수 가능 (Tab / Enter / Esc)
- 스크린리더로 핵심 시나리오 1 완수 가능 (ARIA labels + landmark)
- 색상만으로 정보 전달 금지 (텍스트 + 아이콘 병행)

<!-- /HUMAN-LOCKED:user_journey -->

> 작성 가이드:
> - 핵심 시나리오는 3-5개로 — 모든 기능을 시나리오화하지 말 것 (가치 흐름 중심)
> - Mermaid sequenceDiagram 은 외부 호출 흐름 / stateDiagram 은 화면 / flowchart 는 의사결정
> - Happy path 만 적지 말 것 — edge case 가 사용자 경험을 결정
> - `view.screens` 가 화면별 명세라면 user_journey 는 그 화면들을 잇는 시퀀스
> - 측정 지표 정의는 출시 전 필수 — 안 정하면 retention 도 측정 못 함
> - **HITL 규칙**: 페르소나 / 시나리오 / 화면 전이 셋 다 LOCKED. `/ha-design` 또는 `/ha-redesign` 외 직접 편집 금지.
