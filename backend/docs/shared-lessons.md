# Shared Lessons

과거 프로젝트에서 실제로 발생한 실수 모음. 모든 에이전트가 이 패턴을 반복하지 않는다.

---

## LESSON-001: Query params에 camelCase 사용 금지

**문제**: FastAPI에서 `alias_generator=to_camel`은 request body(JSON)에만 적용됨.
Query params는 URL 파라미터라 alias 변환이 안 됨.
프론트에서 `?projectId=1`로 보내면 서버가 무시 → 필터가 조용히 동작하지 않음.

**규칙**: FastAPI 엔드포인트의 Query params는 반드시 **snake_case**로 정의.

```python
# ✅
@router.get("/issues")
async def list_issues(project_id: int, sprint_id: int | None = None): ...

# ❌ camelCase Query param — 동작 안 함
async def list_issues(projectId: int): ...
```

---

## LESSON-002: limit 상한을 화면 요구사항 기준으로

**문제**: 기본 `le=100`으로 설정했다가 백로그/보드 화면에서 이슈가 잘려서 표시됨.

**규칙**:
- 보드/백로그 = `le=500`
- 단순 목록 = `le=50`
- skeleton 섹션 7에 명시된 상한 따라라

---

## LESSON-003: updated_at 자동 갱신

**문제**: `DEFAULT now()`는 INSERT 시에만 동작. UPDATE 시 자동 갱신 안 됨.

**규칙**: `onupdate=func.now()` 명시 또는 서비스에서 명시적 갱신.

```python
# ✅
updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

---

## LESSON-004: timezone-naive TIMESTAMP 금지

**문제**: timezone 정보 없는 TIMESTAMP는 서버 환경에 따라 시간대가 달라져서 데이터 불일치 발생.

**규칙**: 모든 datetime 컬럼은 `DateTime(timezone=True)` (TIMESTAMPTZ).

---

## LESSON-005: URL params가 source of truth

**문제**: `selectedProjectId`를 Zustand store에만 저장 → 새로고침 시 null → 빈 화면.

**규칙**: 현재 프로젝트/이슈 ID는 `useParams()`로 읽어라. store는 폴백만.

```typescript
// ✅
const { projectId: paramId } = useParams<{ projectId?: string }>()
const storeId = useAppStore(s => s.selectedProjectId)
const projectId = paramId ? Number(paramId) : storeId
```

---

## LESSON-006: input type="number" CJK 환경 금지

**문제**: `<input type="number">`는 한글(CJK) IME와 충돌 — 입력값이 사라지거나 이상하게 처리됨.

**규칙**: `type="text" inputMode="numeric"` 또는 선택 UI(Select, Stepper) 사용.

---

## LESSON-007: ID 타입을 명시하라

**문제**: SQLModel/SQLAlchemy 기본값이 Integer인지 UUID인지 불명확해서 프론트-백 타입 불일치 발생.

**규칙**: skeleton 섹션 6에서 Integer auto-increment vs UUID 명시 후 모델 구현 방법까지 기술.

---

## LESSON-008: 디자인에서 버튼/액션 누락

**문제**: Designer가 데이터 표시 화면만 설계하고 "이슈 생성", "삭제" 같은 액션 버튼을 누락.
백엔드 API는 있는데 프론트에 UI가 없는 상황 발생.

**규칙**: Designer는 화면마다 가능한 **모든 사용자 액션**을 명시해야 함.
- 생성 버튼, 편집 버튼, 삭제 버튼, 상태 변경 드롭다운 등 전부 포함
- Reviewer는 skeleton 섹션 7 API와 섹션 8 UI를 대조해서 API는 있는데 UI 액션이 없는 경우 reject

---

## LESSON-009: 컴포넌트에서 직접 API 호출 금지

**문제**: 컴포넌트에서 `axios.get()`을 직접 호출 → 로딩/에러 상태 분산, 캐시 없음, 테스트 어려움.

**규칙**: 모든 API 호출은 Zustand store action 안에서만. 컴포넌트는 store를 구독만 한다.

---

## LESSON-010: 에러 처리 형식 통일

**문제**: 일부 엔드포인트는 `{"detail": "..."}`, 일부는 `{"error": "..."}` — 프론트에서 파싱 혼란.

**규칙**: 모든 에러 응답은 `{"error": "...", "code": "ERROR_CODE", "details": {}}` 형식 통일.
`init_exception_handlers(app)`으로 전역 등록.

---

## LESSON-011: Tailwind v4 — @layer 밖의 CSS가 유틸리티를 덮어씀

**문제**: `tokens.css`에 `* { margin: 0 }` 같은 리셋을 `@layer` 밖에 두면,
Tailwind v4의 `@layer utilities` 클래스보다 cascade 우선순위가 높아짐.
`mx-auto`, `px-4` 등 마진/패딩 유틸리티가 무시됨 → 레이아웃 깨짐.

**규칙**: `@import "tailwindcss"` 이후 커스텀 CSS 리셋/베이스 스타일은 반드시 `@layer base {}` 안에 작성.

```css
/* ✅ */
@import "tailwindcss";
@layer base {
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg-base); }
}

