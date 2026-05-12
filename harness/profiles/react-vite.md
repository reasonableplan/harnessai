---
id: react-vite
name: React + Vite Frontend
status: confirmed
extends: _base
version: 1
maintainer: harness-core

paths: [".", "frontend/", "apps/web/", "apps/frontend/"]
detect:
  files: [package.json]
  contains:
    package.json: ['"react"']
  contains_any:
    package.json: ['"vite"']
  not_contains:
    package.json: ['"next"', '"electron"', '"react-native"', '"expo"']

components:
  - id: view.screens
    required: true
    skeleton_section: view.screens
    description: 경로별 Container (react-router-dom v7)
  - id: view.components
    required: true
    skeleton_section: view.components
    description: 공용 컴포넌트 + 컴포넌트 트리
  - id: state.flow
    required: true
    skeleton_section: state.flow
    description: Zustand store — store action에서 API 호출
  - id: interface.http
    required: false
    skeleton_section: interface.http
    description: axios 클라이언트 + interceptor (401 refresh)
  - id: core.logic
    required: true
    skeleton_section: core.logic
    description: 유틸 함수 (formatters, validators)

skeleton_sections:
  required: [overview, stack, view.screens, view.components, state.flow, core.logic, tasks, notes]
  optional: [requirements, configuration, errors, auth, interface.http, test_strategy, ci_cd, user_journey, error_ux, environments]
  order: [overview, requirements, stack, configuration, environments, errors, auth, interface.http, view.screens, view.components, state.flow, core.logic, error_ux, test_strategy, ci_cd, user_journey, tasks, notes]

toolchain:
  install: "pnpm install"
  test: "pnpm test"
  lint: "pnpm lint"
  type: "pnpm exec tsc --noEmit"
  format: "pnpm format"

whitelist:
  runtime:
    - react
    - react-dom
    - react-router-dom
    - zustand
    - axios
    - react-hook-form
    - zod
    - tailwindcss
    - class-variance-authority
    - clsx
    - tailwind-merge
    - lucide-react
    - postcss
    - autoprefixer
  dev:
    - vite
    - "@vitejs/plugin-react"
    - vitest
    - "@testing-library/react"
    - "@testing-library/jest-dom"
    - typescript
    - eslint
    - prettier
  prefix_allowed:
    - "@radix-ui/"

file_structure: |
  frontend/
    package.json
    vite.config.ts
    tsconfig.json
    .env.example
    src/
      main.tsx                 # 엔트리포인트
      App.tsx                  # Router + Providers
      shared/
        components/            # Button, Input, Modal, Toast
        store/
          auth.store.ts
        api/
          client.ts            # axios + interceptor
        types/
      containers/
        <domain>/
          <Domain>Container.tsx
          components/
          store/
            <domain>.store.ts
          index.style.ts       # CVA
      core/
        validators/
        formatters/
    __tests__/

provides_capabilities:
  - ui
  - complex_state
  - env_config

gstack_mode: manual
gstack_recommended:
  before_design: [office-hours]
  after_design: [plan-design-review]
  after_build: [design-review, review]
  before_ship: [qa]
  after_ship: [retro]

lessons_applied:
  - LESSON-006   # type=number CJK IME
  - LESSON-STYLE-001  # CVA + index.style.ts
---

# React + Vite Frontend Profile

## 핵심 원칙

- **상태 관리는 Zustand 단일화** — React Query 사용 금지. Store action에서 직접 axios 호출
- **낙관적 업데이트 패턴** — 즉시 로컬 변경 → 실패 시 fetch로 롤백
- **CVA + `index.style.ts` 분리** — 인라인 Tailwind 2개 이상 금지 (LESSON-STYLE-001)
- **`type="number"` 금지** — `type="text" inputMode="numeric"` 사용 (LESSON-006)
- **폼 submit 아닌 버튼에 `type="button"` 명시** — 의도치 않은 폼 제출 방지
- **shadcn/ui 사용 시 base-ui 기반** — `render=` 패턴, `asChild` 금지

## components.view.screens

- react-router-dom v7
- `<ProtectedRoute>` 래퍼로 인증 필요 경로 감쌈
- 경로 → 컨테이너 1:1 매핑 (skeleton.view.screens 섹션과 일치)

## components.view.components

- **공용 컴포넌트**는 `shared/components/` — 도메인 로직 0
- **컨테이너**는 `containers/<domain>/` — store 연결, API 호출
- **프레젠테이션 컴포넌트**는 props로만 데이터 받음 (store 직접 접근 금지)

## components.state.flow

- 각 도메인별 store: `containers/<domain>/store/<domain>.store.ts`
- authStore만 `shared/store/auth.store.ts` (여러 화면 공유)
- Store action:
  - loading/error 상태 관리
  - axios 호출 후 response.data 저장
  - 실패 시 error 필드 세팅 + toast
- **React Query, SWR 같은 서버 상태 라이브러리 금지** — Zustand로 일원화

## components.interface.http

- `shared/api/client.ts`에 axios 인스턴스 단일
- 401 interceptor: POST `/api/auth/refresh` → 성공 시 원 요청 재시도
- 환경변수: `VITE_API_BASE_URL`

## 금지 사항

- `any` 타입 (TypeScript)
- 인라인 Tailwind 2개 이상 (CVA로)
- `console.log` — 프로덕션 코드 (logger 래퍼 사용)
- store 밖에서 axios 직접 호출
- React Query / SWR / TanStack Query

## 검증 명령

```bash
cd frontend
pnpm test
pnpm lint
pnpm exec tsc --noEmit
```
