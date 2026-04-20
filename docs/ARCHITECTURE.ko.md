# HarnessAI Architecture

🌐 [English](ARCHITECTURE.md) · **한국어**

**대상 독자**: 시스템 구조를 30분 안에 이해하고 싶은 기여자 · 포트폴리오 리뷰어 · 미래의 나.

**한 줄 요약**: *프로파일 기반 멀티 에이전트 오케스트레이션*. 스택별 규칙을 선언하고, 에이전트들이 그 규칙을 지켜서 코드를 짠다. 벗어나면 게이트가 차단한다.

---

## 1. 전체 구조

```
┌──────────────────────────────────────────────────────────────────────┐
│                           사용자 (CLI)                               │
│  /ha-init → /ha-design → /ha-plan → /ha-build → /ha-verify → /ha-review │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                 ┌──────────────────┼──────────────────┐
                 ▼                  ▼                  ▼
        ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
        │  프로파일    │   │  skeleton    │   │  plan_manager│
        │  (스택 규칙) │   │  (계약서)    │   │  (상태 전이)  │
        └──────────────┘   └──────────────┘   └──────────────┘
                 │                  │                  │
                 └──────────────────┼──────────────────┘
                                    ▼
                ┌──────────────────────────────────────┐
                │  7개 에이전트 (Claude CLI subprocess) │
                │  Architect/Designer/Orchestrator/    │
                │  Backend Coder/Frontend Coder/       │
                │  Reviewer/QA                         │
                └──────────────────────────────────────┘
                                    │
                                    ▼
                ┌──────────────────────────────────────┐
                │  품질 게이트                         │
                │  · 보안 훅 6개                       │
                │  · ai-slop (LESSON-018 포함) 7패턴   │
                │  · 테스트 분포 체크                  │
                │  · skeleton 정합성 (harness integrity)│
                └──────────────────────────────────────┘
```

핵심 발상은 **"선언 → 생성 → 검증"의 닫힌 루프**. 사용자가 원하는 것을 skeleton(계약서) 에 선언하고, 에이전트가 생성하고, 게이트가 계약 위반을 차단한다.

---

## 2. 프로파일 시스템

### 왜 프로파일?

v1은 `fastapi / nextjs / react-native / electron` 4개 스택을 하드코딩했다. 새 스택(Python CLI, Python lib, Claude Skill 등)이 생길 때마다 구현 스킬(`/my-api`, `/my-ui`...) 을 포크해야 했다. 유지보수 불가능.

v2는 **프로파일** 로 추상화했다. 한 파일(`<profile>.md`)이 스택 하나의 모든 규칙을 담는다.

```
~/.claude/harness/profiles/
  _base.md          # 공통 원칙 11개 (테스트·git·에러·보안·코드 품질·
                    #                 의존성·타입·설정 중앙화·2대 원칙)
  _registry.yaml    # 감지 규칙 (어떤 파일 있으면 어느 프로파일)
  fastapi.md        # FastAPI 백엔드 규칙
  react-vite.md     # React + Vite 프런트엔드
  python-cli.md     # Python CLI (click 기반)
  python-lib.md     # Python 라이브러리
  claude-skill.md   # Claude Code 스킬
```

### 프로파일 파일 구조

각 프로파일은 YAML frontmatter + Markdown body:

```yaml
---
id: fastapi
name: FastAPI Backend
extends: _base           # 상속 — _base 원칙 자동 적용

paths: [".", "backend/", "apps/api/"]    # 감지 대상 경로
detect:
  files: [pyproject.toml]
  contains: { pyproject.toml: ["fastapi"] }

components:                # 이 프로파일이 갖춰야 할 컴포넌트
  - { id: persistence,     required: true,  skeleton_section: persistence }
  - { id: interface.http,  required: true,  skeleton_section: interface.http }
  - { id: auth,            required: false, skeleton_section: auth }
  ...

skeleton_sections:         # skeleton.md 에 어느 섹션 포함 필수/선택
  required: [overview, stack, errors, interface.http, core.logic, tasks, notes]
  optional: [requirements, configuration, auth, persistence, ...]
  order:    [...20개 ID 순서...]

toolchain:                 # /ha-verify 가 실행할 명령
  test: "uv run pytest tests/"
  lint: "uv run ruff check src/"
  type: "uv run pyright src/"

whitelist:                 # security_hooks 가 차단할 외부 의존성
  runtime: [fastapi, uvicorn, sqlalchemy, ...]
  dev:     [pytest, ruff, pyright]

lessons_applied:           # 이 프로파일에 강제 적용할 과거 실수 목록
  - LESSON-001   # query params snake_case
  - LESSON-018   # dead 상수
  ...
---

# FastAPI Backend Profile

## 핵심 원칙
- 라우터는 DB 직접 접근 금지 — service 레이어 경유
- HTTP 500 내부 에러 미노출
- ...
```

