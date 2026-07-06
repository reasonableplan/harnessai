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
- skeleton `interface.http` 섹션에 명시된 상한 따라라

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

**규칙**: skeleton `persistence` 섹션에서 Integer auto-increment vs UUID 명시 후 모델 구현 방법까지 기술.

---

## LESSON-008: 디자인에서 버튼/액션 누락

**문제**: Designer가 데이터 표시 화면만 설계하고 "이슈 생성", "삭제" 같은 액션 버튼을 누락.
백엔드 API는 있는데 프론트에 UI가 없는 상황 발생.

**규칙**: Designer는 화면마다 가능한 **모든 사용자 액션**을 명시해야 함.
- 생성 버튼, 편집 버튼, 삭제 버튼, 상태 변경 드롭다운 등 전부 포함
- Reviewer는 skeleton `interface.http` 와 `view.screens` / `view.components` 를 대조해서 API는 있는데 UI 액션이 없는 경우 reject

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

**규칙**: skeleton `notes` 섹션 (테스트 전략 영역) 에 프론트엔드 테스트 전략 명시 필수.
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

**규칙**: skeleton `view.screens` / `view.components` 섹션의 디자인 가이드에 디자인 시스템 소스를 반드시 명시.
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

## LESSON-022: JWT access/refresh 토큰 반드시 구분 — type + ver claim 필수

**문제**: access token과 refresh token이 동일한 payload 구조(sub + exp)를 가지면,
refresh token을 Authorization 헤더에 Bearer로 넣어도 인증이 통과됨. 보안 결함.

**규칙**: 두 토큰에 반드시 `type` claim과 `ver` claim 포함.
- `get_current_user`: `type == "access"` AND `ver == user.token_version` 두 가지 모두 검증
- `decode_refresh_token`: `type == "refresh"` 검증

```python
# ✅ access token
payload = {"sub": str(user_id), "exp": expire, "type": "access", "ver": user.token_version}

# ✅ refresh token
payload = {"sub": str(user_id), "exp": expire, "type": "refresh", "ver": user.token_version}

# ✅ get_current_user 검증
if payload.get("type") != "access":
    raise TokenInvalidError
if payload.get("ver") != user.token_version:
    raise TokenInvalidError
```

---

## LESSON-023: logout은 서버에서 토큰 무효화 필수 — no-op 금지

**문제**: `async def logout(self) -> None: pass` 는 쿠키만 삭제. 탈취된 refresh/access
token은 만료 전까지 영원히 유효. 로그아웃이 실질적으로 동작하지 않음.

**규칙**: logout 시 `User.token_version`을 +1 증가시켜 커밋. 기존 발급 토큰 전체 즉시 무효화.
별도 revocation table 없이 stateless하게 구현 가능.

```python
# ✅ token_version 기반 무효화
async def logout(self, *, db: AsyncSession, user: User) -> None:
    user.token_version = (user.token_version or 0) + 1
    db.add(user)
    await db.commit()

# ❌ no-op 절대 금지
async def logout(self) -> None:
    pass
```

**User 모델**: `token_version: int = Field(default=0, nullable=False)` 컬럼 필수.

---

## LESSON-024: refresh 엔드포인트는 httponly 쿠키만 허용 — body fallback 금지

**문제**: `/api/auth/refresh`가 body의 `refresh_token`도 수락하면, httponly 쿠키의 보안
의미가 사라짐. XSS로 탈취한 refresh token을 body로 전송해 갱신 가능.

**규칙**: refresh endpoint는 Cookie만 허용. body fallback 코드 완전 제거.
프론트엔드는 `withCredentials: true`로 쿠키 자동 전송.

```python
# ✅ 쿠키만 허용
@router.post("/refresh")
async def refresh(
    refresh_token_cookie: Annotated[str | None, Cookie(alias="refresh_token")] = None,
) -> dict:
    if not refresh_token_cookie:
        raise TokenInvalidError
    ...

# ❌ body fallback 절대 금지
token = refresh_token_cookie or (body.refresh_token if body else None)
```

