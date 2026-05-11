---
id: claude-skill
name: Claude Skill (Meta)
status: confirmed
extends: _base
version: 1
maintainer: harness-core

paths: [".", "skills/"]
detect:
  # 자동 감지 어려움 — /ha-init에서 사용자 설명으로 수동 선택 주 경로
  # 감지 보조: ~/.claude/skills/<name>/SKILL.md 구조
  files: [SKILL.md]

components:
  - id: interface.cli
    required: true
    skeleton_section: interface.cli
    description: 스킬 호출 인터페이스 (/<skill-name> 커맨드 + args)
  - id: core.logic
    required: true
    skeleton_section: core.logic
    description: SKILL.md 본문 — 프롬프트/지침 텍스트 + bash 흐름
  - id: configuration
    required: false
    skeleton_section: configuration
    description: allowed-tools, model 지정 등 frontmatter

skeleton_sections:
  required: [overview, interface.cli, core.logic, tasks, notes]
  optional: [requirements, configuration, errors]
  order: [overview, requirements, interface.cli, configuration, core.logic, errors, tasks, notes]

toolchain:
  install: null
  test: null
  lint: null
  type: null
  format: null

whitelist:
  runtime: []
  dev: []
  prefix_allowed: []

file_structure: |
  ~/.claude/skills/<skill-name>/
    SKILL.md                  # 본체 — YAML frontmatter + Markdown 본문
    (선택)
    templates/                # 스킬이 생성/참조하는 템플릿
    scripts/                  # 스킬이 호출하는 bash 스크립트

provides_capabilities: []

gstack_mode: manual
gstack_recommended:
  after_design: [plan-eng-review]
  after_build: [review]
  # 스킬은 QA/ship/canary 없음 — 로컬 파일 시스템 변경만

lessons_applied: []
---

# Claude Skill Profile (Meta)

"Claude Code 스킬을 만드는 프로젝트" 타입. SKILL.md 파일을 Claude Code가 읽고 실행하는 구조.

## 핵심 원칙

- **SKILL.md는 프롬프트 + 실행 흐름**  — 코드가 아니라 LLM 지침
- **YAML frontmatter 필수**: `name`, `description`, `allowed-tools`
- **Manual trigger 명시 필요**: description 첫 줄에 "MANUAL TRIGGER ONLY" 추가하면 자동 발동 방지
- **한 스킬 = 한 목적**  — 기능 여러 개면 스킬을 쪼갠다
- **재현 가능성**: 스킬 실행 결과는 결정론적이어야. 대화 상태에 의존하면 안 됨

## SKILL.md 스키마

```markdown
---
name: <스킬 ID — slash 없이>
description: <Claude가 매칭에 쓰는 설명 — 한 줄, 트리거 키워드 포함>
allowed-tools:                    # Claude가 이 스킬 안에서 쓸 수 있는 툴
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - AskUserQuestion
  - Skill                         # 다른 스킬 호출 (선택)
model: sonnet | opus | haiku      # (선택)
---

# <Skill Title>

## 역할 / 목적

<한 문단>

## 실행 순서

### 1. <단계 이름>
<지침 — 평문 + 코드 블록>

### 2. <단계 이름>
...

## 금지 사항 / 게이트

- <실수 방지 규칙>

## 출력 형식

<Claude가 최종적으로 출력할 형태>
```

## components.interface.cli

스킬의 "인터페이스"는 사용자가 입력하는 slash 커맨드:
- 커맨드: `/<name>`
- 인자 (optional): 슬래시 뒤 자유 텍스트 (`$ARGUMENTS` 변수로 접근)

예시:
```
/my-skill arg1 arg2
```
→ SKILL.md 안에서 `$ARGUMENTS`를 사용자 입력으로 사용

## components.core.logic

- SKILL.md 본문 = LLM에 전달되는 지침
- 코드 블록은 "예시" 또는 "이 bash 스크립트를 실행하라"로 해석됨
- 외부 파일(templates/, scripts/)을 참조할 때는 **절대 경로** 또는 `$HOME` 기반 경로

## components.configuration

frontmatter의 `allowed-tools` 설정:
- 최소 권한 원칙 — 필요한 툴만 나열
- `Write` 권한은 파일 생성이 명확할 때만
- `Bash` 권한 주면 허용할 명령 범위를 스킬 본문에 명시

## 테스트 / 검증

- 자동 테스트 어려움 — Claude Code에서 실제 실행해서 동작 확인
- `harness validate` 가 frontmatter 스키마 체크 (name, description, allowed-tools 존재)
- 최소 수동 테스트:
  1. 스킬 호출: `/<name>`
  2. 기대 출력 확인
  3. 엣지: 인자 없이, 잘못된 인자, 중복 실행

## 금지 사항

- **프롬프트에 비밀값 하드코딩** — 사용자에게 받거나 env 참조
- **부작용 큰 명령 무승인** — `rm -rf`, `git push --force` 등은 반드시 사용자 확인
- **다른 스킬 호출을 과용** — `Skill` tool은 용도 명확할 때만
- **애매한 description** — Claude가 매칭 실패 → 스킬 발동 안 됨

## 공개 (선택)

- `~/.claude/skills/` 에 두면 자신만 사용
- oh-my-claudecode 같은 플러그인으로 배포하려면 별도 저장소
- 커뮤니티 스킬은 보통 README에 설치 방법 + 스크린샷 포함

## 검증 명령

```bash
# 수동 검증
bash -n ~/.claude/skills/<name>/SKILL.md  # (Markdown이라 shell syntax 없지만, $ARGUMENTS 등 참조 확인)
harness validate --profile claude-skill ~/.claude/skills/<name>/SKILL.md
```
