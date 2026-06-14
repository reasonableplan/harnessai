---
id: electron
name: Electron (Desktop)
status: confirmed
extends: _base
version: 1
maintainer: harness-core

paths: [".", "apps/desktop/", "desktop/"]
detect:
  files: [package.json]
  contains:
    package.json: ['"electron"']

components:
  - id: interface.ipc
    required: true
    skeleton_section: interface.ipc
    description: ipcMain.handle() 핸들러 + contextBridge.exposeInMainWorld() — Main↔Renderer 계약
  - id: view.screens
    required: true
    skeleton_section: view.screens
    description: Renderer 프로세스 화면 (React) — preload API 경유 IPC 호출
  - id: view.components
    required: true
    skeleton_section: view.components
    description: 공용 컴포넌트 + 컨테이너 (Renderer)
  - id: state.flow
    required: true
    skeleton_section: state.flow
    description: Zustand (Renderer UI 상태) — Main 프로세스 데이터는 IPC 경유
  - id: mobile.build_config
    required: true
    skeleton_section: mobile.build_config
    description: electron-builder 플랫폼별 빌드 설정 (Windows NSIS / macOS DMG / Linux AppImage) + 코드 서명 + 자동 업데이트
  - id: persistence
    required: false
    skeleton_section: persistence
    description: electron-store (설정) + better-sqlite3 (로컬 DB, has.storage 시 활성)
  - id: core.logic
    required: true
    skeleton_section: core.logic
    description: 순수 함수 — Main/Renderer 양쪽에서 import 가능한 공유 로직

skeleton_sections:
  required:
    - overview
    - stack
    - errors
    - interface.ipc
    - mobile.build_config
    - view.screens
    - view.components
    - state.flow
    - core.logic
    - tasks
    - notes
  optional:
    - requirements
    - configuration
    - environments
    - auth
    - persistence
    - error_ux
    - test_strategy
    - ci_cd
    - deployment
  order:
    - overview
    - requirements
    - stack
    - configuration
    - environments
    - errors
    - auth
    - persistence
    - interface.ipc
    - mobile.build_config
    - view.screens
    - view.components
    - state.flow
    - core.logic
    - error_ux
    - deployment
    - test_strategy
    - ci_cd
    - tasks
    - notes

toolchain:
  install: "pnpm install"
  test: "pnpm test"
  lint: "pnpm lint"
  # project-references 루트(tsconfig.json: files:[] + references)는 bare `tsc --noEmit`
  # 가 0개 파일만 검사하고 통과한다 — `-b`(build mode)로 leaf config 를 따라가야 실검사.
  type: "pnpm exec tsc -b --noEmit"
  format: "pnpm format"

whitelist:
  runtime:
    - electron
    - electron-updater
    - electron-store
    - better-sqlite3
    - react
    - react-dom
    - zustand
    - zod
    - react-hook-form
    - tailwindcss
    - postcss
    - autoprefixer
    - clsx
    - tailwind-merge
    - class-variance-authority
    - lucide-react
  dev:
    - vite
    - "@vitejs/plugin-react"
    - electron-builder
    - vitest
    - "@testing-library/react"
    - "@testing-library/jest-dom"
    - playwright
    - typescript
    - eslint
    - prettier
    - "@types/node"
    - "@types/react"
    - "@types/better-sqlite3"
  prefix_allowed:
    - "@radix-ui/"

file_structure: |
  desktop/                         # 또는 apps/desktop/
    package.json
    electron-builder.yml           # 플랫폼별 빌드 / 코드서명 설정
    tsconfig.json                  # paths: { "@shared/*": ["shared/*"] }
    tsconfig.main.json             # Main process (Node.js target)
    tsconfig.renderer.json         # Renderer process (DOM target)
    vite.config.ts                 # Renderer 번들링
    .env.example
    electron/                      # Main 프로세스
      main.ts                      # BrowserWindow 생성 + 앱 생명주기
      preload.ts                   # contextBridge.exposeInMainWorld()
      ipc/
        channels.ts                # IPC 채널 이름 상수 (Main + Renderer 공유)
        handlers/
          <domain>.handler.ts      # ipcMain.handle('<domain>:action', ...)
    renderer/                      # Renderer 프로세스 (React 앱)
      index.html
      main.tsx
      App.tsx
      shared/
        components/                # Button / Input / Modal / Toast
        store/
          auth.store.ts
        types/
          electron.d.ts            # window.electronAPI 타입 선언
      screens/
        <domain>/
          <Domain>Screen.tsx
          components/
          store/
            <domain>.store.ts
      core/
        validators/
        formatters/
    shared/                        # Main + Renderer 공유 순수 로직
      types/
      utils/
    resources/
      icons/                       # icon.ico (Win) / icon.icns (Mac) / icon.png (Linux)
    __tests__/

provides_capabilities:
  - ui
  - ipc
  - complex_state
  - env_config

gstack_mode: manual
gstack_recommended:
  before_design: [office-hours]
  after_design: [plan-design-review]
  after_build: [review]
  before_ship: [qa]
  after_ship: [retro]

