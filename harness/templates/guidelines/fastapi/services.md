# FastAPI — Service 레이어 컨벤션

## 역할 분리

- **라우터**: HTTP 파싱 + 응답 직렬화만 담당
- **서비스**: 비즈니스 로직 + 도메인 규칙 + DB 조작
- **모델**: SQLAlchemy ORM 정의만 (로직 없음)

## 서비스 함수 시그니처

```python
def create_user(db: Session, *, email: str, password: str) -> User:
    ...
```

- keyword-only 인자 (`*,`) 로 혼동 방지
- 반환 타입 명시 필수
- DB 세션은 항상 첫 번째 인자

## 트랜잭션

- 서비스가 `db.commit()` 책임 (라우터는 commit 호출 금지)
- 실패 시 `db.rollback()` — `try/except` 또는 context manager
- 단위 작업 당 1 commit (여러 테이블 동시 변경 시 같은 트랜잭션 안에서)

## 에러

- 도메인 예외: 프로젝트 내 `exceptions.py` 정의 후 서비스에서 raise
- 라우터가 잡아서 `HTTPException` 으로 변환
- 외부 API 호출: timeout + retry 설정, `httpx.TimeoutException` 처리

## 금지 사항

- 서비스에서 `HTTPException` raise 금지 (HTTP 레이어 오염)
- 서비스에서 `Request` / `Response` 객체 참조 금지
- N+1 쿼리 금지 → `joinedload` / `selectinload` 사용
