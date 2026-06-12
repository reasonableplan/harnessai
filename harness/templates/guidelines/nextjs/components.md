# Next.js — 컴포넌트 컨벤션

> 컴포넌트 생성, Server/Client 분리 결정 시 읽어라.

## Server / Client 분리 — 기본은 서버

- **Server Component 기본** — `'use client'` 는 이벤트 핸들러·훅·브라우저 API 가 있을 때만
- 분리 단위: 도메인별 `<Domain>Section.tsx` (서버, 데이터 조회) + `<Domain>Client.tsx` (클라이언트, 상호작용)

```tsx
// containers/dashboard/DashboardSection.tsx — Server Component
export default async function DashboardSection() {
  const stats = await getStats()           // DB/API 직접 조회
  return <DashboardClient stats={stats} /> // 직렬화 가능한 props 만 전달
}

// containers/dashboard/DashboardClient.tsx
'use client'
export default function DashboardClient({ stats }: DashboardClientProps) { ... }
```

- 서버→클라이언트 props 는 직렬화 가능한 값만 — 함수, Date 인스턴스(문자열로 변환), class 인스턴스 금지
- `'use client'` 를 상위로 올려서 해결하려는 충동 금지 — 상호작용 부분만 클라이언트 컴포넌트로 쪼개 내려라

## 디렉토리 — colocation

```
src/
  shared/components/    # 2개 이상 도메인이 쓰는 순수 UI 만 (Button/Input/Modal/Toast)
  containers/
    <domain>/
      <Domain>Section.tsx
      <Domain>Client.tsx
      components/             # 도메인 로컬 컴포넌트
      actions/<domain>.actions.ts
      store/<domain>.store.ts
      schema/<domain>.schema.ts   # zod 폼 스키마 + z.infer
```

- 도메인 로컬 자원은 container 하위 colocate — 2개 이상 도메인이 쓸 때만 `shared/` 승격
- `shared/` 컴포넌트에 도메인 로직 0 — props 로만 동작

## import 경계 — 단방향만 허용

```
shared → containers → app(라우트)
```

- `shared/` 는 `containers/` import 금지, container 간 cross-import 금지 — 필요 시 `shared/` 승격
- 출처: bulletproof-react unidirectional codebase

## 네이밍 / 작성 규칙

- 컴포넌트: default export function + 같은 파일 상단 `<Name>Props` interface (`React.FC` 금지)
- 폼 검증: `<domain>.schema.ts` 의 zod 스키마 + `z.infer` — 수동 if 분기 금지
- 사용자 노출 문자열은 한국어, 코드 주석은 영어
- `type="number"` 금지 — `type="text" inputMode="numeric"` (LESSON-006)
