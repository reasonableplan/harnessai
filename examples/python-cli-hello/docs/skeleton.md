# Project Skeleton — hello-cli

## 1. 프로젝트 개요

<!-- TODO /ha-design: fill this section -->

- **프로젝트명**: hello-cli
- **한 줄 설명**: _(to be filled by Architect)_
- **핵심 사용자 가치**: _(to be filled)_


## 2. 기술 스택

<!-- TODO /ha-design: fill this section -->

### 런타임 / 언어
- Python 3.12+

### 허용 라이브러리 (python-cli whitelist)
- click, rich, platformdirs, pydantic, tomli, tomli-w


## 3. 에러 핸들링

<!-- TODO /ha-design: fill this section -->

### Exit codes
- `0`: success
- `1`: general failure
- `2`: user input error (click default)
- `3`: internal processing failure


## 4. CLI 커맨드

<!-- TODO /ha-design: fill this section -->

### Entry point
- Command: `hello`
- Module: `src/hello_cli/cli.py` (click group)


## 5. 도메인 로직

<!-- TODO /ha-design: fill this section -->

### 핵심 비즈니스 규칙
_(to be filled — pure functions in `core/`)_


## 6. 태스크 분해

<!-- TODO /ha-plan: this section is filled by Orchestrator -->

### Phase 1 — MVP
| ID | agent | deps | description | status |
|----|-------|------|-------------|--------|
| _(to be filled)_ | | | | |


## 7. 구현 노트

<!-- TODO /ha-design: fill this section -->

- Test strategy: _(to be filled — pytest + click.testing.CliRunner)_
- Logging: `logging` stdlib, INFO to stderr
