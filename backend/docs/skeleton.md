# Project Skeleton — HabitFlow

## 1. Overview
- **프로젝트명**: HabitFlow
- **한 줄 설명**: 매일 습관을 체크하고 스트릭을 추적하는 앱
- **목적**: 스트릭 기반 동기부여로 사용자가 매일 습관을 유지하도록 돕는다
- **타겟 사용자**: 개인 생산성을 높이고 싶은 사람

---

## 2. 기능 요구사항

### 핵심 기능 (MVP — Phase 1)
- [x] 회원가입 / 로그인 / 토큰 갱신 (JWT)
- [x] 습관 CRUD (생성, 목록 조회, 수정, 소프트 삭제)
- [x] 오늘의 습관 체크 / 언체크 (하루 1회, 오늘 날짜만)
- [x] 현재 스트릭 계산 + 오늘 완료 여부 표시
- [x] 오늘의 진행률 (완료 수 / 전체 수)

### 추가 기능 (Phase 2)
- [ ] 완료 기록 히트맵 (최근 91일)
- [ ] 습관 상세 페이지 (스트릭 + 히트맵)

### 비즈니스 규칙
- 완료 기록은 오늘 날짜만 가능 (과거 소급 입력 불가)
- 습관 삭제 = 소프트 딜리트 (`is_active = False`) — 완료 기록 보존
- 사용자당 습관 수 제한 없음

---

## 3. 기술 스택

### 프론트엔드 (TypeScript)
- **프레임워크**: React 19 (Vite)
- **라우팅**: react-router-dom v7
- **상태 관리**: Zustand (서버 데이터 포함 전체 — store action에서 API 호출)
- **HTTP 클라이언트**: axios (interceptor로 401 자동 갱신)
- **스타일링**: Tailwind CSS + CVA (`index.style.ts` 분리, inline 금지)
- **폼**: React Hook Form + zod
- **UI 컴포넌트**: shadcn/ui (base-ui 기반), lucide-react

### 백엔드 (Python)
- **프레임워크**: FastAPI (async)
- **ORM**: SQLAlchemy Column 스타일 (async + aiosqlite)
- **마이그레이션**: Alembic
- **인증**: python-jose (JWT HS256) + passlib + bcrypt
- **유효성 검증**: Pydantic v2
- **테스트**: pytest + httpx AsyncClient
- **DB**: SQLite (개발)

### 허용 라이브러리 화이트리스트

**프론트엔드:**
```
react, react-dom, react-router-dom, zustand, axios,
tailwindcss, postcss, autoprefixer, react-hook-form, zod,
@radix-ui/*, class-variance-authority, clsx, tailwind-merge,
lucide-react
```

**백엔드:**
```
fastapi, uvicorn, sqlalchemy, alembic,
python-jose, passlib, bcrypt, pydantic, pydantic-settings,
httpx, pytest, pytest-asyncio, aiosqlite
```

---

## 5. 인증 / 권한

### JWT 설정
- 알고리즘: HS256
- Access token 만료: 24시간
- Refresh token 만료: 7일
- 저장: localStorage (accessToken, refreshToken)

### 토큰 갱신 흐름
```
API 호출 → 401 응답
  → axios interceptor: POST /api/auth/refresh
    → 성공: 새 accessToken 저장 → 원래 요청 재시도
    → 실패: 토큰 삭제 → /login 리디렉션
```

### 보호 라우트
- 인증 필요: `/`, `/habits`, `/habits/:id`
- 인증 불필요: `/login`, `/register`
- 구현: `ProtectedRoute` 컴포넌트

### 백엔드 인증 의존성
```python
CurrentUser = Annotated[User, Depends(get_current_user)]
# get_current_user: Bearer 토큰 → decode → User 반환, 실패 시 AuthException
```

---

## 6. DB 스키마

> LESSON-003: updated_at → onupdate=func.now() 필수
> LESSON-004: 모든 datetime → DateTime(timezone=True)
> LESSON-007: ID = Integer auto-increment

### users
```python
class User(Base):
    __tablename__ = "users"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    email       = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    created_at  = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at  = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
```

### habits
```python
class Habit(Base):
    __tablename__ = "habits"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    user_id     = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name        = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)
    is_active   = Column(Boolean, nullable=False, default=True, index=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at  = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
```

### habit_completions
```python
class HabitCompletion(Base):
    __tablename__ = "habit_completions"
    id             = Column(Integer, primary_key=True, autoincrement=True)
    habit_id       = Column(Integer, ForeignKey("habits.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id        = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    completed_date = Column(Date, nullable=False)
    created_at     = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("habit_id", "completed_date", name="uq_habit_completion_date"),
    )
```

