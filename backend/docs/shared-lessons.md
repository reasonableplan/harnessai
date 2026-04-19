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

---

## LESSON-018: 상수 정의 범위 vs 실제 사용 범위 불일치 (dead 상수)

**문제**: 상수 컬렉션(tuple/list/dict)을 정의했으나 소비 루프/조건의 범위와 불일치해
일부 요소가 **절대 실행되지 않음**. code-hijack 1차 E2E 에서 발견:
`_BACKOFF_SECONDS = (1.0, 2.0, 4.0)` 정의했으나 `max_retries = 2` 로 3번째 값 dead.

**규칙**:
- 상수 정의 길이 ≤ 실제 소비 범위
- 정의가 더 클 경우 **명시적 주석** (`# 확장 예정: rate-limit 전용 시 사용`) 필수
- 또는 소비 루프를 `for delay in _BACKOFF_SECONDS:` 처럼 컬렉션 전체를 돌도록 작성

```python
# ❌ dead: 3번째 값 절대 사용 안 됨
_BACKOFF_SECONDS = (1.0, 2.0, 4.0)
for i in range(2):  # max_retries = 2
    time.sleep(_BACKOFF_SECONDS[i])

# ✅ 일치
_BACKOFF_SECONDS = (1.0, 2.0)
for delay in _BACKOFF_SECONDS:
    time.sleep(delay)
```

**자동 검출**: `/ha-review` 의 ai-slop 훅에 정규식 패턴 포함. 튜플/리스트 정의 +
근접 `max_(retries|attempts)=N` 대비 길이 불일치 감지 (fragile — AST 분석 대체는 후속).

---

## LESSON-019: 외부 명령 stderr → 사용자 친화 메시지 번역

**문제**: 외부 명령어 (git, docker, kubectl, uv, pip, npm 등) 의 stderr 을
그대로 사용자에게 노출. `fatal: could not read Username for 'https://github.com'`
같은 jargon 이 CLI 출력에 섞여 사용자 혼란 유발.

**규칙**: subprocess 의 stderr 을 **카테고리별 안내 메시지로 번역**.
- 네트워크/권한/리소스/입력 오류 등 분류
- 원본 stderr 은 `--verbose` 플래그 또는 로그 파일 로만 노출
- `click.ClickException` 계층에 맞춰 exit code 설정

```python
# ❌ jargon 그대로 노출
if result.returncode != 0:
    raise FetchError(f"git clone 실패: {result.stderr}")

# ✅ 번역 + 원본은 로그로만
if result.returncode != 0:
    hint = _categorize_git_error(result.stderr)
    # hint 예: "네트워크 문제 — 인터넷 연결 확인" / "권한 문제 — 자격 증명 확인"
    logger.debug("git stderr: %s", result.stderr)  # --verbose 시 출력
    raise FetchError(f"git clone 실패: {hint}")
```

**적용 대상**: 모든 외부 subprocess (git / docker / kubectl / uv / pip / npm / pnpm / cargo 등).

---

## LESSON-020: 진행 표시 [N/M] 은 실제로 작동해야 — 껍데기 금지

**문제**: `[3/4] LLM 분석 중...` 을 출력하고 그 안에서 90% 시간을 보내면
사용자는 멈춘 줄 착각. 상위 단계만 찍고 **오래 걸리는 내부 작업은 진행도 없음**
= "껍데기 진행 표시". code-hijack 1차 E2E 에서 실제 발생.

**규칙**:
- **2초 이상 걸리는 단계는 내부에도 진행 표시 필수**
- 중첩 진행 (예: `[3/4] LLM 분석 (architecture 1/3)`) 또는 `tqdm` / `rich` 활용
- `[N/M]` 을 쓰면 **실제 N 번 갱신** — 찍고 바로 끝나는 단계는 `[N/M]` 쓰지 말 것
- 일관성 규칙: 시리즈면 전부 표시 또는 전부 생략

```python
# ❌ 껍데기 — 사용자는 10분간 아무 피드백 없음
click.echo("[3/4] LLM 분석 중...")
for cat in categories:
    await analyze(cat)  # 각각 30초

# ✅ 내부 진행도
click.echo(f"[3/4] LLM 분석 ({len(categories)} 카테고리)")
for i, cat in enumerate(categories, 1):
    click.echo(f"    ({i}/{len(categories)}) {cat}...", err=True)
    await analyze(cat)
```

**검출**: 주로 리뷰어 판단 (문맥 필요). 정규식으로는 `[N/M]` 사용 여부만 확인 가능.

---

## LESSON-021: 태스크 `done` = toolchain 전체 통과 (test + lint + **type**)

**문제**: ui-assistant 2차 E2E 중간 발견. backend 13개 + frontend 13개 태스크가 `done`
상태였으나 `/ha-verify` 를 한 번도 안 돌렸음. 실제로 돌려보니 **pyright 15 errors**
(SQLModel + ConfigDict 혼용, `.desc()` 타입 추론, `__tablename__` declared_attr)
+ **eslint 설정 누락** (v9 migration 안 됨) 발견.

단위 테스트 (pytest, vitest) 만 통과시키면 `done` 으로 mark 되는 흐름 때문.
타입 체크와 린트는 스킵됨 → 누적된 15개 타입 에러가 E2E 까지 숨어있음.

**규칙**:
- 태스크를 `done` 마킹 전에 프로파일의 **`toolchain.test + toolchain.lint + toolchain.type`
  전부** 강제 실행
- 실패 시 태스크는 `in_progress` 또는 `blocked` 유지
- 단위 테스트만 통과한 상태를 `done` 으로 부르지 말 것

**구현 위치**:
- `~/.claude/skills/ha-build/run.py::cmd_complete` 에서 mark-done 전 toolchain
  검증 추가 (현재는 pytest 만)
- 또는 `/ha-build` 스킬 본문에서 "완료 체크리스트" 로 명시

**연결**:
- 같은 정신: LESSON-018 (dead 상수) — 선언만 되고 실행 안 되는 것 금지
- 반대 패턴 주의: 타입 체크를 "nice to have" 로 분류하면 결국 프로젝트 끝에서 누적 폭발
