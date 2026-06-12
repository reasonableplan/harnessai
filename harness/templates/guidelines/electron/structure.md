# Electron — 구조 / 네이밍 컨벤션

> 파일 생성, 디렉토리 배치, import 작성 시 읽어라.

## 프로세스 경계 — 3분할

```
electron/    Main 프로세스 — 파일 I/O, DB, 시스템 API, 윈도우 생명주기
renderer/    React 앱 — UI 만. Node.js API 접근 불가 (contextIsolation)
shared/      순수 타입/유틸 — 양쪽에서 import 가능, I/O·Electron API import 금지
```

- `shared/` 가 `electron/` 또는 `renderer/` 를 import 하면 경계 붕괴 — 금지
- Main↔Renderer 가 주고받는 타입 (`IpcResult`, DTO) 은 전부 `shared/types/` 에

## Renderer 도메인 구조 — colocation

```
renderer/
  shared/              # 2개 이상 도메인이 쓰는 것만 (Button/Input/Modal/Toast, 공용 store)
  containers/
    <domain>/
      index.container.tsx   # 화면 단위 — 하위 섹션 조립
      index.style.ts        # 이 컨테이너의 CVA 스타일 (서브 컴포넌트와 공유)
      components/           # 도메인 로컬 컴포넌트
      store/<domain>.store.ts
      api/<domain>.api.ts   # window.electronAPI 래핑
      schema/<domain>.schema.ts  # zod 폼 스키마
```

- 도메인 로컬 자원은 container 하위에 colocate — 2개 이상 도메인이 쓸 때만 `shared/` 승격
- 진입 컴포넌트 (App 라우트 분기) 는 파라미터 검증만 하고 container 에 위임 — 레이아웃 JSX/비즈니스 로직 금지

## import 경계 — 단방향만 허용

```
shared → containers → 라우트(App)
```

- `shared/` 는 `containers/` 를 import 금지
- container 간 cross-import 금지 — 공유가 필요해지면 `shared/` 로 승격
- 출처: bulletproof-react unidirectional codebase

## 네이밍

- 파일: kebab-case + 역할 도트 접미사 — `<name>.store.ts` / `<name>.api.ts` / `<name>.schema.ts` / `<name>.types.ts`
- 컴포넌트: default export function + 같은 파일 상단 `<Name>Props` interface (`React.FC` 금지)
- 타입/인터페이스: PascalCase (I- 접두사 없음, 소문자 타입명 금지)
- IPC 채널: `domain:action` (ipc.md 참조)

## 폼 / 검증

- 폼 검증은 `<domain>.schema.ts` 에 zod 스키마 + `z.infer` 로 타입 도출 — 수동 if 분기 금지
- 사용자 노출 문자열 (에러/안내/검증 메시지) 은 한국어, 코드 주석은 영어