### 인덱스
| 테이블 | 컬럼 | 이유 |
|--------|------|------|
| users | email | 로그인 조회 |
| habits | user_id | 사용자별 목록 |
| habits | is_active | 활성 필터 |
| habit_completions | habit_id | 습관별 기록 |
| habit_completions | user_id | 사용자별 기록 |
| habit_completions | (habit_id, completed_date) | UNIQUE 중복 방지 |

---

## 7. API 스키마

> LESSON-001: Query params는 snake_case
> 응답: BaseResponse<T> 래핑
> 에러: { "error": string, "code": string, "details": {} }

### 에러 코드
```
AUTH_001: 인증 실패 (이메일/비밀번호 불일치)
AUTH_002: 토큰 만료 또는 무효
AUTH_003: 권한 없음 (다른 사용자 리소스 접근)
VALIDATION_001: 입력값 검증 실패
RESOURCE_001: 리소스 없음
RESOURCE_002: 중복 리소스 (이메일 중복, 오늘 이미 완료)
SERVER_001: 내부 서버 에러
```

### Auth

**POST /api/auth/register**
```
Request:  { "email": string, "password": string (min 8자) }
Response 201: BaseResponse<{ "id": int, "email": string, "createdAt": string }>
Error 409: RESOURCE_002 (이메일 중복)
Error 422: VALIDATION_001
```

**POST /api/auth/login**
```
Request:  { "email": string, "password": string }
Response 200: BaseResponse<{ "accessToken": string, "refreshToken": string, "tokenType": "bearer" }>
Error 401: AUTH_001
```

**POST /api/auth/refresh**
```
Request:  { "refreshToken": string }
Response 200: BaseResponse<{ "accessToken": string, "tokenType": "bearer" }>
Error 401: AUTH_002
```

### Habits

**GET /api/habits** `[Auth]`
```
Query: (없음)
Response 200: BaseResponse<list[HabitResponse]>

HabitResponse: {
  "id": int, "name": string, "description": string|null,
  "isActive": bool, "createdAt": string,
  "currentStreak": int, "completedToday": bool
}
```
> N+1 방지: 활성 습관 전체 조회 후 완료 기록 일괄 조회

**POST /api/habits** `[Auth]`
```
Request:  { "name": string (max 100), "description": string|null (max 500) }
Response 201: BaseResponse<{ "id": int, "name": string, "description": string|null, "isActive": bool, "createdAt": string }>
Error 422: VALIDATION_001
```

**PATCH /api/habits/{habit_id}** `[Auth]`
```
Request:  { "name": string|null, "description": string|null, "isActive": bool|null }
Response 200: BaseResponse<{ "id": int, "name": string, "description": string|null, "isActive": bool, "updatedAt": string }>
Error 403: AUTH_003 | Error 404: RESOURCE_001
```

**DELETE /api/habits/{habit_id}** `[Auth]`
```
Response 204
Error 403: AUTH_003 | Error 404: RESOURCE_001
```
> 소프트 딜리트: is_active = False

### Completions

**POST /api/completions** `[Auth]`
```
Request:  { "habitId": int }
Response 201: BaseResponse<{ "id": int, "habitId": int, "completedDate": string, "createdAt": string }>
Error 404: RESOURCE_001 | Error 409: RESOURCE_002
```

**DELETE /api/completions** `[Auth]`
```
Request body: { "habitId": int }
Response 204
Error 404: RESOURCE_001 (오늘 완료 기록 없음)
```

**GET /api/completions** `[Auth]`
```
Query: start_date (YYYY-MM-DD), end_date (YYYY-MM-DD), habit_id (int, optional)
Response 200: BaseResponse<list[{ "habitId": int, "completedDate": string }]>
Error 400: VALIDATION_001 (날짜 오류, 최대 91일 범위)
```

---

## 8. UI/UX 설계

### 화면 목록
| 경로 | 화면명 | 컨테이너 |
|------|--------|----------|
| /login | 로그인 | LoginContainer |
| /register | 회원가입 | RegisterContainer |
| / | 오늘의 습관 | HomeContainer |
| /habits | 습관 관리 | HabitsContainer |
| /habits/:id | 습관 상세 (Phase 2) | HabitDetailContainer |

### 사용자 흐름
```
미인증
  /login → 로그인 성공 → /
  /register → 가입 + 자동 로그인 → /

홈 (/)
  습관 카드 클릭 → 체크/언체크 (낙관적 업데이트)
  + FAB → AddHabitSheet (바텀 시트)
  헤더 "관리" → /habits
  로그아웃 → /login

습관 관리 (/habits)
  행 클릭 → /habits/:id (Phase 2)
  삭제 → confirm → 소프트 딜리트
  + 추가 → AddHabitSheet

에러 케이스
  체크 실패 → 낙관적 업데이트 롤백 + 에러 토스트
  401 → 토큰 갱신 → 실패 시 /login
  기타 → 에러 토스트
```

