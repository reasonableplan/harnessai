# Next.js — 스타일 컨벤션

> UI 컴포넌트의 className, 폰트/이미지 처리 시 읽어라.
> react-vite 의 CVA 규칙과 동일 — Next.js 고유 사항만 추가.

## Prettier

```json
{ "semi": false, "singleQuote": true, "trailingComma": "all", "printWidth": 100 }
```

## CVA 스타일 분리 — LESSON-STYLE-001

**유틸리티 클래스 2개 이상 → 컨테이너의 `index.style.ts` 에 CVA export. 인라인 금지.**

```ts
// containers/<domain>/index.style.ts
import { cva } from 'class-variance-authority'

export const card = cva(`
  p-4
  bg-[var(--bg-surface)]
  rounded-xl
  border
  border-[var(--bg-border)]
`)
```

- `index.style.ts` 는 서버/클라이언트 어느 쪽에서도 import 가능 (순수 모듈 — `'use client'` 불필요)
- Tailwind 클래스는 한 줄에 하나씩 세로 나열, 조건부는 `variants` (template literal 조건부 금지)
- 인라인 허용 예외: 단일 클래스, 라이브러리 크기 오버라이드, Lucide 아이콘 사이즈

## 폰트 — next/font

```ts
// app/layout.tsx
import { Noto_Sans_KR } from 'next/font/google'
const notoSansKr = Noto_Sans_KR({ subsets: ['latin'], display: 'swap' })
```

- `@import` CDN 폰트 / `<link>` 폰트 태그 금지 — FOUT + 외부 요청
- 폰트 변수는 root layout 한 곳에서만 선언

## 이미지 — next/image

- `<img>` 태그 금지 — `next/image` 사용 (`unoptimized` 도 원칙상 금지)
- 외부 도메인 이미지는 `next.config.ts` 의 `images.remotePatterns` 에 선언
- LCP 후보 이미지에 `priority` — 그 외엔 기본 lazy

## HTML 규칙

- form submit 아닌 버튼엔 `type="button"`, 내용 없는 버튼엔 `aria-label` 필수
- `type="number"` 금지 — `type="text" inputMode="numeric"` (LESSON-006)

## 디자인 토큰

- 색상은 CSS 변수로만 — hex 직접 사용 금지. 토큰 정의는 skeleton view 섹션이 권위