---

## LESSON-025: MAX()+1 시퀀스는 unique constraint + IntegrityError retry 필수

**문제**: `SELECT MAX(scene_number) + 1`로 번호를 배정하면, 동시 요청 2개가 같은 번호를
읽고 INSERT → duplicate key 에러 또는 데이터 손상. PostgreSQL에서 재현됨.

**규칙**: DB에 unique constraint를 반드시 걸고, IntegrityError 발생 시 최대 3회 재시도.

```python
# ✅ unique constraint + retry 패턴
from sqlalchemy.exc import IntegrityError

for attempt in range(3):
    max_result = await db.execute(select(func.max(Scene.scene_number)).where(...))
    scene_number = (max_result.scalar_one_or_none() or 0) + 1
    scene = Scene(scene_number=scene_number, ...)
    db.add(scene)
    try:
        await db.commit()
        break
    except IntegrityError:
        await db.rollback()
        if attempt == 2:
            raise ResourceConflictError("번호 충돌. 다시 시도해 주세요.")

# Migration에 반드시 포함
sa.UniqueConstraint("chapter_id", "scene_number", name="uq_scene_chapter_number")
```

---

## LESSON-026: SSE async generator는 try/finally로 cleanup 필수

**문제**: SSE 스트리밍 중 클라이언트가 연결을 끊으면 FastAPI가 `.aclose()`를 호출해
generator를 종료함. finally 블록이 없으면 generator 종료 후의 DB 저장 코드가 실행되지 않아
사용자 메시지는 커밋됐지만 assistant 응답이 영영 저장 안 되는 고아 메시지 발생.

**규칙**: async generator 내 DB 저장은 반드시 `finally` 블록에서 처리.

```python
# ✅ try/finally로 disconnect 대응
async def _generate() -> AsyncIterator[str]:
    try:
        async for chunk in await llm.stream(messages, ...):
            collected.append(chunk)
            yield f"data: {chunk}\n\n"
    except LLMError as exc:
        yield f"data: {json.dumps({'error': exc.message})}\n\n"
    except Exception as exc:
        logger.error("stream error: %s", exc)
    finally:
        full_content = "".join(collected)
        if full_content:
            db.add(AiConversation(role="assistant", content=full_content, ...))
            try:
                await db.commit()
            except Exception:
                logger.error("Failed to persist assistant message", exc_info=True)
                await db.rollback()
```

---

## LESSON-027: access token은 메모리만 — localStorage/sessionStorage 저장 금지

**문제**: Zustand persist나 localStorage.setItem으로 token을 저장하면 XSS 공격 시
스크립트 한 줄로 탈취 가능. `refreshToken`을 localStorage에 저장하면 httponly 쿠키
보안이 완전히 무력화됨.

**규칙**:
- `accessToken`: JS 모듈 변수(메모리)에만 보관. 새로고침 후 `/api/auth/refresh`로 복원.
- `refreshToken`: httponly 쿠키만. JS 접근 불가.
- Zustand `persist`의 `partialize`에서 token 계열 필드 전부 제외.

```typescript
// ✅ 메모리 변수로만 보관
let _accessToken: string | null = null
export function setAccessToken(token: string | null) { _accessToken = token }

// ✅ persist partialize — user 정보만 저장
partialize: (state) => ({ user: state.user })  // accessToken 제외

// ❌ 절대 금지
localStorage.setItem('accessToken', token)
localStorage.setItem('refreshToken', token)
```

---

## LESSON-028: in-memory rate limiter = 싱글워커 전제 — 멀티워커 시 무력화

**문제**: module-level dict로 구현된 rate limiter는 프로세스 메모리에만 존재.
Gunicorn 멀티워커 배포 시 워커마다 별도 dict → 실제 limit이 `워커 수 × 설정값`으로 증가.

