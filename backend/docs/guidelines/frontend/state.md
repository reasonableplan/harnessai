# Frontend — 상태 관리 가이드

> Zustand store 작성, 전역/기능별 상태 설계 시 읽어라.

---

## 원칙: Zustand store action이 API를 직접 호출한다

TanStack Query 없음. 서버 데이터도 Zustand store에서 관리한다.
store action 안에서 API 함수를 호출하고, 결과를 state에 저장한다.

```
Zustand store action → API 함수 호출 → state 갱신 → 컴포넌트 리렌더
```

---

## 스토어 위치 — 기능별 vs 전역

```
containers/
  notebooks/
    store/
      notebooks.store.ts   ← 이 기능에서만 쓰는 서버 상태 + 액션

shared/
  store/
    user-store.ts          ← 진짜 전역 (로그인 사용자, 토큰)
    notebook-meta-store.ts ← 앱 전반에서 참조하는 경량 메타 상태
```

**per-feature store**: 해당 컨테이너 안 `store/` 폴더. 2곳 이상 공유할 때만 `shared/store/`로 이동.

---

## 스토어 구조 패턴

```ts
// containers/notebooks/store/notebooks.store.ts
import { create } from 'zustand'
import { getNotebooks, createNotebook, updateNotebook, deleteNotebook } from '@/shared/api/notebook.api'
import type { Notebook, NotebookSortType } from '@/shared/api/notebook.api'

interface NotebooksState {
  // State
  notebooks: Notebook[]
  sort: NotebookSortType
  isLoading: boolean
  error: string | null

  // Actions
  fetchNotebooks: () => Promise<void>
  createNotebook: (title: string) => Promise<void>
  renameNotebook: (id: number, title: string) => Promise<void>
  deleteNotebook: (id: number) => Promise<void>
  togglePin: (id: number, pinned: boolean) => Promise<void>
  setSort: (sort: NotebookSortType) => void
  clearError: () => void
}

export const useNotebooksStore = create<NotebooksState>((set, get) => ({
  notebooks: [],
  sort: 'recent',
  isLoading: false,
  error: null,

  fetchNotebooks: async () => {
    set({ isLoading: true, error: null })
    try {
      const notebooks = await getNotebooks(get().sort)
      set({ notebooks })
    } catch {
      set({ error: '불러오기에 실패했습니다.' })
    } finally {
      set({ isLoading: false })
    }
  },

  createNotebook: async (title) => {
    try {
      const notebook = await createNotebook(title)
      set((s) => ({ notebooks: [notebook, ...s.notebooks] }))
    } catch {
      set({ error: '생성에 실패했습니다.' })
    }
  },

  deleteNotebook: async (id) => {
    const previous = get().notebooks
    set((s) => ({ notebooks: s.notebooks.filter((n) => n.id !== id) })) // 낙관적 삭제
    try {
      await deleteNotebook(id)
    } catch {
      set({ notebooks: previous, error: '삭제에 실패했습니다.' })
    }
  },

  setSort: (sort) => set({ sort }),
  clearError: () => set({ error: null }),
}))
```

---

## 셀렉터로 접근 — 리렌더 최소화

```tsx
// ✅ 필드별 개별 구독
const notebooks = useNotebooksStore((s) => s.notebooks)
const isLoading = useNotebooksStore((s) => s.isLoading)
const error = useNotebooksStore((s) => s.error)

// ❌ 전체 구독 — 스토어 변경 시 항상 리렌더
const store = useNotebooksStore()
```

---

## 낙관적 업데이트 + 롤백

```ts
deleteNotebook: async (id) => {
  const previous = get().notebooks             // 1. 이전 상태 저장
  set((s) => ({ notebooks: s.notebooks.filter((n) => n.id !== id) }))  // 2. 즉시 반영
  try {
    await deleteNotebook(id)                   // 3. 서버 요청
  } catch {
    set({ notebooks: previous, error: '...' }) // 4. 실패 시 원복
  }
}
```

---

## 더블클릭 가드

```ts
if (get().isSyncing) return
set({ isSyncing: true })
try { ... } finally { set({ isSyncing: false }) }
```

---

## 전역 store (shared/store)

진짜 앱 전반에서 쓰이는 것만:

```ts
// user-store.ts — 인증 사용자 + 토큰
// notebook-meta-store.ts — 현재 열린 노트북 ID/제목 (여러 컨테이너에서 참조)
// app-store.ts — 사이드바, 전역 필터 등 UI 상태
```

---

## persist는 최소한으로

```ts
// ✅ 토큰, 사용자 정보만
create(persist((set) => ({ accessToken: null, ... }), { name: 'user' }))

// ❌ 서버 데이터, 임시 UI 상태 persist 금지
```

---

## 판단 기준

| 상황 | 판단 |
|------|------|
| 서버 데이터를 어디서 관리? | per-feature store action이 API 호출 |
| 스토어를 합칠까? | 관심사 다르면 분리 |
| shared/store로 올릴까? | 2곳 이상 공유할 때만 |
| localStorage에 저장? | 토큰/사용자 정보만 |
| 에러 표시? | store의 error state → ErrorAlert 컴포넌트 |