### 감지 흐름

```
사용자: /ha-init (프로젝트 루트에서)
  │
  ▼
profile_loader.detect(project_root)
  │  ├─ _registry.yaml 로드
  │  ├─ 각 프로파일의 paths × detect rule 매칭
  │  │   예: backend/pyproject.toml 에 "fastapi" 문자열 있으면 → fastapi 프로파일
  │  └─ 모노레포는 복수 매칭 (backend/ → fastapi + frontend/ → react-vite)
  │
  ▼
ProfileRef[] (profile_id + path) 리스트
  │
  ▼
harness-plan.md 의 profiles 필드에 기록
```

---

## 3. Skeleton 시스템

### Skeleton 이란?

프로젝트의 **계약서**. "이 프로젝트는 무엇을 갖춰야 하는가"를 20개 표준 섹션으로 명세.

```
20개 표준 섹션 ID:
  overview         project 정체
  requirements     기능 요구사항
  stack            기술 스택
  configuration    환경/설정
  errors           에러 처리 규약
  auth             인증
  persistence      DB 스키마
  integrations     외부 연동
  interface.http   REST API
  interface.cli    CLI 명령
  interface.ipc    IPC (electron)
  interface.sdk    SDK 경계
  view.screens     화면
  view.components  컴포넌트
  state.flow       상태 흐름
  core.logic       순수 함수 로직
  observability    로깅/메트릭
  deployment       배포
  tasks            태스크 분해
  notes            메모
```

### 조립 방식

각 섹션은 `harness/templates/skeleton/<id>.md` 조각 파일로 저장. 프로파일이 요구하는 섹션만 골라서 조립:

```
skeleton_assembler.py::assemble()
  │
  ├─ 1. profile.skeleton_sections.order 를 확인
  ├─ 2. 각 section_id 에 대해:
  │     - {project}/.claude/harness/templates/skeleton/<id>.md  (local override)
  │     - ~/.claude/harness/templates/skeleton/<id>.md          (global)
  ├─ 3. frontmatter 제거, {{section_number}} → 실제 번호 치환
  └─ 4. 연결 → skeleton.md
```

### ```filesystem 블록 규약

/ha-design 이 skeleton 을 채울 때, 파일 구조를 아래 블록으로 선언:

````markdown
```filesystem
src/myapp/
  cli.py
  core/
    logic.py
tests/
  test_cli.py
```
````

이것이 **harness integrity 의 검증 대상**. 선언한 경로가 실재 파일시스템에 존재해야 `/ha-verify` 통과. 템플릿 플레이스홀더 (`<pkg>`, `<cmd_a>`) 가 남아있어도 실패.

---

## 4. State Machine — harness-plan.md

`docs/harness-plan.md` 는 프로젝트 상태의 Single Source of Truth. YAML frontmatter 에 상태 기록.

```
                                       ┌─ (reject) ──┐
                                       │             │
                                       ▼             │
init ──▶ designed ──▶ planned ──▶ building ──▶ built ──▶ verified ──▶ reviewed ──▶ shipped
         △                                                                         │
         │                                                                         │
         └──────────── (retro) ────────────────────────────────────────────────────┘
```

| 전이 | 트리거 | 담당 |
|---|---|---|
| init → designed | `/ha-design` 완료 | Architect + Designer 에이전트 |
| designed → planned | `/ha-plan` 완료 | Orchestrator |
| planned → building | 첫 `/ha-build` 시작 | Backend/Frontend Coder |
| building → built | 모든 태스크 done | plan_manager (자동) |
| built → verified | `/ha-verify` PASS | toolchain + harness integrity |
| verified → reviewed | `/ha-review` APPROVE | Reviewer 에이전트 |
| reviewed → shipped | `/ship` (gstack) | — |
| * → building (reject) | `/ha-review` REJECT | 재구현 필요 |

plan 파일은 `plan_manager.py::PlanManager` 가 로드/저장/전이. 스키마는 `harness validate --plan` 으로 강제.

---

## 5. 스킬 ↔ 에이전트 매핑

