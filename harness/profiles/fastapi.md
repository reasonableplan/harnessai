---
id: fastapi
name: FastAPI Backend
status: confirmed
extends: _base
version: 1
maintainer: harness-core

paths: [".", "backend/", "apps/backend/", "apps/api/", "services/api/"]
detect:
  files: [pyproject.toml]
  contains:
    pyproject.toml: ["fastapi"]

components:
  - id: persistence
    required: true
    skeleton_section: persistence
    description: SQLAlchemy/SQLModel 모델 + Alembic 마이그레이션
  - id: auth
    required: false
    skeleton_section: auth
    description: JWT + bcrypt + get_current_user 의존성
  - id: interface.http
    required: true
    skeleton_section: interface.http
    description: FastAPI 라우터 + Pydantic 스키마 + 서비스 레이어
  - id: integrations
    required: false
    skeleton_section: integrations
    description: 3rd party API 클라이언트 + webhook 수신
  - id: core.logic
    required: true
    skeleton_section: core.logic
    description: 순수 함수 (core/) + I/O 분리 (io/)
  - id: errors
    required: true
    skeleton_section: errors
    description: AppError 예외 계층 + 전역 핸들러

skeleton_sections:
  required: [overview, stack, errors, interface.http, core.logic, tasks, notes]
  optional: [requirements, configuration, auth, persistence, integrations, state.flow, observability, deployment, test_strategy, ci_cd, rate_limiting, environments]
  order: [overview, requirements, stack, configuration, environments, errors, auth, persistence, integrations, interface.http, rate_limiting, state.flow, core.logic, observability, deployment, test_strategy, ci_cd, tasks, notes]

toolchain:
  install: "uv sync"
  test: "uv run pytest tests/ --rootdir=."
  lint: "uv run ruff check src/"
  type: "uv run pyright src/"
  format: "uv run ruff format src/ tests/"

whitelist:
  runtime:
    - fastapi
    - uvicorn
    - sqlalchemy
    - sqlmodel
    - alembic
    - pydantic
    - pydantic-settings
    - python-jose
    - passlib
    - bcrypt
    - python-multipart
    - httpx
    - aiosqlite
    - asyncpg
  dev:
    - pytest
    - pytest-asyncio
    - pytest-mock
    - ruff
    - pyright
  prefix_allowed: []

file_structure: |
  backend/
    pyproject.toml
    .env.example
    alembic.ini
    src/
      main.py                  # FastAPI 앱 진입점
      config.py                # pydantic-settings
      models/
        __init__.py
        base.py                # BaseModel (id, created_at, updated_at)
        <domain>.py
      schemas/
        common.py              # PaginatedResponse, ErrorResponse
        <domain>.py
      services/
        <domain>.py            # 비즈니스 로직
      routers/
        auth.py
        <domain>.py
      dependencies/
        auth.py                # get_current_user
      core/
        exceptions/            # AppError 계층
        logging.py
      db/
        session.py
        migrations/            # Alembic
    tests/
      conftest.py
      api/
      models/
      services/

provides_capabilities:
  - http_server
  - env_config
  - production_concerns

gstack_mode: manual
gstack_recommended:
  before_design: [office-hours]
  after_design: [plan-eng-review]
  after_build: [review]
  before_ship: [qa]
  after_ship: [retro]

lessons_applied:
  - LESSON-001   # query params snake_case
  - LESSON-002   # limit 상한 화면별
  - LESSON-003   # updated_at onupdate
  - LESSON-004   # DateTime timezone=True
  - LESSON-007   # ID 타입 통일
  - LESSON-018   # 상수 정의 범위 vs 실제 사용 범위 불일치 (dead 상수)
  - LESSON-019   # 외부 명령 stderr → 사용자 친화 메시지 번역 (subprocess 사용 시)
  - LESSON-020   # 진행 표시 [N/M] 실제 작동 — 껍데기 금지 (긴 백그라운드 작업 시)
---

# FastAPI Backend Profile

## 핵심 원칙

- **라우터는 DB 직접 접근 금지** — 반드시 service 레이어 경유
- **응답 네이밍 camelCase** — body는 `alias_generator=to_camel`, query는 snake_case (LESSON-001)
- **HTTP 500 내부 에러 미노출** — `SERVER_001` 코드만 반환
- **모든 모델에 id/created_at/updated_at** — BaseModel 상속 강제
- **datetime는 `DateTime(timezone=True)`** — naive timestamp 금지 (LESSON-004)
- **외래키는 ondelete 명시** — CASCADE / SET NULL / RESTRICT

