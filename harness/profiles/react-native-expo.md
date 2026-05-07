---
id: react-native-expo
name: React Native + Expo
status: confirmed
extends: _base
version: 1
maintainer: harness-core

paths: [".", "apps/mobile/", "mobile/"]
detect:
  files: [package.json]
  contains_any:
    package.json: ['"expo"', '"react-native"']
  not_contains:
    package.json: ['"react-native-windows"', '"electron"']

components:
  - id: view.screens
    required: true
    skeleton_section: view.screens
    description: Expo Router file-based routing — app/<route>.tsx 1:1 매핑
  - id: view.components
    required: true
    skeleton_section: view.components
    description: src/shared/components/ + src/containers/<domain>/components/
  - id: state.flow
    required: true
    skeleton_section: state.flow
    description: Zustand 도메인별 store — store action 에서 axios 호출 (web 과 일관)
  - id: mobile.navigation
    required: true
    skeleton_section: mobile.navigation
    description: Expo Router 네비게이션 그래프 + deep linking + route guards
  - id: mobile.build_config
    required: true
    skeleton_section: mobile.build_config
    description: app.config.ts profiles + EAS Build + 시그니처 / 환경변수
  - id: mobile.lifecycle
    required: true
    skeleton_section: mobile.lifecycle
    description: 권한 / 백그라운드 / 앱 상태 / 푸시 알림 라이프사이클
  - id: persistence
    required: false
    skeleton_section: persistence
    description: AsyncStorage / expo-sqlite / expo-secure-store (선택, has.storage 시 활성)
  - id: interface.http
    required: false
    skeleton_section: interface.http
    description: axios + interceptor (paired 모드 — backend 가 함께 있을 때만)
  - id: core.logic
    required: true
    skeleton_section: core.logic
    description: 유틸 (formatters, validators)

skeleton_sections:
  required:
    - overview
    - stack
    - view.screens
    - view.components
    - state.flow
    - mobile.navigation
    - mobile.build_config
    - mobile.lifecycle
    - core.logic
    - tasks
    - notes
  optional:
    - requirements
    - configuration
    - errors
    - auth
    - persistence
    - interface.http
  order:
    - overview
    - requirements
    - stack
    - configuration
    - errors
    - auth
    - mobile.build_config
    - mobile.lifecycle
    - persistence
    - interface.http
    - mobile.navigation
    - view.screens
    - view.components
    - state.flow
    - core.logic
    - tasks
    - notes

toolchain:
  install: "bun install"
  test: "bun test"
  lint: "bun run lint"
  type: "bunx tsc --noEmit"
  format: "bun run format"

whitelist:
  runtime:
    - expo
    - expo-router
    - expo-constants
    - expo-status-bar
    - expo-sqlite
    - expo-secure-store
    - expo-localization
    - expo-image
    - expo-camera
    - expo-location
    - expo-notifications
    - expo-linking
    - expo-splash-screen
    - react
    - react-native
    - zustand
    - axios
    - react-hook-form
    - zod
    - nativewind
    - tailwindcss
    - react-native-mmkv
    - react-native-reanimated
    - react-native-gesture-handler
    - react-native-safe-area-context
    - react-native-screens
    - "@react-native-async-storage/async-storage"
  dev:
    - typescript
    - eslint
    - eslint-config-expo
    - prettier
    - jest
    - jest-expo
    - "@testing-library/react-native"
    - "@testing-library/jest-native"
    - expo-doctor
    - "@types/react"
    - "@types/jest"
  prefix_allowed:
    - "@expo/"
    - "@react-native/"
    - "@react-native-community/"

file_structure: |
  mobile/                    # 또는 apps/mobile/
    package.json
    app.json
    app.config.ts            # SDK 변형 + extra (env 주입)
    eas.json                 # EAS Build profiles (development/preview/production)
    tsconfig.json
    bun.lockb
    .env.example
    babel.config.js
    metro.config.js
    app/                     # Expo Router file-based routing
      _layout.tsx            # Root layout (Providers / SplashScreen)
      (auth)/                # 인증 영역 group
        _layout.tsx          # auth 가드 layout
        login.tsx
        signup.tsx
      (main)/                # 메인 영역 group
        _layout.tsx          # Tab navigator
        index.tsx            # 홈 탭
        profile.tsx
      [+not-found].tsx
    src/
      shared/
        components/          # Button / Input / Modal / Toast (RN 컴포넌트)
        store/
          auth.store.ts      # Zustand — 여러 화면 공유
        api/
          client.ts          # axios + interceptor (paired 모드만)
        types/
        hooks/               # useColorScheme / useResponsive 등
        theme/               # NativeWind 테마 (선택)
      containers/
        <domain>/
          <Domain>Container.tsx
          components/
          store/
            <domain>.store.ts
          index.style.ts     # NativeWind className 또는 StyleSheet
      core/
        validators/
        formatters/
    __tests__/
    assets/
      images/
      fonts/

gstack_mode: manual
gstack_recommended:
  before_design: [office-hours]
  after_design: [plan-design-review]
  after_build: [design-review, review]
  before_ship: [qa]
  after_ship: [retro]

