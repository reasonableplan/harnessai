---
id: nextjs
name: Next.js (App Router)
status: confirmed
extends: _base
version: 1
maintainer: harness-core

paths: [".", "frontend/", "web/", "apps/web/", "apps/frontend/"]
detect:
  files: [package.json]
  contains:
    package.json: ['"next"']
  not_contains:
    package.json: ['"react-native"', '"expo"', '"electron"']

components:
  - id: view.screens
    required: true
    skeleton_section: view.screens
    description: app/(group)/page.tsx — Server Component 기본, 렌더링 전략 (SSG/SSR/ISR) 명시
  - id: view.components
    required: true
    skeleton_section: view.components
    description: src/containers/<domain>/<Domain>Section.tsx (서버) + <Domain>Client.tsx (클라이언트)
  - id: state.flow
    required: true
    skeleton_section: state.flow
    description: RSC 데이터 패칭 + Server Actions (변경) + Zustand (클라이언트 UI 상태만)
  - id: errors
    required: true
    skeleton_section: errors
    description: AppError 계층 + error.tsx / not-found.tsx / global-error.tsx
  - id: auth
    required: false
    skeleton_section: auth
    description: better-auth / NextAuth v5 — httpOnly 세션 쿠키, 서버 세션 기반
  - id: persistence
    required: false
    skeleton_section: persistence
    description: Drizzle ORM + PostgreSQL (풀스택 모드) — Route Handler 없이 서버에서 직접 접근
  - id: interface.http
    required: false
    skeleton_section: interface.http
    description: app/api/ Route Handlers — 외부 API 소비자(모바일 앱 등)가 있을 때만 사용
  - id: core.logic
    required: true
    skeleton_section: core.logic
    description: 순수 함수 (formatters, validators) — 서버/클라이언트 공유 가능

skeleton_sections:
  required:
    - overview
    - stack
    - errors
    - view.screens
    - view.components
    - state.flow
    - core.logic
    - tasks
    - notes
  optional:
    - requirements
    - configuration
    - environments
    - auth
    - persistence
    - interface.http
    - rate_limiting
    - error_ux
    - test_strategy
    - ci_cd
    - observability
    - deployment
  order:
    - overview
    - requirements
    - stack
    - configuration
    - environments
    - errors
    - auth
    - persistence
    - interface.http
    - rate_limiting
    - view.screens
    - view.components
    - state.flow
    - core.logic
    - error_ux
    - observability
    - deployment
    - test_strategy
    - ci_cd
    - tasks
    - notes

toolchain:
  install: "pnpm install"
  test: "pnpm test"
  lint: "pnpm lint"
  type: "pnpm exec tsc --noEmit"
  format: "pnpm format"

whitelist:
  runtime:
    - next
    - react
    - react-dom
    - typescript
    - tailwindcss
    - postcss
    - autoprefixer
    - clsx
    - tailwind-merge
    - class-variance-authority
    - lucide-react
    - zustand
    - zod
    - react-hook-form
    - better-auth
    - next-auth
    - drizzle-orm
    - "@vercel/postgres"
    - postgres
    - framer-motion
  dev:
    - vitest
    - "@vitejs/plugin-react"
    - "@testing-library/react"
    - "@testing-library/jest-dom"
    - playwright
    - eslint
    - eslint-config-next
    - prettier
    - drizzle-kit
    - "@types/react"
    - "@types/node"
  prefix_allowed:
    - "@radix-ui/"
    - "@testing-library/"

file_structure: |
  web/                           # 또는 frontend/ / apps/web/
    package.json
    next.config.ts               # Next.js 설정 (experimental.serverActions 등)
    tsconfig.json
    tailwind.config.ts
    drizzle.config.ts            # DB 마이그레이션 설정 (persistence 있을 때)
    .env.example                 # NEXT_PUBLIC_* (클라이언트) + 서버 전용 분리
    app/
      layout.tsx                 # Root layout (Providers, next/font, Metadata)
      not-found.tsx              # 전역 404
      error.tsx                  # 전역 에러 바운더리 ('use client')
      (auth)/                    # Route group — 인증 불필요 영역
        login/
          page.tsx
        signup/
          page.tsx
      (main)/                    # Route group — 인증 필요 영역
        layout.tsx               # 세션 검증 (redirect 없으면 middleware에서 처리)
        dashboard/
          page.tsx               # Server Component
          loading.tsx            # Suspense fallback
      api/                       # Route Handlers (외부 소비자만)
        auth/
          [...nextauth]/route.ts # better-auth / NextAuth 핸들러
        <domain>/
          route.ts
    src/
      shared/
        components/              # Button / Input / Modal / Toast (공용 UI)
        lib/
          auth.ts                # better-auth / NextAuth 설정
          db.ts                  # Drizzle / Prisma 클라이언트 singleton
        types/
      containers/
        <domain>/
          <Domain>Section.tsx    # Server Component — DB 직접 조회 + 자식에 props 전달
          <Domain>Client.tsx     # 'use client' — 이벤트 핸들러, 훅, 브라우저 API
          actions/
            <domain>.actions.ts  # Server Actions ('use server') — 뮤테이션
          store/
            <domain>.store.ts    # Zustand — 클라이언트 UI 상태만 (서버 데이터 X)
      core/
        validators/
        formatters/
    __tests__/
      unit/
      e2e/                       # Playwright

gstack_mode: manual
gstack_recommended:
  before_design: [office-hours]
  after_design: [plan-design-review]
  after_build: [design-review, review]
  before_ship: [qa]
  after_ship: [retro]