**규칙**: 싱글워커 배포면 코드 주석으로 전제 명시. 멀티워커 필요 시 Redis 기반으로 교체.

```python
# 싱글워커(uvicorn 단일 프로세스) 전제 — Gunicorn 멀티워커 시 Redis로 교체 필요
_rate_limit_store: dict[int, list[float]] = defaultdict(list)
```

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

---

## LESSON-STYLE-001: 인라인 스타일 분리 — 별도 스타일 시스템 사용

**문제**: 프레임워크별 스타일 시스템이 있어도 인라인 스타일을 누적하면 동일 컴포넌트의
변형(state/theme/variant) 추적이 어려워지고 디자인 시스템 통합이 깨진다.

**규칙** — profile별 한도 초과 시 별도 추출:
- **react-vite / nextjs / electron**: 인라인 Tailwind 2개 이상 → CVA + `index.style.ts`
- **react-native-expo**: 인라인 NativeWind className 또는 인라인 StyleSheet 2개 이상 → 별도 StyleSheet 추출
- **flutter**: 인라인 BoxDecoration 2개 이상 → ThemeData / `Theme.of(context)`
- **android-kotlin**: 인라인 Modifier 체인 5개 이상 → MaterialTheme + 추출 Modifier
- **ios-swift**: 인라인 modifier 체인 5개 이상 → ViewModifier 추출

**이유**: 별도 추출 시 재사용 + 변형(variant) 관리 + 디자인 토큰 일관성 확보. 인라인이
누적되면 동일 컴포넌트의 5가지 상태가 5개 파일에 분산되어 디자인 변경 시 누락 발생.

**구현 위치**:
- 각 profile 의 "금지 사항" 섹션에 구체 위반/권장 패턴 명시
- ha-review 의 ai-slop + style audit 에서 인라인 누적 패턴 탐지 (휴리스틱)

**연결**:
- 같은 정신: LESSON-014 (Designer 가 디자인 시스템 소스를 직접 정의하면 품질 미보장)
  — 시스템화된 추출 패턴이 디자인 토큰 일관성의 기반

---

## LESSON-029: pyright 가변 tuple 빈 체크는 len() 내로잉만 인정

**문제**: `tuple[str, ...]` 의 빈 여부를 `if not parts:` truthiness 로 가드하면 pyright 가 빈 tuple 분기를 제거하지 못해 `parts[-1]` 에 'Index -1 out of range for tuple[()]' 오류 지속.

**규칙**: 가변 길이 tuple (`Path.parts` 등) 의 빈 가드는 `if len(parts) == 0: continue` 처럼 **len() 비교**로 작성 — pyright 의 tuple 길이 내로잉은 len() 체크에서만 동작한다.

**근거**: code-hijack Phase 3 ha-verify — negative_space.py:188, truthiness 가드로 1차 수정 실패 → len()==0 으로 해소 (2026-06-11, 사용자 promotion 승인).

## LESSON-030: 보안 훅이 .md 문서 diff 산문을 코드로 오인 (eval/print/import FP)

**문제**: command-guard/code-quality/dependency-check 가 diff 의 파일 종류를 구분하지 않아 마크다운 문서가 diff 에 포함되면 산문·인라인 예시를 코드로 오인한다. code-hijack 에서 3회 반복: (1) harness-plan.md rationale 의 'external eval (matching...' 문구 → eval() BLOCK 3건, (2) SKILL.md 인라인 스크립트 예시 print → WARN, (3) SKILL.md 예시 import hijack/tomllib → dependency WARN 다발. FP 홍수가 진짜 finding 을 묻는다

**규칙**: 보안 훅 입력에서 .md/.rst/.txt 문서 diff 는 command-guard·code-quality·dependency-check 대상에서 제외하거나 별도 severity(INFO) 로 강등. 코드 펜스 블록만 선택 스캔하는 것도 대안. 리뷰어는 BLOCK 의 snippet 출처 파일 확장자를 fp-check 1차 기준으로 사용

