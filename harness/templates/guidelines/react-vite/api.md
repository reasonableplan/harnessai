# Frontend — API 연동 가이드

> API 함수 작성, fetcher 사용, 인증 처리 작업 시 읽어라.

---

## 파일 구조

```
shared/
  api/
    notebook.api.ts        ← API 함수 + 타입 정의 (같은 파일)
    chat.api.ts
    auth.api.ts
    ...
  utils/
    fetcher.ts             ← axios 인스턴스 + interceptors + fetcher 래퍼 + SSE
```

---

## 파일 네이밍 — `*.api.ts`

API 함수와 그 도메인의 타입을 **같은 파일**에 정의한다.
`shared/types/`에 별도 타입 파일을 만들지 않아도 된다.

```ts
// shared/api/notebook.api.ts
import { fetcher } from '@/shared/utils/fetcher'

// 타입도 같은 파일에
export interface Notebook {
  id: number
  title: string
  pinned: boolean
  created_at: string
}

export type NotebookSortType = 'recent' | 'created_at' | 'name'

export const getNotebooks = async (sort: NotebookSortType = 'recent'): Promise<Notebook[]> => {
  const response = await fetcher.get<Notebook[]>(`/notebook/list?sort=${sort}`)
  return response.data
}

export const createNotebook = async (title: string): Promise<Notebook> => {
  const response = await fetcher.post<Notebook>('/notebook', { title })
  return response.data
}

export const updateNotebook = async (id: number, body: { title?: string; pinned?: boolean }): Promise<Notebook> => {
  const response = await fetcher.patch<Notebook>(`/notebook/${id}`, body)
  return response.data
}

export const deleteNotebook = async (id: number) => {
  return fetcher.delete(`/notebook/${id}`)
}
```

---

## fetcher 래퍼

백엔드가 항상 `{ code, message, data, status }` 래퍼를 반환한다.
`fetcher`는 axios 인스턴스를 감싸서 `BaseResponse<T>`를 반환한다.

```ts
// fetcher.get<T>(url) → Promise<BaseResponse<T>>
const response = await fetcher.get<Notebook[]>('/notebook/list')
return response.data  // BaseResponse.data = Notebook[]
```

```ts
export const fetcher = {
  get: <T>(url: string) =>
    api.get<BaseResponse<T>>(apiUrl(url)).then((res) => res.data),
  post: <T>(url: string, data?: unknown) =>
    api.post<BaseResponse<T>>(apiUrl(url), data).then((res) => res.data),
  patch: <T>(url: string, data?: unknown) =>
    api.patch<BaseResponse<T>>(apiUrl(url), data).then((res) => res.data),
  delete: <T = null>(url: string) =>
    api.delete<BaseResponse<T>>(apiUrl(url)).then((res) => res.data),
}
```

---

## axios 인스턴스 + 인터셉터

```ts
// shared/utils/fetcher.ts 핵심 구조

// 1. 요청 인터셉터 — 토큰 자동 주입
api.interceptors.request.use((config) => {
  const token = useUserStore.getState().accessToken
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 2. 401 응답 인터셉터 — 토큰 갱신 (큐잉 방식)
let isRefreshing = false
let refreshQueue: Array<{ resolve: (token: string) => void; reject: (err: unknown) => void }> = []

// 동시 401이 여러 번 와도 갱신 요청은 1번만. 나머지는 큐에서 대기
```

---

## BaseResponse 타입

```ts
// shared/types/response.ts 또는 fetcher.ts 상단에 정의
export interface BaseResponse<T> {
  code: number
  message: string
  data: T
  status: string
}
```

---

## SSE (서버 전송 이벤트)

```ts
import { SSE } from '@/shared/utils/fetcher'

const controller = new AbortController()

await SSE({
  url: '/chat/stream',
  data: { message: input },
  signal: controller.signal,
  onMessage: (event) => {
    if (controller.signal.aborted) return   // stale 요청 무시
    // event.data 처리
  },
  onError: () => {
    if (controller.signal.aborted) return   // 사용자 취소는 에러 아님
    set({ error: '연결 오류가 발생했습니다.' })
  },
})

// 취소
controller.abort()
```

---

## Query params — snake_case 변환

FastAPI Query params는 `alias_generator`가 적용되지 않는다.
camelCase로 보내면 서버가 무시한다 → 반드시 snake_case로 변환해서 전송.

```ts
// ❌ camelCase 그대로 전송 — 필터 무시됨
api.get('/issues', { params: { projectId: 1, sprintId: 2 } })

// ✅ snake_case 변환 후 전송
const toSnakeParams = (filters: IssueFilters) => ({
  project_id: filters.projectId,
  sprint_id: filters.sprintId,
  issue_type: filters.issueType,
  // 새 파라미터 추가 시 반드시 여기도 추가
})
api.get('/issues', { params: toSnakeParams(filters) })
```

---

## 에러 처리

store action에서 catch → error state 저장 → 컨테이너에서 ErrorAlert 렌더링.

```ts
// store action
} catch {
  set({ error: '불러오기에 실패했습니다.' })
}

// 컨테이너
<ErrorAlert error={error} onClose={clearError} />
```

특정 에러 코드 분기가 필요한 경우:

```ts
import { AxiosError } from 'axios'

} catch (err) {
  const code = (err as AxiosError<BaseResponse<null>>).response?.data?.code
  if (code === 'ERR_DEPENDENCY_CYCLE') {
    set({ cycleError: '순환 의존성이 발생합니다.' })
    return
  }
  set({ error: '요청에 실패했습니다.' })
}
```

---

## 판단 기준

| 상황 | 판단 |
|------|------|
| API 타입은 어디에? | `*.api.ts` 파일 안에 같이 |
| 인터셉터로 BaseResponse 벗길까? | 금지 — fetcher 래퍼에서 `.then(res => res.data)` |
| Query params camelCase? | toSnakeParams()로 변환 필수 |
| 에러 표시? | store error state → ErrorAlert |
| 스트리밍? | SSE helper + AbortController |