## components.persistence

- SQLModel 또는 SQLAlchemy Column 스타일 일관성
- BaseModel 상속:
  ```python
  class BaseModel(SQLModel):
      id: int | None = Field(default=None, primary_key=True)
      created_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False))
      updated_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False))
  ```
- Alembic autogenerate 후 **생성된 마이그레이션 수동 검토**
- 인덱스는 skeleton.persistence 섹션과 1:1 일치

## components.interface.http

- 에러 응답 공통 래퍼: `{ error, code, details }`
- 페이지네이션: `{ items, total, page, limit }` — `limit` 상한 프로파일별 (보드/백로그 500, 목록 50)
- `@router.get()` 데코레이터에 `response_model` 명시 (타입 안전성)
- 인증 필요 엔드포인트: `current_user: CurrentUser` 파라미터 추가

## components.auth

- JWT HS256 + Access 15m / Refresh 7d (기본, 프로젝트별 조정)
- 비밀번호 해시: bcrypt cost ≥ 12
- 시크릿은 `SECRET_KEY` 환경변수 (configuration 섹션)
- 토큰 payload (LESSON-022, LESSON-023):
  ```json
  { "sub": "<user_id>", "type": "access", "ver": "<token_version>", "exp": "<unix_ts>" }
  ```
  - `type`: "access" / "refresh" — 혼용 방지 필수 (LESSON-022)
  - `ver`: User.token_version 과 일치 검증 — logout 시 token_version 증가로 무효화 (LESSON-023)
  - `role` 필요 시 추가 가능 (최소 payload 원칙)
- User 모델에 `token_version: int = 0` 필드 필수 (LESSON-023)
- refresh endpoint: httpOnly 쿠키 전용 — body.refresh_token 수락 금지 (LESSON-024)

## components.core.logic

- `core/` 디렉토리: 순수 함수만. I/O 금지.
- `io/` 디렉토리: DB/네트워크/파일 접근.
- 테스트: core/ 는 단위 테스트 커버리지 ≥ 90%, io/ 는 통합 테스트

## 설정 중앙화 (_base §10 구체화)

FastAPI 는 `pydantic-settings` 로 단일 `Settings` 클래스에 집중:

```python
# src/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    # 런타임 (env 전용 — 비밀값)
    database_url: str
    secret_key: str

    # 튜너블 (기본값 있음, env override 가능)
    jwt_expires_hours: int = 24
    rate_limit_per_minute: int = 60
    pagination_default_limit: int = 50
    pagination_max_limit: int = 500

    # 내부 상수 (코드 상수, 변경 드묾)
    health_check_interval: int = 30
    # 재시도 backoff — 컬렉션 전체를 소비하도록 작성 (LESSON-018)
    retry_backoff_seconds: tuple[float, ...] = (1.0, 2.0)

settings = Settings()  # 모듈 레벨 singleton


# 사용 예 — 반드시 컬렉션 전체를 순회 (dead 원소 없음)
for delay in settings.retry_backoff_seconds:
    time.sleep(delay)
    ...  # 재시도 로직
```

**원칙**:
- 비밀값 (DB URL, SECRET_KEY, 3rd-party API 키) → **env 전용**. 기본값 금지. (_base §4 보안 규칙)
- 튜너블 (rate limit, 페이지네이션) → `BaseSettings` 필드, env 로 override 가능.
- 코드 상수 (backoff, 내부 타임아웃) → `BaseSettings` 에 포함해 테스트에서 주입 가능하게.
- **매직 숫자 금지**: `time.sleep(30)` X, `time.sleep(settings.health_check_interval)` O.
- **LESSON-018 연결**: tuple/list 상수 정의 길이 ≤ 실제 소비 범위. `for x in settings.collection:` 순회가 가장 안전.

## 금지 사항

- `data: Any`, `response: object` 같은 모호한 타입
- `except Exception: pass` — 반드시 `logger.error` + 에러 응답
- 라우터 안에서 직접 DB 쿼리
- `print()` — 반드시 `logger` 사용
- raw SQL 문자열 concat — ORM 또는 `text()` + bound params

## 검증 명령

```bash
cd backend
uv run pytest tests/ --rootdir=.
uv run ruff check src/
uv run pyright src/
```