**근거**: code-hijack 2026-06-11 ha-review prepare: BLOCK 3 (harness-plan.md), WARN 16 중 16 FP (SKILL.md). 2026-06-11 직전 리뷰도 WARN 28 중 27 FP 동일 원인 (2026-06-11, 사용자 promotion 승인 — `strip_doc_files_from_diff` + `detect_local_packages` + stdlib 허용으로 구현됨).

## (promoted 2026-06-30 — 아래 LESSON-031~037 사용자 promotion 완료)







## LESSON-037: LLM 출력 검증: 실재 심볼에 대한 거짓 부정주장도 탐지

**문제**: 코드 설명 LLM이 AST에 실재하는 함수/클래스를 '존재하지 않는다/정의되지 않았다'고 거짓 단언할 수 있다(약한 모델일수록). 발명된 심볼만 잡는 환각가드(find_hallucinations)는 이걸 못 잡는다 — 심볼이 known이라 통과. 결과: 명백히 틀린 설명에 경고 플래그 0, bottom-up으로 의존 파일에 전파.

**규칙**: 환각 검증을 2축으로: (1)발명된 심볼 언급(known셋 밖) (2)실재 심볼에 대한 거짓 부정주장(known 심볼+존재/정의 부정문구 인접). 후자는 부정패턴을 '존재하지 않/정의되지 않/does not exist/not defined'로 좁히고 '없음/없이/없습니다'(=기능부재·조건 서술, 정상)는 제외해 FP 최소화. 프롬프트도 'AST 심볼은 실재함, 없다고 말하지 말 것'으로 강화.

**근거**: code-mate find_false_negations(guard.py). 전체점검 실제 Ollama explain서 qwen2.5-coder:7b가 def add를 '존재하지 않습니다' 환각한 사례 실증.

---
## LESSON-036: 다언어 파이프라인: 언어 특정 도구는 파일타입으로 게이트

**문제**: 다언어 파일을 처리하는 파이프라인에서 언어 특정 정적분석 도구(ruff=Python, eslint=JS 등)를 파일 타입 구분 없이 모든 파일에 돌리면, 그 도구가 다른 언어 파일을 자기 언어로 파싱해 가짜 결과(예: ruff가 .ts를 파이썬으로 파싱해 invalid-syntax 46개)를 생성하고 산출물(사이드카/리포트)을 오염시킨다. 유닛테스트가 그 도구 호출을 mock하면 verify가 green이라 못 잡는다.

**규칙**: 언어 특정 외부 도구는 호출 전 파일 확장자/타입으로 게이트: if path.suffix=='.py': run_ruff(path). 도구가 자기 언어 외 입력에 빈 결과를 준다고 가정하지 말 것(실제로는 파싱오류를 뱉을 수 있음). mock 테스트 외에 실제 도구를 비-자기-언어 파일에 1회 돌려보는 스모크로 검증.

**근거**: code-mate T-014: pipeline이 모든 파일에 run_ruff 호출 → .ts 사이드카가 파이썬 invalid-syntax로 오염. 점검 스모크로 발견, .py 게이트+회귀테스트로 수정.

---
## LESSON-035: LLM 출력은 결정론적 사실셋과 대조해 환각 탐지(비파괴 annotate)

**문제**: LLM이 코드/도메인을 설명할 때 존재하지 않는 심볼·API를 그럴듯하게 지어냄(환각). 사용자가 틀린 설명을 사실로 학습하면 안 하느니만 못함. 그러나 자연어 전체를 검사하면 일반 단어가 오검출돼 FP 폭발.

**규칙**: LLM에 코드 참조를 인라인 백틱으로 감싸라 지시 → 출력에서 백틱 토큰만 추출(코드펜스 제외) → 결정론적 known셋(AST 추출 심볼 + 직접의존 + builtin/stdlib allowlist)과 대조 → 밖의 토큰은 '환각 의심'으로 원본 보존한 채 append annotate(파괴/재생성 아님). 검사 표면을 백틱+식별자형으로 좁혀 FP 최소화. dotted 접근(a.b)은 모호하니 제외.

