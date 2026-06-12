# Next.js — 라우팅 컨벤션 (App Router)

> `app/` 하위 파일 생성, 라우트 설계 시 읽어라.

## 파일 규칙

- 1 경로 = 1 `page.tsx`. Pages Router (`pages/`) 생성 금지
- 데이터 fetch 있는 페이지마다 `loading.tsx` (Suspense fallback) 필수
- 라우트 그룹별 `error.tsx` (`'use client'` 필수) — 전역은 `app/error.tsx` + `app/not-found.tsx`
- 라우트 세그먼트 디렉토리는 kebab-case (`order-history/`)

## Route Group — 인증 경계

```
app/
  (auth)/     # 비로그인 영역 — login / signup
  (main)/     # 로그인 필요 영역
    layout.tsx   # 세션 검증 + redirect — 페이지마다 중복 검증 금지
```

- 세션 검증은 `(main)/layout.tsx` 또는 `middleware.ts` 한 곳 — 두 곳에 중복 작성 금지
- 페이지 컴포넌트 안에서 `redirect()` 분기 반복 금지

## 렌더링 전략 — 페이지마다 명시적 결정

| 전략 | 선언 | 사용처 |
|---|---|---|
| SSG | `generateStaticParams` / `dynamic = 'force-static'` | 마케팅, 문서 |
| ISR | `export const revalidate = <초>` | 목록형 콘텐츠 |
| SSR | 기본값 (`cookies()`/`headers()` 사용 시 자동) | 개인화 페이지 |

- skeleton `view.screens` 섹션에 페이지별 전략이 선언돼 있으면 그대로 — 임의 변경 금지
- `dynamic = 'force-dynamic'` 은 사유 주석 없이 금지 (캐시 전부 포기하는 결정)

## Metadata

- 각 `page.tsx` 에 `export const metadata` 또는 `generateMetadata` — title/description 누락 금지
- 동적 페이지는 `generateMetadata` 에서 데이터 기반 생성 (fetch 중복은 `cache()` 로 dedupe)

## 금지 사항

- `pages/` 디렉토리 생성
- layout 수준 `'use client'` — 하위 트리 전체가 클라이언트로 전락
- 라우트 핸들러 (`app/api/`) 를 내부 웹 뮤테이션 용도로 생성 — Server Action 사용 (data.md 참조)
