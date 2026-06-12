# Electron — IPC 컨벤션

> Main↔Renderer 통신 코드 (핸들러, preload, 호출부) 작성 시 읽어라.

## 채널 정의

- 채널명: `domain:action` 형식 (`drawing:open`, `settings:get`) — `electron/ipc/channels.ts` 상수로만, 문자열 리터럴 직접 사용 금지
- 채널 추가 시 4곳 동시 갱신: channels.ts → Main 핸들러 → preload 노출 → `electron.d.ts` 타입

## 응답 봉투 — IpcResult

모든 `invoke` 응답은 공통 봉투로 감싼다. Main 핸들러는 **throw 금지** — 실패도 값으로 반환:

```ts
// shared/types/ipc.ts — Main + Renderer 공유
export type IpcResult<T> =
  | { ok: true; data: T }
  | { ok: false; code: string; message: string }
```

```ts
// electron/ipc/handlers/drawing.handler.ts
ipcMain.handle(IPC_CHANNELS.DRAWING_OPEN, async (_e, path: string): Promise<IpcResult<Drawing>> => {
  try {
    return { ok: true, data: await openDrawing(path) }
  } catch (err) {
    log.error('drawing:open failed', err)
    return { ok: false, code: 'DRAWING_001', message: '도면 파일을 열 수 없습니다' }
  }
})
```

- `message` 는 사용자 노출용 한국어, `code` 는 skeleton errors 섹션의 에러 코드 체계와 1:1
- Renderer 쪽도 throw 금지 — `ok` 분기로 처리

## Renderer 호출 — api 모듈 경유

컴포넌트/스토어에서 `window.electronAPI` 직접 호출 금지. 도메인별 api 모듈이 preload 노출 함수를 래핑한다:

```ts
// containers/drawing/api/drawing.api.ts
export const openDrawing = (path: string) => window.electronAPI.drawing.open(path)
```

- api 모듈은 타입만 보강하고 변환 로직 없음 — 얇게 유지
- 입력 검증은 Main 핸들러 책임 (Renderer 는 신뢰 경계 밖)

## 단방향 알림 (Main → Renderer)

- `webContents.send()` + `ipcRenderer.on()` — 채널명 역시 `IPC_CHANNELS` 상수
- preload 에서 구독 해제 함수를 반환: `onProgress: (cb) => { ipcRenderer.on(CH, cb); return () => ipcRenderer.removeListener(CH, cb) }`
- React 에서는 `useEffect` cleanup 으로 해제 — 리스너 누수 금지

## 금지 사항

- `nodeIntegration: true` / `contextIsolation: false`
- Renderer 에서 Node.js API (`fs`, `path`) 직접 호출 — Main 핸들러 경유
- 동기 IPC (`ipcMain.on` + `event.returnValue`) — 앱 블로킹
- 핸들러에서 raw Error 를 Renderer 로 전파 (Electron 이 메시지를 직렬화하며 스택 노출) — IpcResult 로 변환