**근거**: code-mate T-012 core/guard.py find_hallucinations — explain 사이드카에 환각 가드. eng리뷰 finding#3(틀린 설명 방지).

---
## LESSON-034: 파생 경로/캐시키는 단일 함수로 — 조회처·기록처 분리 금지

**문제**: 사이드카(.explain.md) 경로를 pipeline(캐시 조회)은 with_name+stem, write_sidecar(기록)는 이중 with_suffix로 각각 계산 → multi-dot 파일명(foo.test.py)에서 두 경로가 달라져(foo.test.explain.md vs foo.explain.md) 캐시가 영원히 silent miss. 단일 dot는 우연히 일치해 테스트/일반사용서 안 드러남.

**규칙**: 캐시키·파생 경로처럼 '조회'와 '기록'이 반드시 일치해야 하는 값은 단일 pure 함수(single source of truth)로 만들어 양쪽이 import해 쓴다. .py→사이드카는 path.with_suffix('.explain.md') 한 줄(마지막 suffix만 치환, stem 보존).

**근거**: code-mate: pipeline._sidecar_path vs adapters.write_sidecar 불일치. core/sidecar.py sidecar_path()로 통일 + 회귀테스트 추가.

---
## LESSON-033: Windows cp949 콘솔: CLI 진입점에서 stdout/stderr UTF-8 강제

**문제**: 한국어 Windows 기본 콘솔(cp949)은 em-dash(—,—) 등 non-cp949 문자 출력 시 UnicodeEncodeError로 크래시. CLI 에러 메시지/진행표시에 그런 문자가 있으면 exit code/친절메시지 계약이 깨짐. typer CliRunner 테스트는 utf-8 인메모리 버퍼라 green이어서 못 잡음(테스트 통과하나 실기동 크래시).

**규칙**: CLI 진입점에서 sys.stdout/stderr.reconfigure(encoding='utf-8', errors='replace') 를 출력 전에 호출(있을 때만). rich Console은 sys.stdout 동적 참조라 런타임 reconfigure도 반영됨. 또는 메시지에서 non-ASCII 구두점 회피. 한국어/Windows 타깃이면 verify에 인코딩 스모크 포함.

**근거**: code-mate cli.py — Ollama 미실행 시 친절메시지의 em-dash가 cp949 크래시(exit 1, 기대 3). _force_utf8_io()로 수정.

---
## LESSON-032: TS project-references 루트에 bare tsc -p 는 0파일 vacuous pass — tsc -b 필수

**문제**: tsconfig.json 이 'files: [] + references' (project references) 구조면 'tsc --noEmit -p tsconfig.json' 은 0개 파일만 검사하고 EXIT 0 으로 통과한다. 타입 게이트가 실제 소스를 전혀 안 보고 'tsc 0 errors' 를 보고 → 실제 타입 RED 가 built/verified/reviewed 까지 통과 (예: 라이브러리 실타입 불일치 6건 + MTEXT height 런타임버그).

**규칙**: project-references 루트(files:[])에는 build mode 를 써야 leaf config 를 따라간다: 'tsc -b --noEmit' (또는 각 leaf 를 직접: 'tsc --noEmit -p tsconfig.app.json && tsc --noEmit -p tsconfig.node.json'). 게이트가 'tsc 0' 인데 검사 파일 수가 0 이면 vacuous 의심. package.json 의 typecheck 스크립트가 있으면 그걸 위임.

**근거**: Mendline(electron) — harness-issues #24. 커밋된 프로파일 toolchain.type 이 bare 'tsc --noEmit' 라 03:06/03:16 ha-verify 가 vacuous pass. tsc -b 로 바꾸니 6건 RED 노출.

---
## LESSON-031: Electron dev/prod 분기는 app.isPackaged — NODE_ENV 금지

