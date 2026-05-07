# FastAPI — 패키지 구조 컨벤션

## 표준 레이아웃

```
backend/
  src/
    app/
      __init__.py
      main.py          # FastAPI 앱 생성, lifespan, include_router
      routers/         # HTTP 라우터 (도메인별)
      services/        # 비즈니스 로직
      models/          # SQLAlchemy ORM 모델
      schemas/         # Pydantic 입출력 스키마
      deps.py          # 의존성 주입 (get_db, get_current_user)
      exceptions.py    # 도메인 예외 클래스
    config.py          # 환경변수 + Pydantic Settings
  tests/
    conftest.py        # pytest fixtures (TestClient, DB 세션 override)
    routers/           # 라우터 통합 테스트
    services/          # 서비스 단위 테스트
```

## 명명 규칙

- 라우터 파일: 도메인명 복수형 (`users.py`, `items.py`)
- 스키마: `UserCreate`, `UserRead`, `UserUpdate` (동사 suffix)
- ORM 모델: 단수형 클래스 (`User`, `Item`)
- 서비스 함수: `<동사>_<명사>` (`create_user`, `get_user_by_email`)

## 환경변수

- `pydantic-settings` 의 `BaseSettings` 로 중앙 관리
- `.env` 파일 지원, 시크릿은 환경변수만 (코드 내 하드코딩 금지)
- `config.py` 싱글턴: `settings = Settings()` — 모듈 임포트 시 1회 생성

## 테스트

- `TestClient` 는 `conftest.py` 에서 fixture 로 제공
- DB: 테스트 전용 SQLite in-memory (`sqlite:///:memory:`)
- 각 테스트는 독립 트랜잭션 (rollback fixture 패턴)
- 외부 API: `pytest-httpx` 또는 `unittest.mock.patch` 로 mock

## 금지 사항

- `app/` 안에서 `import *` 금지
- 순환 import 방지 — `deps.py` 가 `services/` import, `services/` 가 `models/` import (단방향)
- 설정 값을 모듈 상수로 하드코딩 금지 → 반드시 `settings.*` 경유
