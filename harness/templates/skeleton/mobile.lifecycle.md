---
id: mobile.lifecycle
name: 라이프사이클 / 권한
required_when: has.lifecycle
description: 권한 정책 + 요청 시점, 백그라운드 작업, 앱 상태 전환 (foreground/background/terminated), 푸시 알림 라이프사이클
---

## {{section_number}}. 라이프사이클 / 권한

### 권한

| 권한 | 사용처 | 요청 시점 | 거부 시 동작 |
|------|--------|---------|-------------|
| `<camera>` | `<프로필 사진 등록>` | 사용자가 카메라 버튼 누른 직후 | 갤러리만 사용 가능 안내 |
| `<location.fineLocation>` | `<주변 매장 검색>` | "내 위치" 버튼 누른 직후 | 수동 주소 입력 fallback |
| `<notifications>` | `<푸시 알림>` | 온보딩 마지막 단계 | 인앱 알림만 작동 |
| `<storage / photo_library>` | `<이미지 업로드>` | 갤러리 진입 직전 | 카메라 직접 촬영만 |

> **권한은 사용 시점에 요청** — 앱 시작 시 일괄 요청 금지 (UX 안티패턴).
> **거부 후 재요청은 1회만** — OS 가 차단하면 시스템 설정 deeplink 안내.

### 백그라운드 작업

| 작업 | 종류 | 트리거 | 정책 |
|------|------|-------|------|
| `<오프라인 큐 동기화>` | Periodic / Opportunistic | 네트워크 복귀 | 배터리 절감 모드 시 미실행 |
| `<위치 기반 알림>` | Geofence | 영역 진입/이탈 | `<정책>` |

### 앱 상태 전환

| 전환 | 저장해야 할 상태 | 복원 시점 | 복원 방식 |
|------|----------------|---------|---------|
| foreground → background | `<form 입력 / scroll position / 검색어>` | 다시 foreground 진입 시 | 자동 (state hydrate) |
| background → terminated (메모리 회수) | `<현재 라우트 / 인증 상태>` | cold start 시 | last-route 복원 + 인증 재검사 |
| terminated → foreground (cold start) | — | 시작 시 | initial route 결정 (deep link 우선) |

### 푸시 알림 라이프사이클 (선택)

| 단계 | 동작 |
|------|------|
| 토큰 발급 | `<FCM / APNS / Expo Push>` 토큰 → 서버 등록 |
| 토큰 갱신 | OS 가 갱신 신호 → 서버에 업데이트 |
| 알림 수신 (foreground) | 인앱 토스트 또는 무시 |
| 알림 수신 (background) | OS 알림 표시, 탭 시 deep link |
| 알림 탭 (cold start) | initial route 가 deep link 로 결정 |
| 토큰 폐기 (로그아웃 / 앱 삭제) | 서버에서 unregister |

> 작성 가이드:
> - **권한 요청은 카메라/마이크/위치/알림 4가지가 가장 흔함** — 각각의 trigger 와 fallback 명시
> - **앱 상태 전환 시 form dirty 보존 필수** — UX 안 그러면 사용자 분노 (LESSON)
> - **푸시 토큰은 인증 상태와 묶어 서버에 저장** — 로그아웃 시 함께 unregister
> - **프레임워크별 권장**:
>   - RN+Expo: `expo-camera`, `expo-location`, `expo-notifications`, `AppState` API
>   - Flutter: `permission_handler`, `geolocator`, `firebase_messaging`, `WidgetsBindingObserver`
>   - Android: `ActivityCompat.requestPermissions`, WorkManager, FCM
>   - iOS: `AVCaptureDevice.requestAccess`, BGTaskScheduler, APNS / UNUserNotificationCenter