**문제**: main 프로세스에서 isDev=process.env.NODE_ENV!=='production' 으로 분기하면 패키징 앱(NSIS/dmg)은 NODE_ENV 가 설정돼 있지 않아 dev 모드로 폴백 — 존재하지 않는 dev 서버 URL 로드(빈 창) + devTools 자동 오픈. E2E 가 launch env 에 NODE_ENV=production 을 주입하면 이 결함이 전 게이트(unit/E2E/smoke)에서 가려짐

**규칙**: Electron main 의 dev/prod 분기는 const isDev = !app.isPackaged 사용. process.env.NODE_ENV 기반 분기는 패키징 산출물에서 fail-open. E2E launch env 에 NODE_ENV 주입 시 prod 위장임을 인지하고 별도 packaged-app smoke 권장

**근거**: sosel /ha-review: desktop/electron/main.ts:10 — E2E(playwright _electron)는 env 주입으로 통과했으나 실제 NSIS 산출물은 빈 창

---
## LESSON-038: React Native(Hermes) 한글/로케일 정렬은 코드포인트 비교 — localeCompare(locale) 금지

**문제**: RN 기본 엔진 Hermes 는 ECMA-402 Intl 을 **부분(subset)만** 지원한다(특히 iOS Hermes 의 Intl 은 JS 구현·제한적 데이터). `arr.sort((a,b)=>a.localeCompare(b,'ko'))` 같은 로케일 정렬이 디바이스/플랫폼에 따라 한국어 가나다순을 **불안정/오정렬**하거나 무시될 수 있다. 단위 테스트(node)는 풀 ICU 라 green 이어도 실기기(iOS Hermes)서 깨질 수 있어 안 잡힌다.

**규칙**: 한국어(완성형 한글) 정렬은 **코드포인트 직접 비교**(`a<b ? -1 : a>b ? 1 : 0`)로 한다. 유니코드 Hangul Syllables 블록(U+AC00~U+D7A3, 11,172자)이 **한국 표준(KS X 1026-1) 가나다 순서로 배열**돼 있어 코드포인트 정렬 = 사용자가 기대하는 가나다순. Intl/Collator 불필요. 로케일 정렬이 꼭 필요하면 `Intl.Collator` 지원을 디바이스에서 실측하거나 Hermes 의 `intl` variant(풀 ICU, 바이너리 증가)를 명시 활성화할 것. 정렬 테스트는 가·나·다·까 등 한글 케이스로 작성.

**근거**: noraebang(react-native-expo, 첫 모바일 빌드) /ha-design 점검 — sortSongs 가 `localeCompare('ko')` 사용. [verified] Hermes Intl subset(reactnative.dev/docs/hermes) + Hangul Syllables=한국표준순(unicode.org L2/L2017/17078). 코드포인트 비교로 정정(2026-06-30).

---
## LESSON-039: expo-file-system 함수형 read/writeAsStringAsync 는 SDK 54+ deprecated — 새 File API 또는 /legacy

