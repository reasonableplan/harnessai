# Backend — API 엔드포인트 가이드

> 라우터 작성, 엔드포인트 추가, BaseResponse 조합 작업 시 읽어라.

---

## 엔드포인트 패턴 — 라우팅만

엔드포인트에 if문이 없어야 한다. 분기는 서비스가 한다.

```python
# api/endpoints/issues.py
from fastapi import APIRouter
from app.db.database import DbSession
from app.services.issue import issue_service
from app.schemas.issue import IssueCreate, IssueUpdate, IssueResponse
from app.schemas.response import BaseResponse

router = APIRouter(prefix="/issues", tags=["issues"])

@router.get("/{issue_id}", response_model=BaseResponse[IssueResponse])
async def get_issue(issue_id: int, db: DbSession) -> BaseResponse[IssueResponse]:
    issue = await issue_service.get(db, issue_id)
    return BaseResponse.ok(IssueResponse.model_validate(issue))

@router.post("", response_model=BaseResponse[IssueResponse], status_code=201)
async def create_issue(body: IssueCreate, db: DbSession) -> BaseResponse[IssueResponse]:
    issue = await issue_service.create(db, body)
    return BaseResponse.ok(IssueResponse.model_validate(issue))

@router.patch("/{issue_id}", response_model=BaseResponse[IssueResponse])
async def update_issue(issue_id: int, body: IssueUpdate, db: DbSession) -> BaseResponse[IssueResponse]:
    issue = await issue_service.update(db, issue_id, body)
    return BaseResponse.ok(IssueResponse.model_validate(issue))

@router.delete("/{issue_id}", status_code=204)
async def delete_issue(issue_id: int, db: DbSession) -> None:
    await issue_service.delete(db, issue_id)
```

---

## BaseResponse

```python
# schemas/response.py
from typing import Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")

class BaseResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str
    data: T | None = None
    status: str = "success"

    @classmethod
    def ok(cls, data: T | None = None, message: str = "Success") -> "BaseResponse[T]":
        return cls(status="success", code=0, data=data, message=message)

    @classmethod
    def error(cls, data: T | None = None, code: int = -1, message: str = "Error") -> "BaseResponse[T]":
        return cls(status="error", code=code, data=data, message=message)
```

모든 엔드포인트가 `return BaseResponse.ok(data)` 한 줄로 끝나야 한다.

---

## DbSession 타입 alias

```python
# db/database.py
from typing import Annotated
from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

DbSession = Annotated[AsyncSession, Depends(get_db)]
```

모든 엔드포인트에서 `db: DbSession` 으로 주입받는다. `Depends(get_db)` 직접 쓰지 마라.

---

## 라우터 집합

```python
# api/route.py
from fastapi import APIRouter
from app.api.endpoints import projects, issues, agents, sprints, labels, comments

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(projects.router)
api_router.include_router(issues.router)
api_router.include_router(agents.router)
api_router.include_router(sprints.router)
api_router.include_router(labels.router)
api_router.include_router(comments.router)
```

새 도메인 추가 = `include_router` 한 줄.

---

## Pagination 패턴

```python
# 공통 pagination 파라미터
@router.get("", response_model=BaseResponse[PaginatedResponse[IssueResponse]])
async def list_issues(
    project_id: int,
    page: int = 1,
    limit: int = 20,
    db: DbSession = ...,
) -> BaseResponse[PaginatedResponse[IssueResponse]]:
    result = await issue_service.list(db, project_id, page, limit)
    return BaseResponse.ok(result)
```

```python
# schemas/response.py에 추가
class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    limit: int
```

---

## main.py 핵심 구조

```python
# main.py
from fastapi import FastAPI
from api.route import api_router
from core.exceptions.exception_handlers import init_exception_handlers

app = FastAPI()
app.include_router(api_router)
init_exception_handlers(app)  # ← 개별 add_exception_handler 직접 호출 금지
```

예외 핸들러는 `init_exception_handlers(app)` 한 줄로. 새 예외 추가는 `exception_handlers.py`에서만.
