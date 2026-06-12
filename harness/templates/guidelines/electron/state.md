# Electron — 상태관리 컨벤션

> Renderer 의 Zustand 스토어, IPC 데이터 로드 코드 작성 시 읽어라.

## 역할 분담

- **Zustand**: Renderer UI 상태 + Main 에서 가져온 데이터의 캐시
- **Main 프로세스**: 파일, DB, 시스템 API — 데이터의 원본. Renderer 는 IPC 로만 접근
- 서버 상태 캐싱 라이브러리 (React Query / SWR) 도입 금지 — 로컬 앱에서는 IPC 호출이 곧 데이터 접근이며, store action 래핑으로 충분

## store action 이 IPC 호출까지 책임

데이터 로드 + 로딩/에러 상태 전이를 store action 하나가 끝까지 처리한다. 컴포넌트는 action 호출과 상태 구독만:

```ts
// containers/drawing/store/drawing.store.ts
interface DrawingState {
  status: 'idle' | 'loading' | 'done' | 'failed'
  drawing: Drawing | null
  error: string | null
  open: (path: string) => Promise<void>
}

export const useDrawingStore = create<DrawingState>((set) => ({
  status: 'idle',
  drawing: null,
  error: null,
  open: async (path) => {
    set({ status: 'loading', error: null })
    const r = await drawingApi.openDrawing(path)
    if (r.ok) set({ status: 'done', drawing: r.data })
    else set({ status: 'failed', error: r.message })
  },
}))
```

- 상태 전이는 `set()` 1회 원자 갱신 — 개별 필드 set 연발 금지
- 유한 상태는 문자열 리터럴 유니온 (`'idle' | 'loading' | 'done' | 'failed'`) — boolean 플래그 조합 금지
- store 는 도메인별 분리 (`<domain>.store.ts`) — 전역 단일 store 금지

## 컴포넌트 구독

- selector 로 필요한 조각만 구독: `useDrawingStore((s) => s.status)` — 객체 통째 구독 금지 (불필요 리렌더)
- 컴포넌트에서 IPC api 직접 호출 금지 — store action 경유

## 토큰/시크릿

- `localStorage` / `sessionStorage` persist 금지 — `electron-store` (encryptionKey) 또는 Main 프로세스 메모리 (LESSON-027)
- Zustand `persist` 미들웨어를 쓰더라도 토큰 필드는 `partialize` 로 제외