lessons_applied:
  - LESSON-006    # type=number CJK IME — type="text" inputMode="numeric" 사용
  - LESSON-022    # JWT type claim 필수 (auth 섹션 있을 때)
  - LESSON-023    # token_version — logout 시 서버에서 무효화
  - LESSON-027    # 토큰 저장 — httpOnly 쿠키 (localStorage/sessionStorage 금지)
  - LESSON-STYLE-001  # CVA + index.style.ts — 인라인 Tailwind 2개 이상 금지
---

# Next.js (App Router) Profile

## 핵심 원칙

- **App Router 전용** — Pages Router (`pages/`) 혼용 금지
- **Server Component 기본** — `use client` 는 이벤트 핸들러·훅·브라우저 API 가 있을 때만
- **Server Actions으로 뮤테이션** — 클라이언트에서 `/api/` fetch 하지 말 것 (폼 submit, 버튼 onClick → `action.ts`)
- **Zustand는 클라이언트 UI 상태만** — 서버 데이터를 Zustand에 넣지 않는다 (RSC가 그 역할)
- **Route Handler는 외부 소비자 전용** — 모바일 앱·서드파티가 없으면 `app/api/` 만들지 않는다
- **`NEXT_PUBLIC_` prefix 규칙** — 클라이언트에 노출될 값만. 시크릿은 서버 전용
- **TypeScript strict** — `any` 금지, `as` 캐스팅 사유 주석 필수

## components.view.screens

- **파일 기반 라우팅**: `app/(group)/page.tsx` — 1 파일 = 1 경로
- **렌더링 전략** (섹션에 명시 필수):
  - 정적 (SSG): `export const dynamic = 'force-static'` 또는 `generateStaticParams`
  - 동적 (SSR): 기본값 (`cookies()` / `headers()` 사용 시 자동 전환)
  - ISR: `export const revalidate = <초>`
- **Metadata**: 각 `page.tsx` 에 `generateMetadata` 또는 `export const metadata`
- **loading.tsx**: 데이터 fetch 있는 페이지마다 Suspense fallback 필수
- **error.tsx**: 에러 바운더리 (must be `'use client'`)
- 인증 영역 분리: `(auth)/` vs `(main)/` Route Group — `(main)/layout.tsx` 에서 세션 검증

## components.view.components

- **서버 컴포넌트** (`<Domain>Section.tsx`): DB/API 직접 조회, 자식에 props 전달
- **클라이언트 컴포넌트** (`<Domain>Client.tsx`): `'use client'` — 상태, 이벤트, 애니메이션
- **공용 컴포넌트** (`shared/components/`): 도메인 로직 0, 순수 UI
- `use client` 를 layout 수준에 올리면 하위 트리 전체가 클라이언트로 전락 — **절대 금지**

## components.state.flow

- **서버 데이터**: Server Component 에서 직접 fetch / DB 조회 — Zustand 저장 금지
- **뮤테이션**: Server Actions (`'use server'`) → `revalidatePath` / `revalidateTag` 로 캐시 무효화
- **클라이언트 UI 상태**: Zustand — 모달 open/close, 탭 선택, 폼 다단계 등
- React Query / SWR / TanStack Query 금지 — RSC + Server Actions 로 대체

## components.auth

- **better-auth** 권장 (NextAuth v5/Auth.js 도 허용)
- 세션: **httpOnly 쿠키** — `localStorage` / `sessionStorage` 토큰 저장 절대 금지 (LESSON-027)
- JWT 사용 시 payload 에 `type` + `ver` claim 필수 (LESSON-022, 023)
- 미들웨어 (`middleware.ts`): 인증 필요 경로 보호 (`(main)/` prefix)
- `auth()` 서버 함수로 세션 접근 — 클라이언트에서 세션 직접 fetch 금지

## components.persistence (풀스택 모드)

- **Drizzle ORM** 권장 (Prisma 도 허용)
- DB 클라이언트: `src/shared/lib/db.ts` 싱글턴 — `new PrismaClient()` 매 요청마다 금지
- Server Component / Server Action 에서만 직접 접근 — 클라이언트 컴포넌트 금지
- 마이그레이션: `drizzle-kit push` (dev) / `drizzle-kit migrate` (prod)

## components.interface.http (Route Handlers — 외부 소비자만)

- `app/api/<domain>/route.ts` — `GET`, `POST`, `PUT`, `DELETE` 핸들러
- 응답 래퍼: `NextResponse.json({ error, code, details })` — 공통 에러 형식
- 인증 필요 시 `auth()` 로 세션 검증 후 처리
- **내부(웹) 에서는 Route Handler 거치지 않는다** — Server Action 사용

## 금지 사항

- `use client` 를 layout 수준 / 상위 트리에 무분별 적용
- 클라이언트에서 DB 직접 접근 (Drizzle / Prisma import)
- `localStorage` / `sessionStorage` 에 토큰·세션 저장 (LESSON-027)
- `<img>` 태그로 외부 이미지 — `next/image` 사용 (`unoptimized` 도 원칙상 금지)
- `@import` CDN 폰트 — `next/font` 사용
- `type="number"` — `type="text" inputMode="numeric"` (LESSON-006)
- 인라인 Tailwind 2개 이상 — CVA + index.style.ts (LESSON-STYLE-001)
- `console.log` 프로덕션 — logger 래퍼 (debug 빌드만 활성)
- React Query / SWR / TanStack Query (RSC + Server Actions 로 대체)
- `pages/` 디렉토리 생성 (App Router 전용)
- Server Action 없이 클라이언트에서 직접 `/api/` POST (내부 뮤테이션용)

## 검증 명령

```bash
cd web
pnpm install
pnpm test
pnpm lint
pnpm exec tsc --noEmit
```
