# CLAUDE.md — Agent Orchestration Project

## 핵심 원칙: 현업전문가 수준, 느려도 완벽하게

**코드 품질 기준: 현업 시니어 엔지니어가 프로덕션에 배포할 수 있는 수준.**
- 쓰레기 코드(dead code, 임시 핵, 의미 없는 추상화) 일절 금지
- 효율적이고 효과적인 코드 — 불필요한 연산, 중복, 과도한 할당 없이
- 모든 코드는 세밀하게 점검 — "대충 돌아가면 됨"은 이 프로젝트에서 허용하지 않음

속도보다 정확성. 코드를 한 줄 쓸 때마다 "이게 틀릴 수 있는 모든 경우"를 먼저 생각한다.
빠르게 만들고 나중에 고치는 방식은 이 프로젝트에서 금지한다.

---

## 코드 작성 규칙

### 1. 테스트 먼저, 코드 나중
- 새 함수/모듈 작성 시 **테스트를 먼저 작성**하고, 테스트가 실패하는 것을 확인한 후 구현
- 테스트 없는 코드는 완성이 아님
- mock 기반 테스트만으로는 부족 — 핵심 로직은 실제 동작을 검증하는 테스트 필요

### 2. 한 번에 완벽하게
- 수정할 때 관련된 **모든 파일**을 함께 수정 (하나 고치고 다른 곳 깨지는 일 방지)
- 인터페이스 변경 시: 타입 → 구현 → mock → 테스트 → 호출처 **전부** 한 번에
- 새 MESSAGE_TYPE 추가 시: types → publisher → subscriber → event-mapper → 테스트 전부

### 3. 외부 API 호출 체크리스트
모든 GitHub API / Claude API / DB 호출 시 반드시 확인:
- [ ] `withRetry()` 래핑 되어 있는가?
- [ ] 응답이 `null`/`undefined`일 수 있는가? → optional chaining + 가드
- [ ] GraphQL `node()` 쿼리 → `result.node?.` 필수
- [ ] 422 (이미 존재) 에러 → 정상 처리 (throw 아님)
- [ ] rate limit → `errors[].type === 'RATE_LIMITED'` 감지

### 4. DB/Board 분리 작업 순서
- **Board(외부) 먼저 → DB(내부) 나중** — Board 실패 시 DB는 원래 상태 유지
- 절대로 DB를 먼저 변경하고 Board를 나중에 변경하지 않음
- `updateTask`의 status 변경은 atomic WHERE (`WHERE status = :from`)

### 5. 비동기 안전성
- `subscribe()` 했으면 반드시 `drain()`에서 `unsubscribe()`
- `setTimeout`/`setInterval` → cleanup에서 `clearTimeout`/`clearInterval`
- `requestAnimationFrame` → cleanup에서 `cancelAnimationFrame`
- useEffect 안 async → `let cancelled = false` + cleanup에서 `cancelled = true`
- `Promise.all`은 독립적 DB 쿼리에 사용 금지 → `Promise.allSettled` 사용
- MessageBus handler 안에서 같은 타입 publish 금지 (무한 루프)

### 6. 타입 안전성
- `as` 캐스트 최소화 — 불가피할 때만, 사유 주석 필수
- `readonly` 필드를 `as Record<string, unknown>`으로 mutation 금지
- DB에 NOT NULL + DEFAULT 있는 필드 → TypeScript에서도 required
- WS/API payload → 알려진 필드만 destructure, raw spread 금지

### 7. 에러 처리
- `catch {}` (빈 catch) 금지 — 최소한 `log.error` 필수
- "존재 확인" 패턴의 catch → NOT_FOUND/404만 삼키고 나머지는 re-throw
- `addComment` 같은 부수효과 → try/catch non-fatal (메인 플로우 차단 금지)
- shutdown/cleanup 함수 → 멱등성 가드 (`if (shuttingDown) return`)
- server.listen() → `once('error', reject)` 필수

### 8. 보안
- CLI 인자에 토큰/시크릿 전달 금지 → 환경변수 또는 credential helper
- Claude 프롬프트에 사용자 입력 → XML 딜리미터 (`<task>`, `<review_feedback>`)
- HTTP 500 응답에 `err.message` 미포함

### 9. 환경/설정
- 환경변수 추가/변경 시 → config.ts + .env.example + MEMORY.md **3곳 동기화**
- Windows 호환성 — `process.kill(pid, 'SIGINT')` 대신 `process.emit('SIGINT')`
- 정규식에서 `\n` → `\r?\n` (CRLF 호환)

### 10. Canvas/React 대시보드
- 좌표 계산에 매직넘버 금지 → 상수 참조 (`CHAR_H + PADDING`, not `CHAR_H + 8`)
- useEffect deps에 state 넣고 같은 state를 set → 무한 루프 → ref로 분리
- 슬롯/인덱스 루프 → 항상 배열 길이 bounds check

---

## 코드 완료 전 자가 검증 체크리스트

코드를 "완료"라고 말하기 전에 반드시 확인:

```
[ ] 빌드 통과 (pnpm build)
[ ] 전체 테스트 통과 (pnpm test)
[ ] 린트 0 errors (pnpm lint)
[ ] 새 함수에 테스트 작성했는가?
[ ] 인터페이스 변경 시 mock/호출처 전부 업데이트했는가?
[ ] 외부 API 호출에 withRetry + null 가드 있는가?
[ ] DB/Board 작업 순서가 Board-first인가?
[ ] subscribe 했으면 drain에서 unsubscribe 하는가?
[ ] async cleanup (cancelled 플래그, clearTimeout 등) 있는가?
[ ] 환경변수 변경 시 .env.example 동기화했는가?
```

---

## 프로젝트 구조 요약

- **모노레포**: pnpm workspace, 8개 패키지
- **스택**: TypeScript, React+Vite, Express+WebSocket, PostgreSQL(Drizzle), Claude API
- **빌드**: `pnpm build` / **테스트**: `pnpm test` / **린트**: `pnpm lint`
- **설계 문서**: `docs/implementation-spec.md` (구현 시 PRIMARY REFERENCE)
- **교훈 기록**: `.claude/projects/.../memory/coding-standards.md` (40개 교훈)

### 패키지 구조
```
packages/
  core/           — 타입, DB, BaseAgent, MessageBus, StateStore, GitService, 리질리언스
  agent-git/      — Git 작업 (branch, commit, PR)
  agent-director/ — 계획, 디스패치, 리뷰
  agent-backend/  — 백엔드 코드 생성
  agent-frontend/ — 프론트엔드 코드 생성
  agent-docs/     — 문서 생성
  dashboard-client/ — React+Canvas 오피스 시각화
  dashboard-server/ — Express+WS 서버
  main/           — 부트스트랩, 팩토리, 어댑터
```

---

## 의사소통 스타일

- 한국어로 소통
- 간결하게 — 불필요한 설명 생략
- 작업 전 계획을 먼저 공유하고 확인 받기
- 확실하지 않으면 추측하지 말고 질문하기
