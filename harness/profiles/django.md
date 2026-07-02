---
id: django
name: Django Backend
status: confirmed
extends: _base
version: 1
maintainer: harness-core

paths: [".", "backend/", "apps/backend/", "apps/api/", "services/api/"]
detect:
  files: [manage.py]

components:
  - id: persistence
    required: true
    skeleton_section: persistence
    description: Django ORM 모델 + makemigrations 마이그레이션
  - id: auth
    required: false
    skeleton_section: auth
    description: django.contrib.auth + DRF 인증 (SessionAuth/TokenAuth/JWT)
  - id: interface.http
    required: true
    skeleton_section: interface.http
    description: DRF ViewSet/APIView + Serializer + urls.py 라우팅
  - id: integrations
    required: false
    skeleton_section: integrations
    description: 3rd party API 클라이언트 + webhook 수신
  - id: core.logic
    required: true
    skeleton_section: core.logic
    description: 서비스 함수 (services.py) — view/serializer 밖의 비즈니스 로직
  - id: errors
    required: true
    skeleton_section: errors
    description: 도메인 예외 계층 + DRF exception_handler 에서 변환

skeleton_sections:
  required: [overview, stack, errors, interface.http, core.logic, tasks, notes]
  optional: [requirements, configuration, auth, persistence, integrations, state.flow, observability, deployment, test_strategy, ci_cd, rate_limiting, environments]
  order: [overview, requirements, stack, configuration, environments, errors, auth, persistence, integrations, interface.http, rate_limiting, state.flow, core.logic, observability, deployment, test_strategy, ci_cd, tasks, notes]

toolchain:
  install: "uv sync"
  test: "uv run pytest"
  lint: "uv run ruff check ."
  type: "uv run mypy ."
  format: "uv run ruff format ."

whitelist:
  runtime:
    - django
    - djangorestframework
    - django-cors-headers
    - django-environ
    - django-filter
    - psycopg
    - psycopg2-binary
    - gunicorn
    - httpx
    - celery
    - redis
  dev:
    - pytest
    - pytest-django
    - pytest-mock
    - ruff
    - mypy
    - django-stubs
    - djangorestframework-stubs
  prefix_allowed: []

file_structure: |
  backend/
    pyproject.toml
    manage.py
    .env.example
    config/
      settings/
        base.py                # 공통 설정 (django-environ 으로 env 로드)
        dev.py
        prod.py
      urls.py                  # 루트 URLConf — 앱별 include()
      wsgi.py
    apps/
      <domain>/
        models.py              # created_at/updated_at 포함 (TimeStampedModel 상속)
        serializers.py
        views.py               # DRF ViewSet/APIView — 얇게
        urls.py
        services.py            # 비즈니스 로직
        migrations/
        tests/
    common/
      models.py                # TimeStampedModel 추상 베이스
      exceptions.py            # 도메인 예외 계층
      exception_handler.py     # DRF 전역 핸들러

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
  - LESSON-003   # updated_at onupdate (Django: auto_now)
  - LESSON-004   # DateTime timezone (Django: USE_TZ=True 고정)
  - LESSON-007   # ID 타입 통일
  - LESSON-018   # 상수 정의 범위 vs 실제 사용 범위 불일치 (dead 상수)
---

# Django Backend Profile

## 핵심 원칙

- **view/serializer 에 비즈니스 로직 금지** — 다중 모델을 건드리는 로직은 `services.py` 함수로
- **네이밍은 DRF 기본 snake_case** — query param 도 snake_case (LESSON-001)
- **HTTP 500 내부 에러 미노출** — 전역 exception_handler 에서 `{ error, code, details }` 로 변환
- **모든 모델에 created_at/updated_at** — `TimeStampedModel(auto_now_add/auto_now)` 상속 강제 (LESSON-003)
- **`USE_TZ = True` 고정** — naive datetime 금지 (LESSON-004)
- **FK 는 `on_delete` 의도적 선택** — CASCADE/PROTECT/SET_NULL, 기계적 CASCADE 금지

## components.persistence

- 추상 베이스:
  ```python
  class TimeStampedModel(models.Model):
      created_at = models.DateTimeField(auto_now_add=True)
      updated_at = models.DateTimeField(auto_now=True)

      class Meta:
          abstract = True
  ```
- FK 컬럼에 `db_index` (Django 는 FK 자동 인덱스 — 커스텀 필터 컬럼은 명시)
- `makemigrations` 후 **생성된 마이그레이션 수동 검토** — 적용된 마이그레이션 파일 수정 금지
- populated 테이블에 NOT NULL 컬럼 추가는 default/백필 순서로 (additive)

## components.interface.http

- 에러 응답 공통 래퍼: `{ error, code, details }` — DRF `EXCEPTION_HANDLER` 설정으로 단일화
- 페이지네이션 필수: `PageNumberPagination` 기본, `max_page_size` 상한 명시 (LESSON-002)
- ViewSet 은 얇게 — queryset 조립 + serializer 선택 + service 호출까지만
- `queryset.all()` 무제한 응답 금지 — 반드시 pagination 클래스 경유
- 인증 필요 엔드포인트: `permission_classes` 명시 (기본 `IsAuthenticated`, 공개는 의도 표시)

## components.auth

- 기본 `django.contrib.auth` — 커스텀 User 는 **첫 마이그레이션 전에** `AUTH_USER_MODEL` 결정
- API 인증: 개인 도구/내부용은 SessionAuth, 외부 공개 시 JWT (simplejwt) 로 승격
- SECRET_KEY 는 env 전용 — 기본값 금지

## components.core.logic

- `services.py`: view 밖의 비즈니스 로직. 트랜잭션 경계는 `transaction.atomic` 을 서비스 함수에
- 순수 계산은 별도 모듈로 분리해 단위 테스트, DB 접근 함수는 pytest-django 통합 테스트

## 설정 중앙화 (_base §10 구체화)

`django-environ` 으로 settings 에 집중:

```python
# config/settings/base.py
import environ

env = environ.Env()

SECRET_KEY = env("SECRET_KEY")                      # env 전용 — 기본값 금지
DATABASES = {"default": env.db("DATABASE_URL")}

# 튜너블 (기본값 있음, env override 가능)
PAGINATION_DEFAULT_LIMIT = env.int("PAGINATION_DEFAULT_LIMIT", default=50)
PAGINATION_MAX_LIMIT = env.int("PAGINATION_MAX_LIMIT", default=500)

USE_TZ = True                                        # 고정 — 변경 금지
```

**원칙**:
- 비밀값 (SECRET_KEY, DATABASE_URL, 3rd-party 키) → env 전용, 기본값 금지 (_base §4)
- 튜너블 → settings 상수 + env override
- 매직 숫자 금지: view/service 안의 하드코딩 대신 settings 상수 참조

## 금지 사항

- view/serializer 안의 다중 모델 비즈니스 로직
- `except Exception: pass` — 반드시 `logger.exception` + 에러 응답
- `print()` — 반드시 `logger` 사용
- raw SQL 문자열 concat — ORM 또는 `cursor.execute(sql, params)`
- 적용된 마이그레이션 파일 수정
- `USE_TZ = False`, naive `datetime.now()` — `timezone.now()` 사용

## 검증 명령

```bash
cd backend
uv run pytest
uv run ruff check .
uv run mypy .
```