/* ❌ @layer 밖 — mx-auto 등 유틸리티 무력화 */
@import "tailwindcss";
* { margin: 0; padding: 0; }
```

---

## LESSON-012: 백엔드 서버 실행 명령어 미명시

**문제**: `main.py`에 `if __name__ == "__main__"` 블록이 없으면 `python -m main`이 안 됨.
skeleton에 실행 명령을 명시하지 않으면 개발자가 명령을 직접 찾아야 함.

**규칙**: skeleton 및 README에 서버 실행 명령어 반드시 명시. Backend Coder는 `main.py`에 uvicorn 블록 추가.

```python
# ✅ main.py 하단에 필수 추가
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
```

---

## LESSON-013: 프론트엔드 테스트 전략 사전 미정의

**문제**: task breakdown에 프론트엔드 테스트 태스크가 없었고 화이트리스트에 vitest가 없었음.
프론트엔드 테스트 0개로 완료 → 시각적 회귀 및 로직 버그 자동 감지 불가.

**규칙**: skeleton 섹션 11(테스트)에서 프론트엔드 테스트 전략 명시 필수.
- 화이트리스트에 `vitest`, `@testing-library/react` 포함
- 핵심 비즈니스 로직(계산, 상태 전이)은 단위 테스트 필수
- Orchestrator는 프론트엔드 테스트 태스크를 task breakdown에 포함

---

## LESSON-015: React Native — 비동기 재시작 루프에 동시 진입 방지 플래그 필수

**문제**: STT 세션 재시작 같은 루프에서 타이머와 에러 이벤트가 동시에 트리거되면
`_restartSession()`이 중복 진입 → 고아 프로세스 생성.

**규칙**: 재진입 가능한 비동기 루프에는 반드시 모듈 레벨 boolean 플래그로 가드.

```typescript
let _isRestarting = false

async function _restartSession(): Promise<void> {
  if (_isRestarting) return   // ← 이중 진입 방지
  _isRestarting = true
  try {
    await stopStt()
    // stopAudio가 호출됐으면 bail out
    const { status } = store.getState()
    if (status === 'idle' || status === 'failed') return
    await startStt()
  } finally {
    _isRestarting = false    // ← 반드시 finally에서 해제
  }
}
```

---

## LESSON-016: React Native — await 후 stale reference 가드

**문제**: `await` 이후 store 상태가 바뀌어 있을 수 있음.
`await Promise.allSettled([speakerId, saveClip])` 후 다른 게임의 detection이 추가되는 버그.

**규칙**: await 이후 참조하는 객체가 "내가 시작할 때의 그것"인지 반드시 재확인.

```typescript
const { currentGame } = store.getState()  // await 전 snapshot
const [speakerResult, clipResult] = await Promise.allSettled([...])

// await 후 — 게임이 바뀌었을 수 있음
const { currentGame: gameAfterAwait } = store.getState()
if (!gameAfterAwait || gameAfterAwait.id !== currentGame.id) return  // ← 폐기
```

---

## LESSON-017: React Native — float 비교 대신 반올림 정수 비교

**문제**: `similarity=0.845`를 `Math.round(0.845 * 100) = 85`로 변환 후
`0.845 >= 0.85` 비교 → false. UI에는 confidence=85 표시되는데 confirmedBy=null.

**규칙**: float 임계값 비교는 표시값과 같은 단위(정수)로 변환 후 비교.

```typescript
const confidence = Math.round(similarity * 100)  // 85

// ❌ float 비교 — 표시값과 불일치 가능
confirmedBy: similarity >= AUTO_CONFIRM_THRESHOLD ? 'auto' : null

// ✅ 정수 비교 — confidence 표시값과 항상 일치
confirmedBy: confidence >= Math.round(AUTO_CONFIRM_THRESHOLD * 100) ? 'auto' : null
```

---

## LESSON-014: Designer가 디자인 시스템 소스를 직접 정의하면 품질 미보장

**문제**: Designer가 색상/간격을 처음부터 직접 정의하면 검증된 시각적 품질 보장 불가.
"기능은 되지만 디자인은 밋밋한" 수준에 머무름.

**규칙**: skeleton 섹션 8 디자인 가이드에 디자인 시스템 소스를 반드시 명시.
- `shadcn/ui 기본 테마 사용` (권장 — 접근성 검증됨)
- 커스텀 시: Mobbin/Dribbble 레퍼런스 URL 첨부 필수
- Designer가 색상을 직접 정의하는 경우 Reviewer가 레퍼런스 없으면 reject
