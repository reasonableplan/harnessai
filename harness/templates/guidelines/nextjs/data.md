# Next.js — 데이터 컨벤션 (RSC + Server Actions)

> 데이터 조회, 뮤테이션, DB 접근 코드 작성 시 읽어라.

## 조회 — Server Component 직접

- 서버 데이터는 Server Component 에서 직접 fetch / DB 조회 — 클라이언트에서 `useEffect` + fetch 금지
- 같은 요청 내 중복 조회는 React `cache()` 로 dedupe (page + generateMetadata 등)
- React Query / SWR / TanStack Query 금지 — RSC + Server Actions 가 그 역할

## 뮤테이션 — Server Actions

```ts
// containers/todo/actions/todo.actions.ts
'use server'

export async function createTodo(_prev: ActionState, formData: FormData): Promise<ActionState> {
  const parsed = todoSchema.safeParse(Object.fromEntries(formData))
  if (!parsed.success) return { ok: false, message: '입력값을 확인해주세요' }

  const session = await auth()
  if (!session) return { ok: false, message: '로그인이 필요합니다' }

  await db.insert(todos).values({ ...parsed.data, userId: session.user.id })
  revalidatePath('/todos')
  return { ok: true }
}
```

- **Action 안에서 검증 + 인증 둘 다** — 클라이언트 검증은 UX 용일 뿐, Action 이 신뢰 경계
- 변경 후 `revalidatePath` / `revalidateTag` 필수 — 빼먹으면 stale 화면
- 반환은 `{ ok, message? }` 형태의 직렬화 가능한 상태 객체 — throw 로 흐름 제어 금지
- 클라이언트에서 내부 뮤테이션을 `/api/` POST 로 호출 금지 — Route Handler 는 외부 소비자 전용

## DB (persistence 있을 때)

- Drizzle 클라이언트는 `src/shared/lib/db.ts` 싱글턴 — 요청마다 인스턴스 생성 금지
- Server Component / Server Action 에서만 import — 클라이언트 컴포넌트에서 import 하면 번들에 시크릿 누출
- 마이그레이션: `drizzle-kit push` (dev) / `drizzle-kit migrate` (prod), 생성 파일 수동 검토

## 클라이언트 상태 — Zustand 는 UI 만

- Zustand 에 서버 데이터 저장 금지 (RSC 가 그 역할) — 모달 open/close, 탭, 폼 다단계 등 UI 상태만
- 유한 상태는 문자열 리터럴 유니온, `set()` 1회 원자 갱신

## 인증 / 세션

- 세션 접근은 서버에서 `auth()` — 클라이언트에서 세션 fetch 금지
- 토큰은 httpOnly 쿠키 — `localStorage` / `sessionStorage` 금지 (LESSON-027)
- 환경변수: 클라이언트 노출은 `NEXT_PUBLIC_` 만 — 시크릿에 prefix 붙이는 실수 금지