lessons_applied:
  - LESSON-006    # type=number CJK IME — type="text" inputMode="numeric"
  - LESSON-022    # JWT type claim (auth 섹션 있을 때)
  - LESSON-023    # token_version — logout 시 무효화
  - LESSON-027    # 토큰 저장 — electron-store (암호화) or Main 프로세스 메모리, localStorage 금지
  - LESSON-STYLE-001  # CVA + index.style.ts — 인라인 Tailwind 2개 이상 금지
---

# Electron (Desktop) Profile

## 핵심 원칙

- **Context Isolation 필수** — `nodeIntegration: false`, `contextIsolation: true` 항상
- **Preload 경유 IPC만** — Renderer 에서 Node.js API 직접 접근 절대 금지
- **채널 이름 상수화** — `electron/ipc/channels.ts` 에 모든 채널명 정의, 문자열 리터럴 직접 사용 금지
- **IPC 타입 안전성** — `window.electronAPI` 에 타입 선언 (`renderer/shared/types/electron.d.ts`)
- **Main 프로세스 무거운 작업** — 파일 I/O, DB, 시스템 API는 Main에서만 (Renderer blocking 방지)
- **자동 업데이트 필수** — `electron-updater` + GitHub Releases / S3, 수동 설치 유도 금지
- **코드 서명 필수** — 미서명 앱은 Windows/macOS 에서 보안 경고 (배포 차단)

## components.interface.ipc

```typescript
// electron/ipc/channels.ts — 채널 이름 상수 (Main + Renderer 공유)
export const IPC_CHANNELS = {
  USER_GET: 'user:get',
  USER_UPDATE: 'user:update',
  FILE_OPEN: 'file:open',
} as const;

// electron/preload.ts — contextBridge 노출
contextBridge.exposeInMainWorld('electronAPI', {
  getUser: (id: string) => ipcRenderer.invoke(IPC_CHANNELS.USER_GET, id),
  updateUser: (data: UserUpdateDto) => ipcRenderer.invoke(IPC_CHANNELS.USER_UPDATE, data),
  openFile: () => ipcRenderer.invoke(IPC_CHANNELS.FILE_OPEN),
});

// renderer/shared/types/electron.d.ts — Renderer 타입
interface Window {
  electronAPI: {
    getUser: (id: string) => Promise<User>;
    updateUser: (data: UserUpdateDto) => Promise<void>;
    openFile: () => Promise<string | null>;
  };
}
```

- skeleton `interface.ipc` 섹션에 채널 목록 + 요청/응답 타입 전부 명시 (Architect 책임)
- 단방향 알림 (Main → Renderer): `ipcRenderer.on()` — 채널 이름도 상수로

## components.mobile.build_config (Electron 빌드)

- **플랫폼 3개**: Windows (NSIS 설치 관리자) / macOS (DMG + Notarization) / Linux (AppImage + deb)
- **환경 변수**: `.env.*` 파일 → Vite `define` 으로 Renderer 주입, Main은 `process.env` 직접
- **코드 서명**:
  - Windows: `CSC_LINK` + `CSC_KEY_PASSWORD` (pfx) — env 변수만, 파일 X
  - macOS: Apple ID + Team ID + App-specific password — env 변수만
- **자동 업데이트**: `electron-updater` + `autoUpdater.checkForUpdatesAndNotify()` — main.ts 에서
- **버전**: `package.json` 의 `version` 단일 소스 → `electron-builder` 자동 반영

## components.persistence

- **설정/소량 KV**: `electron-store` (`new Store<Schema>()`) — Main 프로세스에서만 접근
- **로컬 DB** (has.storage): `better-sqlite3` — 동기 API, WAL 모드 필수, Main에서만
- **토큰 저장** (auth 있을 때): `electron-store` + `encryptionKey` 옵션 — Keychain 연동은 `keytar` (LESSON-027)
- Renderer 에서 DB 직접 접근 금지 — IPC 경유 (Main 핸들러가 처리)

## components.state.flow

- **Zustand**: Renderer UI 상태 (모달, 탭, 폼 단계 등)
- **Main 데이터**: IPC 호출 결과 → Zustand 에 캐시 가능, 단 "서버 상태" 개념 그대로
- React Query / SWR 금지 — IPC 호출은 단순 Zustand action 으로 래핑

## 금지 사항

- `nodeIntegration: true` — 보안 취약점 (XSS → RCE)
- `contextIsolation: false` — 동일 취약점
- Renderer 에서 `require('fs')`, `require('path')` 등 Node.js API 직접 호출
- `remote` 모듈 (`@electron/remote`) — deprecated, 사용 금지
- IPC 채널명 문자열 리터럴 (`ipcRenderer.invoke('user:get')`) — `IPC_CHANNELS` 상수 사용
- `localStorage` / `sessionStorage` 에 토큰 저장 — electron-store 암호화 또는 Main 메모리 (LESSON-027)
- `type="number"` — `type="text" inputMode="numeric"` (LESSON-006)
- 인라인 Tailwind 2개 이상 — CVA + index.style.ts (LESSON-STYLE-001)
- Main 프로세스에서 동기 IPC (`ipcMain.on` + `event.returnValue`) — 앱 블로킹

## 검증 명령

```bash
cd desktop
pnpm install
pnpm test
pnpm lint
pnpm exec tsc --noEmit
```
