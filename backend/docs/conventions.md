# Conventions & Golden Principles

모든 에이전트가 따르는 개발 원칙 + 코딩 규칙.

---

## Part 1. Golden Principles — 개발 원칙

골든 원칙 위반 = 즉시 reject 사유.

### 1. Surgical Changes — 요청한 것만 변경
요청받은 범위만 수정한다. 관련 없는 파일, 함수, 스타일 "개선" 금지.

### 2. Contract First — skeleton이 법이다
skeleton에 없는 API/테이블/화면 추가 금지. "더 좋을 것 같아서"는 사유가 안 됨.

### 3. Evidence-Based Completion — 증거 없으면 완료 아니다
완료 전 반드시: 테스트 통과 + 린트 0 errors + 타입 체크 통과.

### 4. Read Before Write — 쓰기 전에 읽어라
기존 파일 읽고 → 패턴 파악 → 참조 파일 확인 → 그 다음 작성.

### 5. One Change, One PR — 태스크 하나 = PR 하나
PR이 너무 크면 태스크 분리를 Orchestrator에 요청.

### 6. Fail Fast — 빠르게 실패를 보고해라
같은 에러 3회 → 상위 에이전트에 보고. 추측으로 계속 시도 금지.

### 7. No Speculation — 추측 금지
불확실하면 추측하지 말고 보고한다. TODO/임시 코드로 PR 생성 금지.

### 8. Preserve Style — 기존 스타일을 따라라
참조 파일의 naming, structure, pattern을 그대로 따른다.

### 9. Security by Default — 기본이 보안이다
하드코딩 시크릿 절대 금지 / raw SQL 금지 / 사용자 입력 항상 검증.

### 10. Test the Behavior, Not the Mock
핵심 비즈니스 로직은 mock만으로 부족. 실제 동작 검증 필수.

### 11. Explicit Over Implicit — 명시적으로 작성해라
매직 넘버 금지 / 타입 힌트 필수 / 변수명이 의도를 설명해야 함.

### 12. Log, Don't Swallow — 에러를 삼키지 마라
빈 `except:` / `catch {}` 절대 금지. 최소 `logger.error()` 필수.

---

## Part 2. 네이밍 규칙

| 위치 | 규칙 | 예시 |
|------|------|------|
| Python 내부 변수/함수 | snake_case | `user_id`, `get_issues()` |
| Python 클래스 | PascalCase | `IssueService`, `ProjectModel` |
| API 응답 JSON | camelCase | `{"projectId": 1, "createdAt": "..."}` |
| API Query params | snake_case | `?project_id=1&sprint_id=2` |
| TypeScript 변수/함수 | camelCase | `projectId`, `fetchIssues()` |
| TypeScript 컴포넌트 | PascalCase | `IssueCard`, `ProjectBoard` |
| TypeScript 파일 (컴포넌트) | PascalCase | `IssueCard.tsx` |
| TypeScript 파일 (유틸/API) | camelCase + 용도 suffix | `issues.api.ts`, `useProject.ts` |
| CSS 클래스 | Tailwind 유틸리티 우선, CVA 변형 | — |

---

## Part 3. 백엔드 규칙 (Python/FastAPI)

### 프로젝트 구조
```
backend/
  app/
    models/          # SQLAlchemy Column 스타일 모델
    schemas/         # Pydantic 요청/응답 스키마
    routers/         # FastAPI 라우터 (엔드포인트만, 로직 없음)
    services/        # 비즈니스 로직 (서비스 클래스)
    exceptions/      # CustomException 계층
      base.py        # BaseCustomException
      도메인.py       # 도메인별 예외
      handlers.py    # init_exception_handlers(app)
    core/
      database.py    # DB 엔진, SessionLocal
      config.py      # 환경변수 설정
```

### 모델 패턴 (SQLAlchemy Column 스타일)
```python
class Issue(Base):
    __tablename__ = "issues"
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
```

### 서비스 패턴 (sync Session)
```python
class IssueService:
    def create(self, db: Session, data: IssueCreate) -> Issue:
        issue = Issue(**data.model_dump())
        db.add(issue)
        db.commit()
        db.refresh(issue)
        return issue

issue_service = IssueService()  # 싱글턴
```

### 응답 형식
```python
class BaseResponse(BaseModel):
    code: int
    message: str
    data: Any
    status: str  # "success" | "error"
```

### 에러 응답 형식
```json
{ "error": "에러 메시지", "code": "ERROR_CODE", "details": {} }
```

### Pydantic 설정
```python
model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
```
> Query params는 alias_generator 미적용 — snake_case로 정의 필수

### 날짜/시간
- 모든 datetime: `DateTime(timezone=True)` (TIMESTAMPTZ)
- API 응답: ISO 8601 (`2026-04-01T09:00:00Z`)

### 페이지네이션
```python
class PaginatedResponse(BaseModel):
    items: list[T]
    total: int
    page: int
    limit: int
```
- 보드/백로그: `limit` 상한 500 / 단순 목록: `limit` 상한 50

---

## Part 4. 프론트엔드 규칙 (TypeScript/React)

### 프로젝트 구조
```
src/
  containers/feature/
    components/       # 순수 UI 컴포넌트
    store/            # Zustand store (per-feature)
    feature.api.ts    # API 함수 + 타입
    FeaturePage.tsx   # 페이지 진입점
  shared/
    store/            # 전역 Zustand store
    components/       # 공용 컴포넌트
    lib/fetcher.ts    # axios 인스턴스 + 메서드 래퍼
```

### 상태 관리
- 서버 데이터: **Zustand store action에서 API 직접 호출**
- UI 전역: Zustand `shared/store/` / 로컬: `useState`
- 컴포넌트 직접 API 호출 금지

### Store action 패턴
```typescript
fetchIssues: async (projectId: number) => {
  set({ isLoading: true, error: null })
  try {
    const data = await issueApi.list(projectId)
    set({ issues: data.items })
  } catch (e) {
    set({ error: (e as Error).message })
  } finally {
    set({ isLoading: false })
  }
}
```

### URL params — source of truth
```typescript
const { projectId: paramId } = useParams<{ projectId?: string }>()
const storeId = useAppStore(s => s.selectedProjectId)
const projectId = paramId ? Number(paramId) : storeId
```

### 스타일
- Tailwind CSS + CVA / inline style 금지
- `<input type="number">` 금지 → `type="text" inputMode="numeric"` (CJK IME 충돌)

### 허용 라이브러리
```
react, react-dom, zustand, axios, tailwindcss, postcss, autoprefixer,
react-hook-form, react-router-dom, @radix-ui/*, class-variance-authority,
clsx, tailwind-merge, lucide-react, zod
```
이 목록에 없는 건 Architect 승인 필요.

---

## Part 5. 공통 금지 패턴

- 빈 catch 블록 / 하드코딩 시크릿 / `any` 타입
- `as` 캐스트 남발 (불가피할 때만, 사유 주석)
- 테스트 없는 코드 merge
- skeleton에 없는 API/화면 추가
- 화이트리스트에 없는 라이브러리 설치
