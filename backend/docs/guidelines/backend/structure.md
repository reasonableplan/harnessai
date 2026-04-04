# Backend — 구조 & 모델 가이드

> 새 도메인 추가, 모델/스키마 작성, 디렉토리 구조 설계 시 읽어라.

---

## 디렉토리 구조

```
app/
  api/
    endpoints/        ← 얇은 라우터 (BaseResponse 조합만, if문 없음)
    route.py          ← 전체 라우터 집합
  crud/               ← 순수 DB 함수 (예외 없음, Model | None 반환)
  services/           ← 비즈니스 로직 + 예외 발생 + 파일 끝 싱글턴
  models/             ← SQLAlchemy Column 테이블 정의
  schemas/            ← Pydantic 요청/응답 스키마
  core/
    config.py         ← pydantic-settings (Settings 클래스)
    exceptions/
      base.py         ← CustomException 베이스
      도메인.py       ← DomainXxxException (404/409 등)
      exception_handlers.py  ← init_exception_handlers(app)
  db/
    database.py       ← engine, get_db, get_db_context, DbSession
```

---

## 새 도메인 추가 순서

기존 파일 복붙해서 이름만 바꾸면 된다:

```
1. models/order.py              ← SQLAlchemy Column 테이블
2. schemas/order.py             ← Create/Update/Response Pydantic
3. crud/order.py                ← get/list/create/update/delete 함수
4. services/order.py            ← 검증 + crud 호출 + 싱글턴
5. core/exceptions/order.py     ← OrderNotFoundException 등
6. core/exceptions/exception_handlers.py ← 핸들러 등록 한 줄 추가
7. api/endpoints/order.py       ← 라우터 (BaseResponse.ok() 조합)
8. api/route.py                 ← router include 한 줄 추가
```

---

## SQLAlchemy 모델 패턴

```python
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, func
from db.database import Base

class IssueModel(Base):
    __tablename__ = "issues"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    status = Column(String, nullable=False, default="TODO")   # 자주 필터링 → index=True
    is_active = Column(Boolean, nullable=False, default=True)

    # FK — ondelete 명시 필수
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    sprint_id = Column(Integer, ForeignKey("sprints.id", ondelete="SET NULL"), nullable=True, index=True)
    assignee_agent_id = Column(Integer, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # updated_at 자동 갱신이 필요하면: onupdate=func.now() 또는 서비스에서 명시적 갱신
```

- `DateTime(timezone=True)` 항상 사용 — timezone-naive TIMESTAMP 금지
- `server_default=func.now()` — INSERT 시 DB가 채움
- `relationship()` 사용 금지 — 암묵적 N+1 유발. 필요한 데이터는 서비스에서 명시적 쿼리

### Enum은 StrEnum

```python
from enum import StrEnum

class IssueSortType(StrEnum):
    RECENT = "recent"
    CREATED_AT = "created_at"
    NAME = "name"
```

Literal은 외부 API 스키마에만. 내부 로직에서 다루는 상태값은 StrEnum.

### FK ondelete 규칙

| 상황 | ondelete |
|------|----------|
| 부모 삭제 시 자식도 삭제 | `CASCADE` |
| 부모 삭제 시 null 허용 | `SET NULL` |
| 감사 로그 — 삭제 방지 | `RESTRICT` |

---

## Pydantic 스키마 패턴

```python
from pydantic import BaseModel, Field

class IssueCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    project_id: int
    priority: str = Field(default="MEDIUM")

class IssueUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: str | None = None

class IssueResponse(BaseModel):
    id: int
    title: str
    status: str
    priority: str
    project_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
```

---

## 레이어 경계

| 레이어 | 역할 | 예외 발생? |
|--------|------|-----------|
| `crud/` | DB 쿼리만 | ❌ None 반환 |
| `services/` | 검증 + 조합 | ✅ AppError |
| `api/endpoints/` | 라우팅 + BaseResponse | ❌ |

None을 아래 레이어로 흘리지 마라. 서비스 진입점에서 즉시 잡아라.

```python
# ✅ 서비스에서 None 처리
async def get_issue(db, issue_id: int) -> Issue:
    issue = await crud.get(db, issue_id)
    if issue is None:
        raise AppError(ERR_ISSUE_NOT_FOUND)
    return issue

# ❌ None을 엔드포인트까지 흘리기
```

---

## 설정 관리

```python
# ✅ Settings 클래스 한 곳 — 코드 전체에 os.getenv() 금지
from app.core.config import settings
DATABASE_URL = settings.database_url

# ❌ 여기저기 os.getenv()
DATABASE_URL = os.getenv("DATABASE_URL")
```