**문제**: `expo-file-system` 의 함수형 API(`FileSystem.readAsStringAsync`/`writeAsStringAsync`/`copyAsync` 등)가 **SDK 54 에서 deprecated** 되고 새 `File`/`Directory` 클래스 API 로 교체됐다. SDK 54 stable 은 함수형을 호출 시 deprecation 에러를 던지고, beta 에선 아예 undefined. 또 jest-expo 가 새 File API 목킹에 이슈(expo/expo#39922)가 있어, 옛 패턴으로 작성하면 런타임 에러 또는 테스트 깨짐.

**규칙**: 파일 IO 는 **새 `File`/`Directory` 클래스 API**(`new File(uri).write(str)` / `.text()`) **또는** `import * as FS from 'expo-file-system/legacy'` 중 하나로 프로젝트 전체를 일관되게. **Expo SDK 버전을 package.json 에 고정**(API 동작이 SDK 의존). 테스트는 expo-file-system/expo-sharing/expo-document-picker 를 jest.mock 으로 스텁. document-picker 결과는 `if (result.canceled) return` 후 `result.assets[0].uri` 사용(구버전 `result.type==='success'` 아님).

**근거**: noraebang(react-native-expo) /ha-design 점검 — T-004 백업 IO 가 `FileSystem.readAsStringAsync`/`writeAsStringAsync` 사용. [verified] Expo FileSystem(legacy) docs + expo/expo#39858/#39922. 새 File API/legacy + SDK 핀으로 정정(2026-06-30).

---

## LESSON-040: 리버스 프록시는 요청·응답 양방향 hop-by-hop 헤더 필터 필요

**문제**: httpx/requests 로 리버스 프록시 구현 시 응답 헤더만 필터하고 들어온 요청 헤더(Content-Length/Connection/Transfer-Encoding/Accept-Encoding)를 그대로 업스트림에 전달하면, 클라이언트가 content 로부터 자체 프레이밍을 재계산하면서 원본 Content-Length 와 충돌해 'bad Content-Length' 로 전 요청이 실패한다. httpx.request 를 통째로 mock 한 단위 테스트는 실제 전송 프레이밍을 검증하지 못해 이 버그를 은폐한다(baker T-021: 모든 정상 타깃이 502, ha-smoke 실기동에서만 발견).

**규칙**: 프록시는 요청과 응답 양쪽에서 hop-by-hop/프레이밍 헤더를 제거한다: 요청측 {host,content-length,connection,keep-alive,transfer-encoding,upgrade,te,trailers,accept-encoding}, 응답측 {connection,keep-alive,transfer-encoding,content-length,x-frame-options,content-security-policy}. accept-encoding 제거로 클라이언트가 디코딩 가능한 인코딩 재협상. 테스트는 httpx 를 통째 mock 하지 말고 최소 1개는 실제 로컬 서버 왕복(또는 respx 로 전송 헤더 assert)으로 프레이밍 검증.

**근거**: baker backend/io_/preview_proxy.py — 응답 헤더만 _STRIPPED_RESPONSE_HEADERS 로 걸러 요청측 누락. test_preview_proxy.py 전부 httpx.request mock 이라 통과. ha-smoke url probe 로 실기동 502 포착.

---

## Pending Lessons (자동 추출 — 사용자 promotion 대기)

> 자동 추출된 LESSON. 사용자 검토 후 main 섹션으로 promote (auto_extracted 마커 제거) 또는 거부 (블록 삭제).

## LESSON-041: command-guard FP: SQLite 드라이버 .exec() + 테스트 DROP TABLE (mobile/SQLite)
<!-- auto_extracted: true / promotion_pending: true / extracted_at: 2026-07-06 -->

**문제**: react-native-expo + expo-sqlite/drizzle 프로젝트에서 command-guard 훅이 DB 드라이버의 .exec() 메서드(begin/commit/rollback/PRAGMA/상수 DDL)와 테스트 파일의 DROP TABLE(에러경로 시뮬)을 코드 인젝션/데이터파괴 BLOCK 으로 오탐. 백엔드 shell exec()/사용자입력 SQL 기준 룰이 SQLite 클라이언트 API 에 그대로 적용돼 발생.

**규칙**: command-guard 는 (1) __tests__/ 경로의 상수 SQL(테스트 픽스처·에러 시뮬)은 제외하고, (2) SQLite 드라이버 .exec()/.execAsync() 는 인자가 문자열 리터럴/상수면 통과, 사용자 입력이 문자열 concat/템플릿 보간될 때만 BLOCK 하도록 스코프. 판정 전 fp-check 로 프로덕션 도달성 확인.

**근거**: workout-app /ha-review: 9 BLOCK 전부 FP (logs/routines store test 의 DROP TABLE 2건 + testSqliteDb.ts 의 .exec 7건). 프로덕션 client.ts 는 drizzle/expo-sqlite API 만 사용.

---
