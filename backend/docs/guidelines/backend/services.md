# Backend — 서비스 & CRUD 가이드

> 서비스 로직, CRUD 함수, 비즈니스 검증, 에러 처리 작업 시 읽어라.

---

## CRUD — 쿼리만, `Model | None` 반환

비즈니스 로직 없음. 예외 없음. 데이터만 다룬다.

```python
# crud/notebook.py
from sqlalchemy.orm import Session
from models.notebook import NotebookModel
from schemas.notebook import NotebookUpdateBody

def get_notebook(db: Session, notebook_id: int) -> NotebookModel | None:
    return db.query(NotebookModel).filter(NotebookModel.id == notebook_id).first()

def get_notebooks_by_user_id(db: Session, user_id: int) -> list[NotebookModel]:
    return db.query(NotebookModel).filter(NotebookModel.user_id == user_id).all()

def create_notebook(db: Session, user_id: int, title: str) -> NotebookModel:
    obj = NotebookModel(user_id=user_id, title=title)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

def update_notebook(db: Session, notebook_id: int, body: NotebookUpdateBody) -> NotebookModel | None:
    obj = db.query(NotebookModel).filter(NotebookModel.id == notebook_id).first()
    if not obj:
        return None
    for field in body.model_fields_set:          # 부분 업데이트 — 필드 루프
        setattr(obj, field, getattr(body, field))
    db.commit()
    db.refresh(obj)
    return obj

def delete_notebook(db: Session, notebook_id: int) -> NotebookModel | None:
    obj = db.query(NotebookModel).filter(NotebookModel.id == notebook_id).first()
    if not obj:
        return None
    db.delete(obj)
    db.commit()
    return obj
```

CRUD는 예외를 던지지 않는다. `None` 반환 → 서비스가 예외 처리.

---

## Service — 검증 + 위임 + 반환, 파일 끝 싱글턴

```python
# services/notebook.py
from sqlalchemy.orm import Session
from core.exceptions.notebook import NotebookNotFoundException
from crud.notebook import get_notebook, create_notebook, update_notebook, delete_notebook
from models.notebook import NotebookModel
from schemas.notebook import NotebookUpdateBody

class NotebookService:
    def get_notebook(self, notebook_id: int, db: Session) -> NotebookModel:
        notebook = get_notebook(db, notebook_id)
        if not notebook:
            raise NotebookNotFoundException()
        return notebook

    def create_notebook(self, user_id: int, title: str, db: Session) -> NotebookModel:
        return create_notebook(db, user_id, title)

    def update_notebook(self, notebook_id: int, body: NotebookUpdateBody, db: Session) -> NotebookModel:
        notebook = update_notebook(db, notebook_id, body)
        if not notebook:
            raise NotebookNotFoundException()
        return notebook

    def delete_notebook(self, notebook_id: int, db: Session) -> NotebookModel:
        notebook = delete_notebook(db, notebook_id)
        if not notebook:
            raise NotebookNotFoundException()
        return notebook

notebook_service = NotebookService()  # ← 파일 끝 싱글턴 필수
```

`from services.notebook import notebook_service`로 엔드포인트에서 임포트.

---

## 에러 처리 — 3계층 구조

```python
# core/exceptions/base.py
class CustomException(Exception):
    code: int = 500
    message: str = "서버 에러가 발생했습니다."

    def __init__(self, message: str | None = None, code: int | None = None):
        self.message = message or self.message
        self.code = code or self.code

# core/exceptions/issue.py
class IssueNotFoundException(CustomException):
    def __init__(self):
        super().__init__("존재하지 않는 이슈입니다.", code=404)

class InvalidStatusTransitionException(CustomException):
    def __init__(self):
        super().__init__("유효하지 않은 상태 전환입니다.", code=409)

# core/exceptions/exception_handlers.py
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

def custom_base_handler(_: Request, exc: CustomException) -> JSONResponse:
    response = BaseResponse.error(message=exc.message, code=exc.code)
    return JSONResponse(status_code=exc.code, content=response.model_dump())

def init_exception_handlers(app: FastAPI):
    app.add_exception_handler(CustomException, custom_base_handler)
    app.add_exception_handler(IssueNotFoundException, custom_base_handler)
    # 새 예외 추가 시 여기에 한 줄만 추가

# main.py
from core.exceptions.exception_handlers import init_exception_handlers
init_exception_handlers(app)
```

새 에러 추가 순서:
1. `core/exceptions/도메인.py`에 클래스 작성
2. `exception_handlers.py`에 `add_exception_handler` 한 줄 추가
3. 서비스에서 `raise IssueNotFoundException()`

---

## async 규칙

프로젝트가 **sync(psycopg2/SQLAlchemy)** 이면 — 일반 `def` + `Session`.
프로젝트가 **async(asyncpg/AsyncSession)** 이면 — `async def` + `await`.

```python
# ✅ sync 프로젝트 (SK 스타일)
def get_notebook(db: Session, notebook_id: int) -> NotebookModel | None:
    return db.query(NotebookModel).filter(NotebookModel.id == notebook_id).first()

# sync Session 메서드 — await 없음
db.add(obj)      # ✅
db.delete(obj)   # ✅
db.commit()      # ✅
db.refresh(obj)  # ✅
```

---

## 부분 업데이트 패턴

```python
# ✅ 필드 루프 — 필드 추가돼도 코드 안 바뀜
for field in body.model_fields_set:
    setattr(obj, field, getattr(body, field))

# ❌ 필드별 if 분기
if body.title is not None:
    obj.title = body.title
if body.description is not None:
    obj.description = body.description
```

---

## 분기 로직은 딕셔너리

```python
# ✅ 딕셔너리 매핑
ORDER_BY_MAP = {
    "recent": Issue.created_at.desc(),
    "priority": Issue.priority.asc(),
    "status": Issue.status.asc(),
}
stmt = select(Issue).order_by(ORDER_BY_MAP[sort_by])

# ❌ if-elif 체인
if sort_by == "recent":
    stmt = stmt.order_by(Issue.created_at.desc())
elif sort_by == "priority":
    ...
```

---

## 타입 작성 규칙

```python
# ✅ Python 3.10+ 문법
def create(db: AsyncSession, data: IssueCreate) -> Issue: ...
def get(db: AsyncSession, id: int) -> Issue | None: ...

# ❌ 구식 문법
from typing import Optional, Dict
def get(db: AsyncSession, id: int) -> Optional[Issue]: ...
```

독스트링은 복잡한 비즈니스 로직에만. 자명한 함수엔 달지 마라.

---

## 추상화 원칙

```python
# ✅ 중복 3번 이상일 때만 추출
# ❌ BaseService, BaseRepository 선제적 생성 금지
# ❌ DI 컨테이너, 과잉 추상화 금지
```
