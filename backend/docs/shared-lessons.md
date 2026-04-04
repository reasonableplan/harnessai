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