### 컴포넌트 트리
```
App (react-router-dom BrowserRouter)
├── ProtectedRoute
│   ├── HomeContainer (/)
│   │   ├── TodayHeader (날짜 텍스트 + ProgressBar)
│   │   ├── HabitList
│   │   │   └── HabitCard[] (체크 원형 + 이름 + 스트릭 뱃지)
│   │   └── AddHabitSheet (바텀 시트)
│   │       └── HabitForm
│   └── HabitsContainer (/habits)
│       ├── HabitRow[] (이름 + 스트릭 + 삭제)
│       └── AddHabitSheet
└── AuthLayout
    ├── LoginContainer (/login)
    └── RegisterContainer (/register)
```

### 상태 관리 설계

**authStore** (`shared/store/auth.store.ts`)
```typescript
interface AuthStore {
  accessToken: string | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: () => void
  setAccessToken: (token: string) => void  // interceptor 갱신용
}
```

**habitStore** (`containers/home/store/habit.store.ts`)
```typescript
interface HabitStore {
  habits: Habit[]
  isLoading: boolean
  error: string | null
  fetchHabits: () => Promise<void>
  createHabit: (name: string, description?: string) => Promise<void>
  deleteHabit: (id: number) => Promise<void>
  // 낙관적 업데이트: 즉시 로컬 변경 → API 실패 시 fetchHabits()로 롤백
  checkHabit: (habitId: number) => Promise<void>
  uncheckHabit: (habitId: number) => Promise<void>
}
```

### 디자인 가이드

**색상 (CSS var)**
```css
--bg-base: #0f1117       /* 전체 배경 */
--bg-surface: #1a1d27    /* 카드 */
--bg-elevated: #242736   /* 시트/모달 */
--bg-border: #2e3147
--text-primary: #f1f3fa
--text-secondary: #9ca3c4
--text-muted: #5b6082
--accent-blue: #4f76f6   /* 완료 체크, 버튼 */
--status-done: #22c55e   /* 완료 상태 */
--priority-high: #f97316 /* 스트릭 불꽃 */
```

**레이아웃**: 모바일 우선, max-width 448px, 좌우 패딩 16px

**스타일 규칙**:
- CVA + `index.style.ts` — 인라인 Tailwind 2개 이상 금지
- `type="number"` 금지 → `type="text" inputMode="numeric"` (LESSON-006)
- 폼 submit 아닌 버튼: `type="button"` 명시
- shadcn/ui: base-ui 기반 (`render=` 패턴, `asChild` 금지)

---

## 9. 에러 핸들링

### 백엔드 예외 계층
```python
# core/exceptions/base.py
class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400): ...

# core/exceptions/auth.py
class AuthException(AppError):      # 401
class ForbiddenException(AppError): # 403

# core/exceptions/resource.py
class NotFoundException(AppError):  # 404
class ConflictException(AppError):  # 409

# core/exceptions/exception_handlers.py
def init_exception_handlers(app): ...  # 전역 등록
```

### 프론트엔드 axios interceptor
```typescript
// 401 → POST /api/auth/refresh → 성공: 재시도 / 실패: logout + navigate('/login')
// 403 → toast("권한이 없습니다")
// 404 → toast("찾을 수 없습니다")
// 409 → toast("이미 처리되었습니다")
// 422 → 폼 필드별 에러 표시
// 500 → toast("잠시 후 다시 시도해주세요")
```

---

## 10. 상태 흐름

### 스트릭 계산 규칙
```
기준일: today (서버 날짜)
완료 날짜 집합: Set<date>

1. today ∈ 완료 → cursor = today
2. today ∉ 완료, (today-1) ∈ 완료 → cursor = today-1
3. today ∉ 완료, (today-1) ∉ 완료 → streak = 0 (종료)

cursor부터 역방향:
  cursor ∈ 완료 → streak++, cursor -= 1일
  cursor ∉ 완료 → 종료

예시:
  [오늘, 어제, 그저께] → streak = 3
  [오늘, 어제] + 공백 + [4일전] → streak = 2
  [어제, 그저께] (오늘 미완료) → streak = 2
  [3일전] 이후 없음 → streak = 0
```

### 습관 상태 전이
```
ACTIVE (is_active=True)
  → 체크: HabitCompletion 생성 (오늘 날짜, UNIQUE)
  → 언체크: HabitCompletion 삭제 (오늘 날짜)
  → 수정: name / description / is_active 변경 가능
  → 삭제: is_active = False → INACTIVE

INACTIVE (is_active=False)
  → 목록 조회 제외
  → 완료 기록은 DB에 보존
  → 복구: is_active = True (PATCH로 가능)
```

---

## 17. 태스크 분해
> Orchestrator Phase에서 채워짐

---

## 18. 구현 노트
> 구현 Phase에서 채워짐