```
/ha-init        → (에이전트 X) profile_loader + skeleton_assembler
/ha-design      → Architect + Designer (ACCEPT/CONFLICT 협의 최대 3회)
/ha-plan        → Orchestrator
/ha-build       → Backend Coder / Frontend Coder (태스크 agent 필드로 결정)
/ha-verify      → (에이전트 X) toolchain + harness integrity 실행
/ha-review      → Reviewer (보안 훅 + LESSON + ai-slop + 테스트 분포)
/ha-deepinit    → (기존 코드베이스용) 전 7개 에이전트 분석
```

에이전트 정의는 `backend/agents/<agent>/CLAUDE.md` 에 시스템 프롬프트로 저장. 실행은 `runner.py::AgentRunner` 가 Claude CLI subprocess 로.

### 모델 선택

| 스킬 | 모델 | 이유 |
|---|---|---|
| /ha-build | Sonnet | 코드 작성 속도/비용 (단순 실행) |
| /ha-verify | Sonnet | 기계적 명령 실행 + 파싱 |
| /ha-init, /ha-design, /ha-plan, /ha-review, /ha-deepinit | Opus | 판단·설계·종합 리뷰 |

---

## 6. 품질 게이트

### 6.1 보안 훅 6개 (`security_hooks.py`)

`Orchestra` 가 에이전트 출력에 강제:

| 훅 | 검사 |
|---|---|
| check_dependency | 프로파일 whitelist 외 의존성 추가 금지 |
| check_path_traversal | `../` 등 경로 상향 참조 차단 |
| check_secret_leak | 토큰/키/비밀번호 하드코딩 감지 |
| check_cli_arg_secret | CLI 인자로 시크릿 전달 금지 |
| check_sql_injection | raw SQL concat 차단 |
| check_xml_delimiter | 에이전트 프롬프트의 사용자 입력 분리 |

프로파일별 whitelist 는 `SecurityHooks.from_profile(profile)` 로 동적 주입.

### 6.2 ai-slop 훅 — 7번째 (LESSON-018 통합)

`/ha-review` 가 git diff 에 정규식 패턴 매칭:

| 패턴 | 심각도 |
|---|---|
| 장황한 docstring (>200자) | WARN |
| 의미 없는 try/except (re-raise만) | WARN |
| 신규 TODO/FIXME (이슈 번호 없음) | WARN |
| unused 함수 prefix (`_unused_`) | WARN |
| 임시 pass 흔적 | BLOCK |
| **dead 상수 (LESSON-018)** — 튜플/리스트 길이 ≥ 3 + `max_retries=1\|2` 근접 | **WARN** |

`_strip_non_code_from_diff` 가 docs/templates placeholder 를 오탐에서 제외.

### 6.3 테스트 분포 체크 (신규, A6)

`/ha-review` 가 프로파일별로:

- **BLOCK**: src/ 모듈 존재 + 테스트 파일 0개
- **WARN**: 편차 10x 이상 (예: analyzer 43 tests vs generator 5 tests)

Python 은 AST `def test_*` 카운트, JS/TS 는 `describe/it/test` 정규식. 모노레포는 profile.path 별 독립 집계.

### 6.4 skeleton 정합성 게이트 (신규, A5)

`/ha-verify` 가 toolchain 전에 `harness integrity` 호출:

