# Electron (Renderer) — 스타일 컨벤션

> Renderer UI 컴포넌트의 className, 스타일 파일 작성 시 읽어라.
> react-vite 의 CVA 규칙과 동일 — 차이점만 여기 명시.

## Prettier

```json
{ "semi": false, "singleQuote": true, "trailingComma": "all", "printWidth": 100 }
```

## CVA 스타일 분리 — LESSON-STYLE-001

**유틸리티 클래스 2개 이상 → 컨테이너의 `index.style.ts` 에 CVA export. 인라인 금지.**

```ts
// containers/<domain>/index.style.ts
import { cva } from 'class-variance-authority'

export const toolbar = cva(`
  flex
  items-center
  gap-2
  px-2
  py-1
  bg-[var(--bg-surface)]
  border-b
  border-[var(--bg-border)]
`)
```

```tsx
import * as S from './index.style'   // 컨테이너 자신
import * as S from '../index.style'  // 서브 컴포넌트

<div className={S.toolbar()}>
```

- Tailwind 클래스는 템플릿 리터럴 안에 한 줄에 하나씩 세로 나열
- 조건부 스타일은 `variants` — template literal 조건부 (`${active ? ... : ...}`) 금지
- 인라인 허용 예외: 단일 클래스, 라이브러리 크기 오버라이드, Lucide 아이콘 사이즈

## 데스크톱 앱 밀도

- 데스크톱 도구 앱은 웹보다 밀도 높게 — 패딩 8px 이하, radius 4px 이하 기본
- 애니메이션은 `transition-colors` (150ms) 만 — 레이아웃 트랜지션 금지 (도구 앱 반응성)

## HTML 규칙

- form submit 아닌 버튼엔 `type="button"` 필수
- 내용 없는 버튼엔 `aria-label` 필수
- `type="number"` 금지 — `type="text" inputMode="numeric"` (LESSON-006, CJK IME)

## 디자인 토큰

- 색상은 CSS 변수 (`--bg-surface`, `--text-primary` 등) 로만 — hex 직접 사용 금지
- 토큰 정의는 프로젝트 skeleton 의 view 섹션이 권위 — 없으면 추가 후 사용
