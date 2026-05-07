---
id: mobile.navigation
name: 네비게이션
required_when: has.navigation
description: 네비게이션 그래프, deep linking, route guards, 백 버튼 처리. has.navigation atom 은 mobile profile 이 mobile.navigation 을 skeleton_sections.required 에 선언할 때 자동 활성.
---

## {{section_number}}. 네비게이션

### 네비게이션 그래프

화면 간 전이 구조 — 모든 진입점/전이 경로/중첩 관계를 명시.

| 레이어 | 종류 | 구현 | 비고 |
|------|-----|------|------|
| `<root>` | Stack / Tab / Drawer / Modal | `<Expo Router 파일 트리 / Navigator 위젯 / NavHost / NavigationStack>` | 최상위 네비게이터 |
| `<nested>` | (선택) | `<중첩 navigator 경로>` | 인증 영역 / 메인 영역 분리 시 |

### 화면 / 라우트 정의

각 라우트의 path, 이름, 파라미터, 가드, 진입점을 표로 정리:

| Route | Path / Name | 파라미터 | Guard | 진입 트리거 |
|-------|------------|---------|-------|------------|
| `<RouteName>` | `/<path>` | `<id: string?>` | `<auth / role / none>` | `<버튼/딥링크/푸시>` |

### Deep Linking

외부에서 앱 내 특정 화면으로 진입하는 URL 스킴.

| 항목 | 값 |
|------|-----|
| URL Scheme | `<myapp:// 또는 https://app.example.com>` |
| Universal / App Links | `<도메인 + 검증 파일 경로>` |
| 매핑 | `<myapp://item/:id → ItemDetail($id)>` |
| Cold start 처리 | `<초기 라우트가 deep link 인 경우 인증 검사 우선순위>` |

### Route Guards

| 가드 종류 | 적용 대상 | 동작 |
|---------|---------|------|
| 인증 필요 | `<라우트 목록>` | 미인증 시 `<로그인 화면>` 으로 redirect |
| 역할 기반 | `<라우트 목록>` | role mismatch 시 `<403 화면 / 토스트 + 뒤로>` |
| Onboarding 필요 | `<라우트 목록>` | 미완료 시 `<온보딩 흐름>` 으로 redirect |

### 백 버튼 / 제스처 (Android 하드웨어 백 + iOS swipe-back)

- 모달 / 다이얼로그 열림 → 백 버튼 = 닫기 (네비게이션 X)
- 폼 입력 중 dirty 상태 → 백 버튼 = "저장 안 함 확인" 모달
- 루트 탭 → 더블 백 버튼 = 앱 종료 (Android)
- iOS swipe-back 비활성화 화면: `<목록 — 인증 / 결제 마지막 단계 등>`

### 전이 애니메이션 / 모달 정책

- 기본 전이: `<slide / fade / 플랫폼 기본>`
- 모달: `<full screen / sheet / popup>` — 어떤 케이스에서 어떤 모달
- 탭 간 전이: `<state 보존 / reset>`

### 상태 보존

- 화면 백그라운드 진입 → state 저장 정책 (form 입력 / scroll position / 검색어)
- App restart 후 라우트 복원 정책 (last route / 항상 root)

> 작성 가이드:
> - **모든 화면이 deep linkable 인지 검토** — 제약이 있다면 그 사유 명시
> - **화면 ID 와 view.screens 섹션의 ID 일치** — 두 섹션은 동일한 화면 집합을 다른 관점에서 기술
> - **Guard 우선순위** — auth > role > onboarding 권장 (인증 없으면 다른 검사 무의미)
> - **Cold start vs warm start 분기 명시** — 푸시/딥링크가 cold start 시 race condition 흔함
> - **프레임워크별 권장**:
>   - RN+Expo: Expo Router (file-based) + `<Stack.Screen options={...}>`
>   - Flutter: `go_router` 또는 Navigator 2.0 + `redirect` callback
>   - Android: Navigation Compose + `composable("route") { ... }` + `argument`
>   - iOS: `NavigationStack` + `NavigationPath` + value-typed routes