lessons_applied:
  - LESSON-006   # type=number CJK IME — RN 은 keyboardType="number-pad" 로 처리
  - LESSON-STYLE-001   # NativeWind className 또는 StyleSheet 분리 — 인라인 2개 이상 금지
---

# React Native + Expo Frontend Profile

## 핵심 원칙

- **Expo Managed Workflow 우선** — bare workflow 금지 (M5+ 검토)
- **Expo Router (file-based)** 사용 — react-navigation 직접 사용 금지
- **상태 관리는 Zustand 단일화** — React Query / SWR / TanStack Query 금지 (web 과 일관)
- **NativeWind className 또는 StyleSheet 분리** — 인라인 스타일 2개 이상 금지 (LESSON-STYLE-001)
- **TypeScript strict** — `any` 금지, `as` 캐스팅도 사유 주석 필수
- **시크릿은 expo-secure-store 만** — AsyncStorage 에 토큰 저장 금지

## components.view.screens

- **Expo Router file-based routing** (`app/<route>.tsx`)
- 인증 영역 / 메인 영역은 group 으로 분리 (`(auth)/`, `(main)/`)
- 각 group 의 `_layout.tsx` 에서 ProtectedRoute 패턴 (`redirect` callback)
- 화면 → `containers/<domain>/<Domain>Container.tsx` 1:1 매핑

## components.view.components

- **공용**: `src/shared/components/` — RN 컴포넌트만 (도메인 로직 0)
- **컨테이너**: `src/containers/<domain>/` — store 연결, API 호출
- **프레젠테이션**: props 로만 데이터 받음 (store 직접 접근 금지)

## components.state.flow

- 도메인별 store: `src/containers/<domain>/store/<domain>.store.ts`
- authStore: `src/shared/store/auth.store.ts` (여러 화면 공유)
- Store action 에서 axios 호출 (paired 모드) 또는 로컬 storage 직접 (standalone)
- 서버 상태 라이브러리 (React Query 등) 금지 — Zustand 일원화

## components.mobile.navigation

- Expo Router 의 file-based routing
- Stack / Tabs / Drawer 의 `_layout.tsx` 에서 정의
- Deep linking: `expo-linking` + `app.config.ts` 의 `scheme`
- Route guard: `_layout.tsx` 의 `redirect` callback (auth → role → onboarding)

## components.mobile.build_config

- `app.config.ts` 의 `extra` 필드로 env 주입 (정적 값만, 시크릿 X)
- EAS Build profiles: `development` / `preview` / `production`
- 시크릿: **EAS Secrets** 또는 `eas.json` 의 환경변수 — 코드/리소스 절대 X
- Bundle ID / Version: `app.config.ts` 단일 소스
- 환경별 API URL: `EXPO_PUBLIC_API_BASE_URL` (Expo public env, build 시 주입)

## components.mobile.lifecycle

- 권한: `expo-camera` / `expo-location` / `expo-notifications` 의 `requestPermissionsAsync` — 사용 시점에만 요청
- 백그라운드: `expo-background-fetch` 또는 `expo-task-manager`
- 앱 상태: `react-native` 의 `AppState` API 로 foreground/background 감지
- 푸시: `expo-notifications` (FCM/APNS 자동 처리, Expo Push 토큰 사용)

## components.persistence (선택)

- 단순 KV: **`@react-native-async-storage/async-storage`**
- 빠른 KV (성능 critical): **`react-native-mmkv`**
- 관계형: **`expo-sqlite`** (또는 drizzle-orm + expo-sqlite)
- 시크릿: **`expo-secure-store`** — Keychain (iOS) / EncryptedSharedPreferences (Android)

## components.interface.http (paired 모드만)

- `src/shared/api/client.ts` axios 단일 인스턴스
- 401 interceptor: refresh → 원 요청 재시도
- 환경변수: `EXPO_PUBLIC_API_BASE_URL` (build 시 주입)
- 백엔드와 동일한 contract — `interface.http` 섹션의 endpoint 표 그대로

## 금지 사항 (RN 특화)

- `any` 타입 (TypeScript strict)
- 인라인 스타일 2개 이상 (NativeWind className 또는 StyleSheet 로)
- `console.log` 프로덕션 — `logger` 래퍼 (debug 빌드만 활성)
- React Query / SWR / TanStack Query
- AsyncStorage 에 시크릿 저장 (expo-secure-store 사용)
- `expo eject` (managed workflow 유지)
- `react-native run-android` 등 RN CLI 직접 (Expo CLI 만 — `expo start`, `eas build`)
- `npm` (bun 사용 — bun.lockb 커밋)
- 직접 OS API reflection
- `__DEV__` 분기로만 처리하지 말 것 — `app.config.ts` 의 변형 단위로 분리

## 검증 명령

```bash
cd mobile
bun install
bun test
bun run lint
bunx tsc --noEmit
bunx expo-doctor   # 선택 — Expo SDK 호환성 검증
```
