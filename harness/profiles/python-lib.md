---
id: python-lib
name: Python Library / SDK
status: confirmed
extends: _base
version: 1
maintainer: harness-core

paths: [".", "packages/", "libs/"]
detect:
  files: [pyproject.toml]
  not_contains:
    pyproject.toml: ["fastapi", "django", "flask", "[project.scripts]", "console_scripts"]

components:
  - id: interface.sdk
    required: true
    skeleton_section: interface.sdk
    description: public API surface (__init__.py export)
  - id: core.logic
    required: true
    skeleton_section: core.logic
    description: 순수 로직 + 도메인 타입
  - id: errors
    required: true
    skeleton_section: errors
    description: 커스텀 예외 계층 (LibError)
  - id: configuration
    required: false
    skeleton_section: configuration
    description: 런타임 설정 (선택)

skeleton_sections:
  required: [overview, stack, interface.sdk, core.logic, errors, tasks, notes]
  optional: [requirements, configuration, integrations]
  order: [overview, requirements, stack, configuration, errors, interface.sdk, core.logic, integrations, tasks, notes]

toolchain:
  install: "uv sync"
  test: "uv run pytest tests/ --rootdir=."
  lint: "uv run ruff check src/"
  type: "uv run pyright src/"
  format: "uv run ruff format src/ tests/"

whitelist:
  runtime:
    - pydantic
    - typing-extensions
  dev:
    - pytest
    - pytest-mock
    - hypothesis
    - ruff
    - pyright
    - mkdocs
    - mkdocs-material
    - mkdocstrings
  prefix_allowed: []

file_structure: |
  <repo>/
    pyproject.toml
    README.md
    CHANGELOG.md
    LICENSE
    src/<pkg>/
      __init__.py               # public API export (여기만 public)
      _internal/                # private — 밑줄 prefix
        <module>.py
      types.py                  # 공개 타입 정의
      errors.py                 # 예외 계층
      <feature>.py
    tests/
      conftest.py
      test_<feature>.py         # 공개 API 경계 테스트
      test_types.py
    docs/                       # mkdocs (선택)

provides_capabilities:
  - sdk_surface

gstack_mode: manual
gstack_recommended:
  before_design: [office-hours]
  after_design: [plan-eng-review]      # API 계약이 핵심 — 필수
  after_build: [review]
  before_ship: []
  after_ship: [document-release]        # CHANGELOG/README 동기화
  # retro 선택

lessons_applied: []
---

# Python Library / SDK Profile

## 핵심 원칙

- **Semver 엄수** — Breaking change = MAJOR 증가
- **public/private 경계** — `__init__.py` export만 public, 나머지는 private
- **타입 힌트 100%** — pyright strict, 공개 API는 `.pyi` stub 고려
- **README에 설치 + 최소 사용 예시** 필수
- **모든 public 함수 docstring** — 파라미터/반환/예외 명시
- **Deprecation 정책**: `@deprecated` + MAJOR 1회 건너뛰고 삭제

## components.interface.sdk

- `src/<pkg>/__init__.py`에서 public API를 명시적으로 export:
  ```python
  from <pkg>.feature import do_something, Feature
  from <pkg>.types import Options, Result
  from <pkg>.errors import LibError, ValidationError

  __all__ = [
      "do_something",
      "Feature",
      "Options",
      "Result",
      "LibError",
      "ValidationError",
  ]
  ```
- 내부 구현은 `_internal/` 디렉토리에 두고 public API는 얇은 facade 유지
- 타입 정의는 `types.py`에 한 곳으로 모음 (외부 import 경로 안정)

## components.core.logic

- 불변 데이터 구조 우선 (frozen dataclass, Pydantic `frozen=True`)
- 순수 함수 — 부작용 최소화
- Property-based test (hypothesis) 적극 사용 — 엣지케이스 자동 탐색

## components.errors

- 베이스 예외: `LibError(Exception)` — 라이브러리 모든 에러의 공통 조상
- 사용자는 `except LibError:` 하나로 모든 예외 포착 가능해야 함
- 내부 에러 메시지에 시크릿/경로 노출 금지

## 테스트 전략

- public API 경계 테스트 (사용자가 쓰는 방식 그대로)
- 100% 커버리지 목표 (라이브러리는 의존성이기 때문)
- 예외 경로 명시적 테스트: `with pytest.raises(LibError): ...`

## 배포

- **PyPI**: `uv build && uv publish` 또는 `python -m build && twine upload`
- 태그 push 시 GitHub Actions로 자동 배포
- 태그 규칙: `v<MAJOR>.<MINOR>.<PATCH>`

## 금지 사항

- 런타임 import (circular 방지 목적이면 설계 재검토)
- 모듈 레벨 side effect (네트워크/파일 접근 / 전역 상태 변경)
- 사용자에게 noisy logging (라이브러리는 기본 quiet, logger handler 사용자 제공)
- public API 시그니처 변경 (MINOR/PATCH에서)

## 검증 명령

```bash
uv run pytest tests/ --rootdir=. --cov=src
uv run ruff check src/
uv run pyright src/
```
