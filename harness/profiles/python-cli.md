---
id: python-cli
name: Python CLI Tool
status: confirmed
extends: _base
version: 1
maintainer: harness-core

# NOTE: "backend/" 제외 — CLI 가 backend/ 에서 매칭되면 plan 의 profile path 가
# backend/ 로 기록되고 ha-verify cwd 가 어긋나 (루트 tests/ 프로젝트에서) 가짜
# FAIL 이 verify_history 에 남는다. backend/ 는 서버 프로파일 (fastapi/nestjs) 영역.
paths: [".", "cli/", "packages/cli/", "apps/cli/", "tools/"]
detect:
  files: [pyproject.toml]
  contains_any:
    pyproject.toml: ["[project.scripts]", "console_scripts", "entry_points"]
  not_contains:
    pyproject.toml: ["fastapi", "django", "flask"]

components:
  - id: interface.cli
    required: true
    skeleton_section: interface.cli
    description: click 커맨드 그룹 + 서브커맨드 모듈
  - id: core.logic
    required: true
    skeleton_section: core.logic
    description: 순수 함수 (core/) + I/O 분리 (io/)
  - id: configuration
    required: false
    skeleton_section: configuration
    description: 환경변수 + 설정 파일 로드 (platformdirs)
  - id: persistence
    required: false
    skeleton_section: persistence
    description: sqlite3 또는 JSON 파일 (상태 영속 필요 시)
  - id: errors
    required: true
    skeleton_section: errors
    description: click.ClickException 계층 + exit code

skeleton_sections:
  required: [overview, stack, errors, interface.cli, core.logic, tasks, notes]
  optional: [requirements, configuration, persistence, integrations]
  order: [overview, requirements, stack, configuration, errors, interface.cli, core.logic, persistence, integrations, tasks, notes]

toolchain:
  install: "uv sync"
  test: "uv run pytest tests/ --rootdir=."
  lint: "uv run ruff check src/"
  type: "uv run pyright src/"
  format: "uv run ruff format src/ tests/"

whitelist:
  runtime:
    - click
    - rich
    - platformdirs
    - pydantic
    - tomli
    - tomli-w
  dev:
    - pytest
    - pytest-mock
    - ruff
    - pyright
  prefix_allowed: []

file_structure: |
  <repo>/
    pyproject.toml
    .env.example                # (있다면)
    src/<pkg>/
      __init__.py
      __main__.py               # python -m <pkg>
      cli.py                    # click 그룹
      commands/
        __init__.py
        <cmd_a>.py
        <cmd_b>.py
      core/                     # 순수 함수 — I/O 금지
        <domain>.py
      io/                       # 파일/네트워크 I/O
        config.py               # 설정 로드
        storage.py              # 로컬 저장
      errors.py                 # ClickException 계층
    tests/
      conftest.py
      test_cli.py               # CliRunner
      test_core/
      test_io/

provides_capabilities:
  - cli_entrypoint
  - env_config

gstack_mode: manual
gstack_recommended:
  after_design: [plan-eng-review]
  after_build: [review]
  before_ship: []               # CLI는 QA 생략 가능
  after_ship: []                # retro 선택

lessons_applied:
  - LESSON-010   # 에러 처리 형식 통일 (CLI: stderr + exit code)
  - LESSON-012   # 실행 명령어 명시 (entrypoint 필수)
  - LESSON-018   # 상수 정의 범위 vs 실제 사용 범위 불일치 (dead 상수)
  - LESSON-019   # 외부 명령 stderr → 사용자 친화 메시지 번역
  - LESSON-020   # 진행 표시 [N/M] 실제 작동 — 껍데기 금지
---

# Python CLI Tool Profile

## 핵심 원칙

- **엔트리포인트 프레임워크는 click** — argparse 금지. Typer도 click 기반이라 OK.
- **I/O와 로직 분리** — core/ (pure) vs io/ (impure) 파일 레벨 분리
- **`print()` 금지** — `click.echo()` 또는 rich 사용
- **`sys.exit()` 금지** — `click.ClickException` 또는 `click.Abort` 사용
- **에러는 stderr로, 결과는 stdout으로** — 파이프 호환성

## components.interface.cli

- click 그룹 + 서브커맨드 패턴:
  ```python
  # src/<pkg>/cli.py
  import click
  from .commands import cmd_a, cmd_b

  @click.group()
  @click.version_option()
  def app():
      """<한 줄 설명>"""

  app.add_command(cmd_a.run)
  app.add_command(cmd_b.run)
  ```
- 테스트: `from click.testing import CliRunner`
  ```python
  def test_cmd_a():
      runner = CliRunner()
      result = runner.invoke(app, ["cmd-a", "--foo=1"])
      assert result.exit_code == 0
      assert "expected" in result.output
  ```
- 에러 exit code:
  - `0`: 성공
  - `1`: 일반 실패
  - `2`: 사용자 입력 오류 (click 기본)
  - `3`: 내부 처리 실패

## components.core.logic

- `core/` 디렉토리의 모든 함수는 순수 — 파일/네트워크 접근 금지
- 타입 힌트 필수 (pyright strict)
- Pydantic v2로 boundary 입력 검증
- 테스트 커버리지 ≥ 90%

## components.configuration (optional)

- 설정 파일 위치: `platformdirs.user_config_dir(<app_name>)`
- 형식: TOML (`tomli` 로드, `tomli-w` 저장)
- 환경변수 우선: `env > config file > defaults`
- 비밀값(API 토큰)은 env만 (config 파일에 저장 금지)

## components.persistence (optional)

- 표준 `sqlite3` 또는 `duckdb` (대용량 분석 시)
- 위치: `platformdirs.user_data_dir(<app_name>)`
- 테스트: `tmp_path` fixture로 격리

## 설정 중앙화 (_base §10 구체화)

하드코딩 상수 3개 이상이면 다음 중 하나로 중앙화:

- **코드 내부 상수** (backoff, timeout, 레이어 이름 등) → `core/config.py` 모듈 단일 소스
  ```python
  # src/<pkg>/core/config.py
  from dataclasses import dataclass

  @dataclass(frozen=True)
  class Config:
      backoff_seconds: tuple[float, ...] = (1.0, 2.0)
      max_retries: int = 2
      max_file_lines: int = 2000
      skip_dirs: frozenset[str] = frozenset({".git", "node_modules", ".venv"})
  ```
- **사용자 튜너블** (모델명, 비용 단가) → `pyproject.toml [tool.<name>]` 섹션
  ```toml
  [tool.hijack]
  default_model = "claude-sonnet-4-6"
  cost_per_input_token = 3e-6
  ```
- **런타임 환경값** (API 키, 엔드포인트) → 환경변수 (§4 보안 규칙에 따름)
- **사용자 상태** (세션/캐시) → `platformdirs.user_data_dir(<app_name>)`

**LESSON-018 연결**: 상수 컬렉션(tuple/list) 정의 시 소비 루프와 길이 일치시킬 것. 또는 컬렉션 전체를 `for x in CONFIG.backoff_seconds:` 로 순회.

## 금지 사항

- `argparse` — click 사용
- `print()` — click.echo/secho 또는 rich
- `sys.exit(n)` — ClickException(...).exit_code 사용
- 전역 상태 (module-level mutable) — context에 담아 전달
- core/에서 파일/네트워크 I/O

## 검증 명령

```bash
uv run pytest tests/ --rootdir=.
uv run ruff check src/
uv run pyright src/
```
