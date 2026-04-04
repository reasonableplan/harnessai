# Frontend — 스타일 가이드

> UI 컴포넌트 작성, className 관리, 디자인 토큰 작업 시 읽어라.

---

## Prettier 설정

세미콜론 없음, 단일 따옴표, trailing comma, 100자 제한.

```json
{ "semi": false, "singleQuote": true, "trailingComma": "all", "printWidth": 100 }
```

---

## shadcn/ui — base-ui 기반 주의사항

이 프로젝트의 shadcn 컴포넌트는 **Radix UI가 아니라 base-ui** 기반이다.

```tsx
// ❌ Radix 패턴 — 작동 안 함
<DialogTrigger asChild>
  <Button>Open</Button>
</DialogTrigger>

// ✅ base-ui 패턴
<DialogTrigger render={<Button />}>
  Open
</DialogTrigger>

// ❌ Accordion에 type/collapsible 없음
<Accordion type="single" collapsible>

// ✅
<Accordion>
```

---

## HTML 규칙

```tsx
// ✅ form submit 아닌 버튼엔 type="button" 필수
<button type="button" onClick={handleClick}>Click</button>

// ✅ 내용 없는 버튼엔 aria-label 필수
<button type="button" aria-label="View TODO column" className={S.dot()} />

// ❌ type 없는 버튼
<button onClick={handleClick}>Click</button>
```

---

## CVA 스타일 분리 — 핵심 규칙

**유틸리티 클래스 2개 이상 → `index.style.ts`에 CVA export. 인라인 금지.**

### 파일 구조

```
containers/feature-name/
  index.style.ts   ← 이 컨테이너의 모든 CVA 스타일
  index.container.tsx
  components/
    my-component.tsx  ← import * as S from '../index.style'
```

서브 컴포넌트는 컨테이너의 `index.style.ts`를 공유한다. 별도 style 파일 없음.

### CVA 작성 패턴

```ts
import { cva } from 'class-variance-authority'

// 정적 스타일
export const card = cva(`
  p-4
  bg-[var(--bg-surface)]
  rounded-xl
  border
  border-[var(--bg-border)]
  hover:border-[var(--accent-blue)]
  transition-colors
  cursor-pointer
`)

// 조건부 → variants (template literal 금지)
export const dot = cva(`
  size-2
  rounded-full
  transition-colors
`, {
  variants: {
    active: {
      true: 'bg-[var(--accent-blue)]',
      false: 'bg-[var(--bg-border)]',
    },
  },
})
```

### 컴포넌트에서 사용

```tsx
import * as S from '../index.style'  // 서브 컴포넌트
import * as S from './index.style'   // 컨테이너 자신

// ✅
<div className={S.card()}>
<button className={S.dot({ active: isActive })}>

// ❌ 인라인 멀티 클래스
<div className="p-4 bg-[var(--bg-surface)] rounded-xl ...">

// ❌ template literal 조건부
<div className={`size-2 ${isActive ? 'bg-blue' : 'bg-gray'}`}>
```

### 인라인 허용 예외

- 단일 클래스: `"flex-1"`, `"min-w-0"`, `"space-y-2"`
- 라이브러리 크기 오버라이드: `<SelectTrigger className="w-36">`
- Lucide 아이콘 사이즈: `<Plus className="size-4" />`

---

## CSS 디자인 토큰

```css
/* 배경 */
--bg-base: #0f1117
--bg-surface: #1a1d27
--bg-elevated: #242736
--bg-border: #2e3147

/* 텍스트 */
--text-primary: #f1f3fa
--text-secondary: #9ca3c4
--text-muted: #5b6082

/* 강조 */
--accent-blue: #4f76f6
--accent-blue-hover: #6b8ff8

/* 이슈 상태 */
--status-todo: #5b6082
--status-in-progress: #4f76f6
--status-review: #f59e0b
--status-done: #22c55e
--status-cancelled: #ef4444

/* 우선순위 */
--priority-low: #6b7280
--priority-medium: #f59e0b
--priority-high: #f97316
--priority-critical: #ef4444

/* 에이전트 상태 */
--agent-idle: #22c55e
--agent-busy: #f59e0b
--agent-offline: #4b5563

/* 에이전트 역할 링 */
--role-architect: #8b5cf6
--role-designer: #ec4899
--role-orchestrator: #4f76f6
--role-backend-coder: #f97316
--role-frontend-coder: #06b6d4
--role-reviewer: #22c55e
--role-qa: #f59e0b
```

---

## 스타일 작업 순서

1. `index.style.ts` 먼저 작성 — UI 구조를 CVA 이름으로 설계
2. 컴포넌트에서 `S.xxx()` 호출
3. 빌드 후 `npm run lint` 확인
