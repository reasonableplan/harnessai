# Frontend — 컴포넌트 & 구조 가이드

> 컨테이너/컴포넌트 신규 작성, 폴더 구조 설계 시 읽어라.

---

## 디렉토리 구조

```
frontend/src/
  containers/
    feature-name/
      index.container.tsx   ← default export, store에서 state/action 가져와 조합
      index.style.ts        ← CVA exports 전부
      components/           ← named exports, 순수 UI 조각
      store/                ← 이 기능 전용 Zustand store (있을 때만)
      constants/            ← 이 기능 전용 상수 (있을 때만)
      utils/                ← 이 기능 전용 유틸 (있을 때만)
  shared/
    api/          ← *.api.ts 파일들 (함수 + 타입 같이)
    components/   ← 재사용 UI (2곳 이상 사용할 때만)
    store/        ← 전역 Zustand store (user, app-wide UI 상태)
    types/        ← 앱 전반 공통 타입 (BaseResponse 등)
    style/        ← tokens.css
    utils/        ← fetcher.ts, cn.ts 등
```

---

## 컨테이너 패턴

### 컨테이너 = 오케스트레이터

```tsx
// ✅ index.container.tsx
'use client'  // Next.js 사용 시 필수

import { useEffect } from 'react'
import { useNotebooksStore } from './store/notebooks.store'
import NotebookCard from './components/notebook-card'
import { ErrorAlert } from '@/shared/components'
import * as S from './index.style'

export default function NotebooksContainer() {
  // 셀렉터 per-field — 개별 구독으로 리렌더 최소화
  const notebooks = useNotebooksStore((s) => s.notebooks)
  const isLoading = useNotebooksStore((s) => s.isLoading)
  const error = useNotebooksStore((s) => s.error)
  const fetchNotebooks = useNotebooksStore((s) => s.fetchNotebooks)
  const clearError = useNotebooksStore((s) => s.clearError)

  useEffect(() => { fetchNotebooks() }, [fetchNotebooks])

  if (isLoading) return <div className={S.loading()}>불러오는 중...</div>

  return (
    <div className={S.page()}>
      <ErrorAlert error={error} onClose={clearError} />
      {notebooks.map((nb) => <NotebookCard key={nb.id} notebook={nb} />)}
    </div>
  )
}

// ✅ components/notebook-card.tsx — 순수 UI
export default function NotebookCard({ notebook }: { notebook: Notebook }) {
  return <div className={S.card()}>{notebook.title}</div>
}
```

컨테이너가 하는 일: store 연결, useEffect, 로딩/에러 처리, 컴포넌트 조합
컴포넌트가 하는 일: props 받아서 UI 렌더링만 — store 직접 접근 금지

### 새 기능 추가 = 기존 컨테이너 복사

기존 컨테이너 폴더를 복사해서 이름만 바꾸면 시작할 수 있는 구조가 좋은 구조다.

---

## 컴포넌트 설계 원칙

### 과도하게 쪼개지 마라

```tsx
// ✅ 18줄짜리 컴포넌트 하나로 충분
export function ErrorAlert({ title, description }: Props) {
  return (
    <div className={S.alert()}>
      <p className={S.alertTitle()}>{title}</p>
      <p className={S.alertDesc()}>{description}</p>
    </div>
  )
}

// ❌ ErrorProvider, useErrorAlert, createErrorMiddleware — 과잉
```

### 한 곳에서만 쓰이는 로직은 쪼개지 마라

```tsx
// ✅ 한 함수에서 흐름이 보이게
const getTimeRemaining = (iso: string) => {
  const diff = new Date(iso).getTime() - Date.now()
  if (diff <= 0) return '만료됨'
  const hours = Math.floor(diff / 3600000)
  const mins = Math.floor((diff % 3600000) / 60000)
  return hours > 0 ? `${hours}시간 ${mins}분` : `${mins}분`
}

// ❌ parseDate(), calcDiff(), formatDuration() 분리
```

### shared/로 옮기는 기준

2곳 이상에서 사용할 때만 `shared/components/`로 이동. 그 전엔 각 컨테이너 안에 두어라.

---

## React 규칙

```tsx
// ✅ 함수형 컴포넌트 + interface Props
interface IssueCardProps {
  issue: Issue
  onDelete?: (id: number) => void
}

export function IssueCard({ issue, onDelete }: IssueCardProps) {
  return <div className={S.card()}>{issue.title}</div>
}

// ❌ any props
export function IssueCard({ issue, onDelete }: any) { ... }
```

---

## URL params가 source of truth

Zustand store의 `selectedProjectId` 같은 메모리 상태는 새로고침 시 null로 초기화된다.
영구적 컨텍스트(현재 보고 있는 프로젝트/이슈 ID)는 반드시 URL에서 읽어라.

```tsx
// ❌ store만 의존 → 새로고침 시 null → 버튼/컴포넌트 소실
const projectId = useAppStore((s) => s.selectedProjectId)

// ✅ URL params 우선, store는 폴백
const { projectId: paramId } = useParams<{ projectId?: string }>()
const storeId = useAppStore((s) => s.selectedProjectId)
const projectId = paramId ? Number(paramId) : storeId
```

`useParams()`는 중첩 라우트에서도 부모 params에 접근 가능하다.

---

## Hydration (SSR/CSR 불일치)

```tsx
// 3줄로 해결. Provider 만들지 마라.
function useIsClient() {
  return useSyncExternalStore(() => () => {}, () => true, () => false)
}
```

---

## 상태 전환은 컨테이너에서

두 컴포넌트를 조율하는 로직은 둘 다 모르게 하고 컨테이너가 처리:

```tsx
// PlaygroundContainer
useEffect(() => {
  if (prevStatus !== 'completed' && status === 'completed') {
    setPreviewMode(true)  // ChatView도 PreviewSection도 이 로직 모름
  }
}, [status])
```

---

## 판단 기준

| 상황 | 판단 |
|------|------|
| 컴포넌트를 쪼갤까? | 재사용되거나 100줄 넘을 때만 |
| shared/로 옮길까? | 2곳 이상 사용할 때만 |
| Context/Provider 만들까? | 3줄 헬퍼로 되면 만들지 마라 |
| 라이브러리 감쌀까? | 라이브러리가 잘 하면 감싸지 마라 |
| 새 기능 시작? | 기존 컨테이너 복사해서 시작 |
