# FastAPI — API 레이어 컨벤션

## 라우터 구조

- 각 도메인별 `APIRouter` 분리 (`routers/users.py`, `routers/items.py`)
- 공통 prefix + tags 선언: `router = APIRouter(prefix="/users", tags=["users"])`
- `main.py` 에서 `app.include_router(router)` 로 조립

## 엔드포인트 규칙

- 응답 타입은 반드시 `response_model=` 명시 (자동 직렬화 + OpenAPI 문서화)
- HTTP 상태 코드: 생성 `201`, 삭제 `204`, 검색 `200`, 잘못된 요청 `422`
- 에러: `HTTPException(status_code=..., detail=...)` — 내부 스택트레이스 미포함
- 페이지네이션: `skip: int = 0, limit: int = Query(20, le=100)` 패턴

## 의존성 주입

- DB 세션: `db: Session = Depends(get_db)` — 요청마다 새 세션, `finally` 에서 close
- 인증: `current_user: User = Depends(get_current_user)` — 라우터 레벨 의존성 체인

## 금지 사항

- 라우터 함수 안에서 직접 DB 쿼리 금지 → 반드시 service 레이어 경유
- `print()` / `logging.debug()` 프로덕션 코드 금지 → `structlog` 또는 `logging` 사용
- `except Exception: pass` 빈 catch 금지