- skeleton.md ` ```filesystem ` 블록 선언 경로가 실재 FS 에 존재?
- 템플릿 플레이스홀더 (`<pkg>`, `<cmd_a>`) 미치환 잔존?

개행 보존 치환으로 라인 번호 정확히 보고 (LESSON-018 내부 구현 품질과 일관).

---

## 7. LESSON 시스템

`backend/docs/shared-lessons.md` 에 과거 실수 21개 (LESSON-001 ~ LESSON-021). 각 프로파일의 `lessons_applied` 필드가 적용 대상 지정.

적용 메커니즘:
- **텍스트 참조** (default): Reviewer 에이전트가 프롬프트에 포함해 판단
- **자동 감지** (LESSON-018 만 현재): ai-slop 정규식 패턴에 통합
- **게이트 강제** (LESSON-021): `/ha-build` 의 toolchain 게이트가 `done` 마킹 전 test+lint+type 강제

LESSON 추가는 수동 (`backend/docs/shared-lessons.md` 직접 편집 + 해당 프로파일 `lessons_applied` 갱신). 자동 학습 (`/ha-review` 반복 패턴 → LESSON 후보) 은 TODOS.md 에 등록된 향후 작업.

---

## 8. 레포 구조

```
<repo>/
  backend/
    agents/               에이전트 시스템 프롬프트 (CLAUDE.md)
      architect/, designer/, orchestrator/, backend_coder/,
      frontend_coder/, reviewer/, qa/
    agents.yaml           에이전트 운영 설정 (model, timeout, on_timeout)
    docs/
      shared-lessons.md   21 LESSONs
      skeleton.md         (실행 시 생성됨)
      harness-plan.md     (실행 시 생성됨)
    src/
      main.py             FastAPI 서버 (dashboard)
      dashboard/          REST + WebSocket
      orchestrator/
        orchestrate.py          Orchestra + assemble_skeleton_for_profiles
        profile_loader.py       프로파일 로드/상속/감지
        skeleton_assembler.py   조각 조립 + find_placeholders
        plan_manager.py         상태 전이
        context.py              섹션 ID 매핑 + extract_section_by_id
        runner.py               AgentRunner (타임아웃/재시도)
        security_hooks.py       보안 훅 6개 + from_profile
        providers/              Claude CLI / 향후 Gemini/local
    tests/                357 pytest
      orchestrator/
      dashboard/
      skills/              신규 — harness integrity + 테스트 분포 회귀 방지

  harness/                ~/.claude/harness 소스 이관 (B8)
    bin/harness           CLI (validate + integrity 서브커맨드)
    profiles/             _base + 5개 스택 프로파일 + _registry.yaml
    templates/skeleton/   20개 조각

  skills/                 ~/.claude/skills/ha-* 소스 이관 (B8)
    ha-init/, ha-design/, ha-plan/, ha-build/,
    ha-verify/, ha-review/, ha-deepinit/
    _ha_shared/utils.py   공유 유틸 (HARNESS_AI_HOME 로드)

  install.sh              Unix/WSL 단일 명령 설치 (B8)
  install.ps1             Windows PowerShell (B8)
  tests/install/          install 스냅샷 테스트 (12 assertion)

  docs/
    ARCHITECTURE.md       이 문서
    harness-v2-design.md  작업 로그 (상세 설계)
    ... (20+ 기존 문서)
```

---

## 9. 설계 결정 (요약, ADR 상세는 후속 `docs/decisions/`)

| # | 결정 | 근거 |
|---|---|---|
| D1 | 데이터 공유 + 검증 CLI | 프로파일 스키마 drift 자동 감지 필요 |
| D2 | `~/.claude/harness/` 글로벌 + 프로젝트 로컬 override | 전역 규칙 + 프로젝트별 예외 허용 |
| D3 | `/my-*` 완전 삭제 → `/ha-*` (Phase 4a + 4b 완료 — [ADR-005](decisions/005-ha-skills-cut-over.md)) | 스킬 중복 유지 비용 |
| D4 | `docs/harness-plan.md` 단일 파일 + YAML frontmatter 상태 | 사람이 직접 편집 가능, git 친화 |
| D5 | 프로파일이 `gstack_mode` 선언 (auto/manual/prompt) | 스택별 CI/CD 정도 차이 |
| D6 | 섹션 ID 20개 표준 | 번호 기반보다 refactor-safe |

---

## 10. 확장 방법

### 새 스택 추가
1. `harness/profiles/<stack>.md` 작성 (frontmatter + 본문)
2. `harness/profiles/_registry.yaml` 에 감지 규칙 추가
3. `harness validate` 로 스키마 확인
4. (선택) 스택 특화 LESSON 을 `shared-lessons.md` 에 추가 + 프로파일 `lessons_applied` 등록

### 새 에이전트 역할 추가
1. `backend/agents/<role>/CLAUDE.md` 작성
2. `backend/agents.yaml` 에 `model`, `timeout_seconds`, `on_timeout` 등록
3. Orchestra 의 phase 파이프라인 (`orchestrate.py`) 에 역할 호출 지점 추가

### 새 게이트 추가
1. `ha-review/run.py::_check_*` 또는 `harness/bin/harness` 의 서브커맨드로 구현
2. 회귀 테스트 `backend/tests/skills/` 에 추가

---

**참고 문서**:
- `docs/harness-v2-design.md` — 이번 재설계의 상세 작업 로그 (1,270+ lines)
- `backend/docs/shared-lessons.md` — 20개 과거 실수 패턴
- `README.md` — 사용자 관점 소개
- `CLAUDE.md` — 구현 시 엄격 규칙 (현업 수준 품질 기준)
