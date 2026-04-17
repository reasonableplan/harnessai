# HarnessAI v2 — 전체 설계 문서

**상태**: Draft (리뷰 대기)
**작성일**: 2026-04-16
**목적**: 어떤 프로젝트에서도 HarnessAI를 적용할 수 있도록 프로파일 기반 아키텍처로 재설계. `/my-*` 스킬의 4개 스택 하드코딩 제약 제거. Orchestra(자동)와 `/ha-*`(수동) 두 실행 모드가 동일한 프로파일·템플릿을 공유.

---

## 1. 목적 및 원칙

### 1.1 목적
1. **어떤 프로젝트든 지원** — 웹앱/CLI/라이브러리/데스크탑/모바일/모노레포/스킬 자체/데이터 파이프라인/브라우저 확장 등.
2. **단일 진리의 원천 (SoT)** — 프로파일과 skeleton 조각은 `~/.claude/harness/`에 하나만 존재.
3. **Orchestra ↔ `/ha-*` 일관성** — 자동 파이프라인과 수동 파이프라인이 같은 프로파일을 읽는다.
4. **사용자 판단 존중** — 규모 tier 기반 자동 분류 금지. 사용자 설명 → Claude 판단 → 제안 → 대화 루프.

### 1.2 설계 원칙
- **스택 지식은 프로파일에** — 스킬 본체/Orchestra 코드에 `if stack == "fastapi"` 금지.
- **모노레포는 다중 프로파일** — composition/merge 로직 없이 경로별 매칭.
- **섹션은 ID로 참조** — 번호 하드코딩 금지.
- **파이프라인 상태는 파일 하나** — `docs/harness-plan.md` 단일 파일.
- **점진적 확장성** — 새 프로파일 추가 = 파일 1개. 스킬 본체 수정 0.
- **정확성 > 속도** — CLAUDE.md 대원칙 준수.

### 1.3 잠긴 결정사항 (변경 시 본 문서 개정 필요)

| ID | 결정 | 근거 |
|----|------|------|
| D1 | 데이터 공유(YAML/MD) + 검증 CLI `harness validate` | 단순함 + 스키마 오류 방지 |
| D2 | 글로벌(`~/.claude/harness/`) + 프로젝트 로컬 override | 80% 글로벌, 20% 커스텀 |
| D3 | `/my-*` 스킬 완전 삭제, `/ha-*`만 | 두 이름 혼란 방지 |
| D4 | `docs/harness-plan.md` 단일 파일 (YAML frontmatter로 상태) | 사람/기계 모두 읽기 쉬움 |
| D5 | 프로파일이 `gstack_mode: auto/manual/prompt` 선언 (기본 manual) | 프로젝트별 맞춤 |
| D6 | `~/.claude/harness/templates/skeleton/` 조각이 skeleton SoT | 중복 제거 |

---

## 2. 전체 아키텍처

```
┌───────────────────────────────────────────────────────────────────┐
│  ~/.claude/harness/  (GLOBAL defaults — 모든 프로젝트 공유)         │
│  ├─ profiles/                                                       │
│  │  ├─ _registry.yaml       감지 규칙 중앙화                          │
│  │  ├─ _base.md             모든 프로파일 공통 원칙                   │
│  │  ├─ fastapi.md           FastAPI 백엔드                           │
│  │  ├─ react-vite.md        React+Vite 프론트엔드                    │
│  │  ├─ nextjs.md            Next.js 풀스택                           │
│  │  ├─ python-cli.md        순수 Python CLI                          │
│  │  ├─ python-lib.md        Python 라이브러리/SDK                    │
│  │  ├─ electron.md          Electron 데스크탑                         │
│  │  ├─ react-native.md      RN/Expo 모바일                            │
│  │  └─ claude-skill.md      Claude 스킬 자체 만들기 (메타)            │
│  ├─ templates/                                                        │
│  │  └─ skeleton/            섹션 ID별 빈 템플릿 20개                  │
│  ├─ lessons/                                                          │
│  │  └─ shared-lessons.md    공용 LESSON (과거 실수 패턴)              │
│  └─ bin/                                                              │
│     └─ harness              검증 CLI (Python uvx 실행)                │
└───────────────────────────────────────────────────────────────────┘
            ▲                                    ▲
            │ resolve (로컬 없으면 글로벌)          │ read
            │                                    │
   ┌────────────────────┐              ┌────────────────────┐
   │ {project}/.claude/ │              │ {project}/docs/    │
   │   harness/         │              │  ├─ harness-plan.md│
   │   (optional)       │              │  ├─ skeleton.md    │
   │   ├─ profiles/     │              │  └─ tasks.md       │
   │   │   *.md         │              └────────────────────┘
   │   └─ lessons/      │                         ▲
   │       lessons-     │                         │ read/write
   │       {project}.md │                         │
   └────────────────────┘              ┌──────────┴──────────┐
            ▲                          │                      │
            │ read/write             MANUAL                 AUTO
            │                      (사용자 대면)          (Orchestra)
   ┌────────┴────────┐       ┌────────────────┐    ┌────────────────┐
   │  스킬 6개        │       │ /ha-init       │    │ Orchestra      │
   │                 │       │ /ha-design     │    │  ├─ Architect  │
   │                 │       │ /ha-plan       │    │  ├─ Designer   │
   │                 │       │ /ha-build      │    │  ├─ Orchestr'r │
   │                 │       │ /ha-verify     │    │  ├─ BE Coder   │
   │                 │       │ /ha-review     │    │  ├─ FE Coder   │
   │                 │       │                │    │  ├─ Reviewer   │
   │                 │       │                │    │  └─ QA         │
   └─────────────────┘       └────────────────┘    └────────────────┘
                                      │                      │
                                      └──────────┬───────────┘
                                                 ▼
                                   ┌──────────────────────────┐
                                   │  harness validate        │
                                   │  (공유 스키마 검증 CLI)    │
                                   └──────────────────────────┘
```

### 2.1 실행 모드 비교

| 측면 | Manual (`/ha-*`) | Automatic (Orchestra) |
|------|------------------|----------------------|
| 진입점 | 사용자가 스킬 실행 | `POST /api/command` 또는 CLI |
| LLM | Claude Code (대화형) | Claude CLI subprocess |
| 속도 | 사람 속도 | 기계 속도 (병렬) |
| 프로파일 읽기 | bash + LLM 판단 | Python `profile_loader.py` |
| skeleton 조립 | bash으로 조각 concat | Python `skeleton_assembler.py` |
| 상태 관리 | `harness-plan.md` frontmatter | `.orchestra/*.json` + harness-plan.md |
| 사용 시점 | 소규모/학습/커스터마이징 | 중규모/반복작업/자동화 |

**중요**: 두 모드 모두 같은 `~/.claude/harness/` 를 읽는다. 프로파일·템플릿 변경은 양쪽에 동시 반영된다.

---

## 3. 프로파일 시스템 명세

### 3.1 프로파일 파일 구조

경로: `~/.claude/harness/profiles/<id>.md` (또는 프로젝트 로컬 override).

```markdown
---
# ── 메타 ──────────────────────────────────────────────
id: <string, 파일명과 일치>                  # 예: "fastapi"
name: <string>                                # 예: "FastAPI Backend"
status: confirmed | draft                     # draft = 즉석 생성된 것
extends: <profile_id | null>                  # 상속 (기본 _base 암묵 상속)
version: <integer>                            # 프로파일 스키마 버전
maintainer: <string>                          # 작성자 (optional)

# ── 감지 ──────────────────────────────────────────────
# _registry.yaml이 주 감지 로직이지만, 자기 기술도 여기 둠
# (자가 문서화 + 프로젝트 로컬 override 시 사용)
# paths 는 top-level (detect 외부) — _registry.yaml 규칙과 구조 일치
paths: [<path>, ...]
detect:
  files: [<file>, ...]
  contains:      { <file>: [<substr>, ...] }
  contains_any:  { <file>: [<substr>, ...] }
  not_contains:  { <file>: [<substr>, ...] }

# ── 컴포넌트 타입 ─────────────────────────────────────
# 이 프로파일에서 생성하는 코드의 카테고리
components:
  - id: <component_id>                        # 예: "persistence"
    required: true | false
    skeleton_section: <section_id>            # 연결된 skeleton 섹션
    description: <one-liner>

# ── skeleton 구성 ─────────────────────────────────────
skeleton_sections:
  required: [<section_id>, ...]               # 반드시 포함
  optional: [<section_id>, ...]               # 조건부 포함
  order:    [<section_id>, ...]               # skeleton.md 최종 순서

# ── 검증 도구 ─────────────────────────────────────────
toolchain:
  install: <shell_command>
  test:    <shell_command>
  lint:    <shell_command>
  type:    <shell_command | null>             # 타입 시스템 없는 언어면 null
  format:  <shell_command | null>

# ── 의존성 화이트리스트 ──────────────────────────────
whitelist:
  runtime: [<package>, ...]
  dev:     [<package>, ...]
  prefix_allowed: [<prefix>, ...]             # 예: "@radix-ui/"

# ── 파일 구조 (LLM에 예시로 주입) ────────────────────
file_structure: |
  <indented tree>

# ── gstack 연동 ──────────────────────────────────────
gstack_mode: auto | manual | prompt           # 기본: manual
gstack_recommended:
  before_design: [<gstack_skill>, ...]
  after_design:  [...]
  before_build:  [...]
  after_build:   [...]
  before_ship:   [...]
  after_ship:    [...]

# ── LESSONs ──────────────────────────────────────────
lessons_applied: [<LESSON_ID>, ...]           # 이 프로파일에 적용되는 LESSON
---

# <Profile Name>

자유 형식 Markdown. 컴포넌트별 구현 원칙, 금지사항, 예시 코드 포함.

## components.<component_id>

(각 컴포넌트에 대해 구체 가이드)

## 금지 사항

(이 스택 특유의 anti-pattern)
```

### 3.2 `_registry.yaml` 상세 (이미 작성됨)

- 7개 기본 규칙 + `fallback.action: prompt_user`
- 매칭 연산자: `files` / `contains` / `contains_any` / `not_contains`
- `paths` 리스트로 모노레포 지원 — 각 경로마다 매칭 시도
- **중복 매칭 OK** — 각 매칭은 `{profile_id, path}` 튜플로 저장

### 3.3 프로파일 해석 우선순위

1. 프로젝트 로컬: `{project}/.claude/harness/profiles/<id>.md`
2. 글로벌: `~/.claude/harness/profiles/<id>.md`

로컬이 있으면 로컬 사용. 둘 다 있을 수 없음 (한쪽만 골라야 함 — merge 안 함).

### 3.4 상속 (`extends`)

- 모든 프로파일은 `_base.md` 를 암묵 상속
- 추가 상속은 명시적으로 `extends: <id>` 선언
- 재귀적 상속 허용 (A extends B extends _base)
- 순환 탐지 필수 (`harness validate` 가 검증)

상속 병합 규칙:
- `whitelist.*`: 리스트는 합집합
- `toolchain.*`: override (자식이 이김)
- `components`: 리스트 append (중복 id는 자식이 이김)
- `skeleton_sections.*`: 리스트 합집합

### 3.5 즉석 프로파일 생성 (draft → confirmed)

**생성 시점**: `/ha-init`에서 기존 프로파일 중 매칭 없음 + 사용자 설명이 명확할 때.

**절차**:
1. 사용자 설명 → Claude가 프로파일 생성
2. 저장 위치: **프로젝트 로컬** (`{project}/.claude/harness/profiles/<new-id>.md`)
3. `status: draft` 마킹 + 주석: `# DRAFT — 프로젝트 진행 중 실제 동작 확인 필요`
4. `harness validate` 로 스키마 검증

**승급 (draft → confirmed)**:
- `/ha-review` 단계에서 draft 프로파일 감지 시 사용자에게 질문:
  > "이 프로파일(<id>) 실제로 써보니 어땠어요? 글로벌로 승급할까요?"
- 승급 = 프로젝트 로컬 파일을 `~/.claude/harness/profiles/`로 복사 + `status: confirmed` 변경
- 승급 거부 = 프로젝트 로컬에 그대로 유지 (다음 프로젝트에선 재사용 안 됨)

---

## 4. skeleton 시스템 명세

### 4.1 섹션 ID 표준 (20개 — 변경 시 설계 개정)

| 섹션 ID | 제목 | 포함 조건 |
|---------|------|----------|
| `overview` | 프로젝트 개요 | 항상 |
| `requirements` | 기능 요구사항 | tiny 이상 |
| `stack` | 기술 스택 | tiny 이상 |
| `configuration` | 환경변수/피처 플래그/설정 | medium 이상 또는 env 존재 |
| `errors` | 에러 핸들링/코드 | small 이상 |
| `auth` | 인증/권한 | 다중 사용자 |
| `persistence` | DB/파일 스키마 | 상태 영속 |
| `integrations` | 3rd party API/OAuth/웹훅 | 외부 의존 있음 |
| `interface.http` | HTTP API | HTTP 서버 |
| `interface.cli` | CLI 커맨드 | CLI 엔트리포인트 |
| `interface.ipc` | IPC 채널 | Electron/데몬 |
| `interface.sdk` | export API | 라이브러리 |
| `view.screens` | 화면 목록 | UI 있음 |
| `view.components` | 컴포넌트 트리 | UI + small 이상 |
| `state.flow` | 상태 흐름 | 비즈니스 로직 복잡 |
| `core.logic` | 도메인 로직 | 항상 |
| `observability` | 로깅/모니터링 | large 이상 |
| `deployment` | 배포 설정 | large 이상 |
| `tasks` | 태스크 분해 | 항상 (`/ha-plan`이 채움) |
| `notes` | 구현 노트 | 항상 (`/ha-build`가 채움) |

"포함 조건"은 가이드. 실제 포함 여부는 프로파일 + `/ha-init` 판단 결과.

**특수 도메인 확장**: 데이터 파이프라인(`data.schema`), ML 훈련(`ml.experiments`), 인프라(`infra.topology`) 같은 특수 영역은 draft 프로파일이 **자체 섹션 선언 가능**. 표준 20개 + 프로파일별 확장이 기본 방침.

### 4.2 섹션 조각 파일 형식

경로: `~/.claude/harness/templates/skeleton/<section_id>.md`

```markdown
---
id: <section_id>
name: <섹션 제목>
required_when: always | has_users | has_storage | has_ui | manual
description: <한 줄>
---

## {{section_number}}. {{section_title}}

<빈 템플릿 + placeholder>

> 작성 가이드:
> - <Architect/Designer가 뭘 채워야 하는지>
> - <다른 섹션과의 연결 관계>

### 하위 섹션 (있으면)
...
```

### 4.3 조립 알고리즘

**`/ha-init`이 호출**:

```
입력: profile(들), 규모 판단, 조건부 포함 결정
출력: {project}/docs/skeleton.md

절차:
1. included_sections = []
   for profile in profiles:
       included_sections += profile.skeleton_sections.required
       for s in profile.skeleton_sections.optional:
           if condition_met(s):
               included_sections.append(s)
   dedupe(included_sections)

2. 프로파일의 order에 따라 재정렬
   (여러 프로파일일 때는 가장 주요한 프로파일의 order 사용)

3. for idx, section_id in enumerate(included_sections, 1):
       fragment_path = resolve_local_or_global(section_id)
       content = read(fragment_path)
       content = substitute(content, section_number=idx, section_title=...)
       append_to_output(content)

4. write(skeleton.md, output)
```

### 4.4 섹션 레퍼런스 규칙

- **금지**: "섹션 7 읽기", "섹션 6 참조"
- **허용**: "`persistence` 섹션 읽기", "`interface.http` 참조"
- 에이전트 프롬프트(`backend/agents/*/CLAUDE.md`)도 섹션 ID로 참조하도록 수정

### 4.5 Fragment 원칙 — Stack-neutral

Fragment는 **기술 스택에 독립적인 "질문 + 뼈대"** 여야 한다. 실제 프레임워크 특화 예시/구현 코드는 프로파일의 본문으로.

**금지 사항 (Fragment에 두면 안 됨)**:
- FastAPI, SQLAlchemy, Click, React 등 **특정 프레임워크 예시 코드**
- HTTP 상태 코드 목록 (해당 내용은 `interface.http` 내부로만)
- 언어별 예외 클래스 구체 이름 (예: `AuthException`, `ClickException`)
- 특정 라이브러리 import 문

**허용**:
- 섹션의 "무엇을 기술해야 하는가" 가이드 질문
- 범용 표 구조 (컬럼 헤더만)
- 플레이스홀더 (`<PROJECT_NAME>`, `<DOMAIN>_NNN`)
- 타 섹션/프로파일 본문 참조 (예: "세부 규격은 `interface.cli` 섹션")

**프로파일은 본문에**:
- 이 스택에서 컴포넌트별 실제 구현 예시
- 사용 프레임워크의 관용 패턴
- 금지 사항 (예: FastAPI에서 라우터 내 DB 직접 접근 금지)

**이유**: Fragment가 stack-biased면 "어떤 프로젝트든" 원칙이 무너진다. CLI 프로젝트에 HTTP 상태 코드가 섞여 들어오는 등 노이즈 발생 (PoC #B-2).

### 4.6 `required_when` 표준 Vocabulary

Fragment의 `required_when` 필드는 다음 표준 값만 허용. Validator가 강제.

**단일 조건**:
| 값 | 의미 |
|----|------|
| `always` | 무조건 포함 |
| `has.users` | 다중 사용자 개념 있음 |
| `has.storage` | 영속 상태(DB/파일) 있음 |
| `has.env_config` | 환경변수 또는 런타임 설정 |
| `has.external_deps` | 3rd party API/OAuth/웹훅 |
| `has.http_server` | HTTP 서버 운영 |
| `has.cli_entrypoint` | CLI 진입점 있음 |
| `has.ipc` | IPC 채널 (Electron/데몬) |
| `has.ui` | 화면/뷰 있음 |
| `has.complex_state` | 복잡한 상태 머신/비즈니스 로직 |
| `has.sdk_surface` | public API 노출 (라이브러리) |
| `has.production_concerns` | 운영/프로덕션 고려 대상 |
| `scale.small_or_larger` | 규모가 tiny 아님 |
| `scale.medium_or_larger` | 규모가 medium 이상 |
| `scale.large` | 규모가 large |

**AND 결합**: `+` 기호 — `has.ui + scale.small_or_larger`

**OR / NOT / 복잡한 부울 식 금지** — `/ha-init`의 판단을 단순 규칙으로 한정. 복잡한 조건이 필요하면 Claude의 판단에 맡기고 `always` + 본문 가이드로 표현.

**평가 주체**: `/ha-init`이 사용자 답변과 프로파일 정보로 조건 평가. 단순 포함 여부 결정이며 실제 UX는 Claude의 판단이 최종.

---

## 5. `/ha-*` 스킬 명세

### 5.1 전체 스킬 목록

| 스킬 | 역할 | 입력 | 출력 | 상태 전이 |
|------|------|------|------|-----------|
| `/ha-init` | 프로젝트 초기화, 판단, 플랜 제안 | 사용자 설명 | `harness-plan.md`, 빈 `skeleton.md` | `_` → `init` |
| `/ha-design` | skeleton 섹션 채우기 (Architect+Designer) | `skeleton.md` (빈 상태) | `skeleton.md` (채워짐) | `init` → `designed` |
| `/ha-plan` | 태스크 분해 | `skeleton.md` (채워짐) | `tasks.md` | `designed` → `planned` |
| `/ha-build <T-ID>` | 태스크 1개 구현 | Task ID | 코드 파일들, `tasks.md` 업데이트 | `planned` → `building` → `built` |
| `/ha-verify` | 검증 파이프라인 | 현재 파일들 | 검증 결과, `harness-plan.md` 업데이트 | `built` → `verified` |
| `/ha-review` | 리뷰 + LESSON 확인 + draft 프로파일 승급 | `git diff` | 리뷰 결과, APPROVE/REJECT | `verified` → `reviewed` 또는 `building` |

### 5.2 `/ha-init` 상세

**목적**: 프로젝트 타입 판단 + 파이프라인 플랜 작성.

**흐름**:
```
1. 자동 감지
   - ~/.claude/harness/profiles/_registry.yaml 로드
   - 현재 디렉토리 + paths 후보 스캔
   - 매칭 결과 → [{profile, path}, ...]
   - 프로젝트 로컬 override 확인

2. 사용자 설명 수집
   - 사용자가 /ha-init 호출 시 설명 같이 했으면 그걸 사용
   - 없으면 "뭘 만들고 싶으세요?" 질문
   - 짧으면 추가 질문 (최대 3번: 타겟 사용자, 주요 기능, 배포 형태)

3. 대화 루프 (최대 5턴)
   a. 자동 감지 + 사용자 설명 조합 → Claude 판단
   b. 판단 출력:
      - 프로젝트 타입 (1줄 요약)
      - 규모 (tiny/small/medium/large)
      - BE/FE 구성
      - 선택된 profile(s)
      - 선택된 skeleton 섹션
      - 제안 파이프라인 (/ha-* + gstack 조합)
      - 생략 스킬 + 생략 이유
   c. 사용자 피드백:
      - "좋아" / "진행" → 탈출
      - 구체 수정 요청 → 반영 후 재제안
      - "취소" → 종료 (저장 안 함)
   d. 루프 카운트 ≥ 5 → 경고 후 현재 제안으로 진행

4. 프로파일 없음 처리
   - 매칭 0개 + 사용자 설명으로 타입 추정 가능 → 즉석 draft 프로파일 제안
   - 사용자 승인 시 {project}/.claude/harness/profiles/<new-id>.md 생성

5. 확정 시 저장
   a. {project}/docs/harness-plan.md 작성 (전체 frontmatter + 본문)
   b. {project}/docs/skeleton.md 조립 (빈 템플릿, 조각 concat)
   c. 상태: current_step = "init"

6. 다음 안내
   "준비 완료. 다음은 /ha-design 실행하세요."
```

**SKILL.md 구조** (요약):
```markdown
---
name: ha-init
description: 프로젝트 초기화 - 설명 듣고 맞춤 파이프라인 제안
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion, Skill]
---

## 1. 자동 감지 (bash 실행)
## 2. 사용자 설명 수집 (AskUserQuestion)
## 3. 대화 루프 (Claude 판단)
## 4. 프로파일 없음 분기
## 5. 저장
## 6. 안내
```

### 5.3 `/ha-design` 상세

**목적**: skeleton.md의 빈 섹션을 채운다.

**흐름**:
```
1. 사전 조건 확인
   - harness-plan.md 읽음
   - current_step == "init" 이어야 함
   - 아니면 에러 + "/ha-init 먼저 실행하세요"

2. 섹션별 채우기
   for section_id in harness-plan.skeleton_sections.included:
       if is_architect_owned(section_id):   # auth, persistence, interface.http, errors 등
           → Architect 역할로 질문/채우기
       elif is_designer_owned(section_id):  # view.screens, view.components, state.flow
           → Designer 역할로 질문/채우기
       elif is_shared(section_id):          # overview, stack, core.logic, errors
           → 양쪽 컨텍스트 섞어서 채우기

3. 충돌 감지
   - Designer가 새 API 요구하면 Architect에게 재검토 요청 (최대 3회)
   - 현재 Orchestra의 design() 루프와 동일 로직

4. 저장 + 상태 전이
   - skeleton.md 갱신
   - harness-plan.md.current_step = "designed"
   - completed_steps += ["ha-design"]

5. gstack 연동 (profile.gstack_mode)
   - manual: "이제 /plan-eng-review 제안. 직접 실행하세요."
   - prompt: "지금 /plan-eng-review 실행할까요? (y/n)"
   - auto: Skill tool로 직접 호출
```

### 5.4 `/ha-plan` 상세

**목적**: 채워진 skeleton → `tasks.md`.

**흐름**:
```
1. 사전 조건: current_step >= "designed"

2. 프로파일별 컴포넌트 추출
   for profile in harness-plan.profiles:
       for component in profile.components:
           if component.required or section_filled(component.skeleton_section):
               → 태스크 후보 추가

3. 태스크 상세화
   - 각 컴포넌트 → 1~3개 태스크로 분할 (너무 크면 분할)
   - 각 태스크: {id, component_id, path, skill: ha-build, depends_on: [...], description, estimated_minutes}

4. 의존성 그래프 구성 + 검증
   - 순환 탐지
   - 고아 태스크 경고

5. tasks.md 작성
   - Markdown 표 + 의존성 그래프 + 병렬 실행 조합

6. 상태 전이
   - current_step = "planned"
   - completed_steps += ["ha-plan"]
```

**태스크 형식 (tasks.md)**:
```markdown
| ID | Component | Path | Depends | Description | Status |
|----|-----------|------|---------|-------------|--------|
| T-001 | persistence | backend/ | — | users, posts 모델 | pending |
| T-002 | interface.http | backend/ | T-001 | auth API | pending |
...
```

### 5.5 `/ha-build <T-ID>` 상세

**목적**: 태스크 하나 구현.

**흐름**:
```
1. 사전 조건
   - current_step >= "planned"
   - T-ID가 tasks.md에 존재
   - depends_on 태스크들이 "done"
   - T-ID 상태가 pending/in-progress/done
     - done이면 "다시 구현할까요?" 물음 (ask)

2. 컨텍스트 로드
   - tasks.md에서 해당 태스크
   - task.path로 프로파일 결정
   - 프로파일의 component 가이드 + skeleton의 관련 섹션

3. 구현
   - 테스트 먼저 (_base.md §1 원칙)
   - 프로파일의 file_structure에 맞춰 파일 생성/수정
   - 프로파일의 whitelist 외 의존성 감지 시 사용자 질문

4. 검증 (자체 검증, /ha-verify와 별도)
   - profile.toolchain.test 실행
   - 실패 시 재시도 (최대 3회)

5. 태스크 상태 갱신
   - pending → in-progress → done (성공 시)
   - 실패 지속 시 "blocked" + 이유 기록

6. 상태 전이
   - 모든 태스크 done → current_step = "built"
   - 일부만 done → current_step = "building"
```

### 5.6 `/ha-verify` 상세

**목적**: 프로파일의 toolchain 파이프라인 실행.

**흐름**:
```
1. 사전 조건: current_step >= "building"

2. 활성 프로파일 각각에 대해
   for profile in harness-plan.profiles:
       cd profile.path
       run profile.toolchain.install (필요시)
       run profile.toolchain.test
       run profile.toolchain.lint
       if profile.toolchain.type:
           run profile.toolchain.type
       수집: 성공 여부, 에러 메시지

3. 결과 집계
   - 모두 성공 → passed = True
   - 하나라도 실패 → passed = False, 실패 목록 출력

4. verify_history에 기록
   harness-plan.md.verify_history += [{step, at, passed, summary}]

5. 상태 전이
   - passed → current_step = "verified"
   - failed → current_step 유지 (building에 머무름) + 실패 리포트
```

### 5.7 `/ha-review` 상세

**목적**: 코드 리뷰 (convention + LESSON + security).

**흐름**:
```
1. 사전 조건: current_step >= "verified"

2. 변경 파일 수집
   - git diff main...HEAD 또는 사용자 지정 범위

3. 검증 3단
   a. 보안 훅 (기존 Orchestra의 security_hooks.py 재사용)
      - 시크릿, 위험 명령, DB, 의존성 외, 품질, contract
   b. LESSON 패턴 (~/.claude/harness/lessons/shared-lessons.md + 프로젝트 lessons)
      - 각 LESSON에 대해 정규식/구조 매칭
   c. 프로파일 convention 위반
      - file_structure 위반, 금지 사항 위반

4. draft 프로파일 감지
   - 활성 프로파일 중 status=draft 있으면
   - 사용자에게 "<id> 프로파일을 글로벌로 승급할까요?" 질문

5. 결과
   - APPROVE: current_step = "reviewed", completed_steps += ["ha-review"]
   - REJECT: 이슈 목록 출력, current_step = "building" (재구현 필요)

6. gstack 연동
   - APPROVE 후: profile.gstack_mode에 따라 /review, /qa, /ship 제안/실행
```

---

## 6. 파이프라인 상태 추적

### 6.1 `harness-plan.md` 스키마

```markdown
---
# ── 버전/메타 ─────────────────────────────────────────
harness_version: 2
schema_version: 1
project_name: <string>
created_at: <ISO 8601>
updated_at: <ISO 8601>

# ── 프로젝트 판단 (ha-init 결과) ───────────────────────
project_type: <string, 1줄 요약>                  # "멀티유저 웹앱 MVP"
scale: tiny | small | medium | large
user_description_original: |
  <사용자의 최초 설명>

# ── 프로파일 (복수 가능) ──────────────────────────────
profiles:
  - id: fastapi
    path: backend/
    status: confirmed
  - id: react-vite
    path: frontend/
    status: confirmed

# ── skeleton 구성 ─────────────────────────────────────
skeleton_sections:
  required: [overview, stack, ...]
  optional: [auth, persistence]
  included: [overview, stack, auth, persistence, ...]  # 최종 선택

# ── 파이프라인 ───────────────────────────────────────
pipeline:
  steps:                                           # ha-init이 제안한 순서
    - ha-init
    - ha-design
    - plan-eng-review                              # gstack
    - plan-design-review                           # gstack
    - ha-plan
    - ha-build                                     # 반복 (여러 번)
    - ha-verify
    - ha-review
    - review                                       # gstack
    - qa                                           # gstack
    - ship                                         # gstack
    - retro                                        # gstack
  current_step: <step_id>
  completed_steps: [ha-init, ha-design]
  skipped_steps: []                                # 사용자가 의도적으로 건너뛴 것
  gstack_mode: manual

# ── 검증 이력 ────────────────────────────────────────
verify_history:
  - { step: ha-verify, at: <iso>, passed: true, summary: "247 tests, lint clean" }

# ── 재시작/롤백 ──────────────────────────────────────
backups: []                                        # {.backup/*.md, at, reason}

last_activity: <ISO 8601>
---

# <Project Name>

## 원본 설명
<사용자의 최초 설명 그대로>

## 판단 근거
- 타입: <type>
- 규모: <scale>
- BE/FE 구성: <description>

## 파이프라인
| # | Step | 상태 | 노트 |
|---|------|------|------|
| 1 | ha-init | ✅ 완료 | ... |
| 2 | ha-design | ✅ 완료 | ... |
| 3 | plan-eng-review | ⏳ 대기 | gstack |
...

## 생략된 스킬 + 이유
- /office-hours — 이미 아이디어 명확
- /retro — 짧은 프로젝트

## 사용자 노트
(대화 중 추가된 메모)
```

### 6.2 상태 전이 규칙

```
_ (시작 전)
 │
 ▼
init (harness-plan.md 생성됨)
 │
 ▼
designed (skeleton.md 채워짐)
 │
 ▼
planned (tasks.md 생성됨)
 │
 ▼
building (일부 태스크 done)
 │
 ▼
built (모든 태스크 done)
 │
 ▼
verified (ha-verify 통과)
 │
 ▼
reviewed (ha-review APPROVE)
 │
 ▼
shipped (선택, gstack /ship 완료)
```

**전이 규칙**:
- 앞 단계로만 전이 (뒤로는 명시적 롤백만)
- 각 `/ha-*` 스킬은 자기가 완료시킬 수 있는 전이만 수행
- 순서 건너뛰기 금지 (예: init → planned 불가)

### 6.3 재시작

**중단된 세션 복구**:
- 어떤 `/ha-*`든 실행 시 `harness-plan.md` 먼저 읽음
- `current_step`이 해당 스킬의 사전 조건 만족 안 하면 에러
- 메시지: "현재 단계: <X>. `/ha-<Y>` 를 먼저 실행하세요."

**같은 스킬 재실행**:
- 사용자가 명시적으로 "다시" / "--reset" 요청
- 또는 해당 스킬이 아직 완료되지 않음 (예: building 중 ha-build 재호출)
- 완료된 단계 재실행 시: backup 생성 후 진행
  - `skeleton.md` → `.backup/skeleton-<ts>.md`
  - `tasks.md` → `.backup/tasks-<ts>.md`

---

## 7. Orchestra 통합

### 7.1 영향 받는 파일 (backend/)

| 파일 | 변경 | 내용 |
|------|------|------|
| `docs/skeleton_template.md` | **삭제** | SoT를 `~/.claude/harness/templates/skeleton/`로 이전 |
| `src/orchestrator/context.py` | **리팩터** | 하드코딩된 section 매핑 제거 → 프로파일이 선언 |
| `src/orchestrator/orchestrate.py` | **리팩터** | `materialize_skeleton()` 조립 알고리즘 교체 |
| `src/orchestrator/output_parser.py` | **리팩터** | 섹션 참조를 ID 기반으로 |
| `src/orchestrator/security_hooks.py` | **유지 + 확장** | 프로파일의 whitelist 읽도록 |
| `agents/*/CLAUDE.md` | **수정** | 섹션 번호 → 섹션 ID 참조 |

### 7.2 신규 파일

| 파일 | 역할 |
|------|------|
| `src/orchestrator/profile_loader.py` | `_registry.yaml` 파싱, 프로파일 해석 (로컬 override 포함), 상속 병합 |
| `src/orchestrator/skeleton_assembler.py` | 섹션 조각 로드 + 조립 |
| `src/orchestrator/plan_manager.py` | `harness-plan.md` frontmatter 읽기/쓰기, 상태 전이 |
| `tools/harness-validate/` (또는 `bin/harness`) | 프로파일·harness-plan 스키마 검증 CLI |

### 7.3 구체 리팩터 — `context.py`

**현재** (HabitFlow 예시 기준):
```python
# 하드코딩된 섹션 번호 매핑
_AGENT_SECTION_MAP = {
    "architect": [5, 6, 7, 10],      # auth, DB, API, state
    "designer": [8],                  # UI/UX
    "orchestrator": [...],
    ...
}
```

**리팩터 후**:
```python
# 프로파일이 선언
# fastapi.md → architect sections: [auth, persistence, interface.http, errors]
# react-vite.md → designer sections: [view.screens, view.components, state.flow]
def build_context(agent: str, profiles: list[Profile], skeleton_path: Path) -> str:
    sections_for_agent = []
    for p in profiles:
        sections_for_agent += p.agent_sections.get(agent, [])
    # 섹션 ID로 skeleton.md에서 추출
    extracted = [extract_section_by_id(skeleton_path, sid) for sid in sections_for_agent]
    return "\n\n".join(extracted)
```

### 7.4 기존 테스트 (208개) 처리

**전략**:
1. 테스트 픽스처를 섹션 ID 기반으로 교체 (번호 → ID)
2. 새 모듈(`profile_loader`, `skeleton_assembler`, `plan_manager`) 각각 단위 테스트 추가 (30~40개)
3. 기존 통합 테스트는 새 모듈 쓰도록 리팩터 (208개 유지 또는 더 높게)
4. 목표: **테스트 250개 이상, 전체 통과**

**리팩터 순서**:
1. 신규 모듈 작성 + 단위 테스트 (기존 코드 건드리지 않음)
2. `context.py` 리팩터 + 기존 테스트 수정
3. `orchestrate.py` 리팩터
4. `output_parser.py` 리팩터
5. `skeleton_template.md` 삭제 + 전체 테스트 실행
6. 하나라도 깨지면 이전 단계로

### 7.5 점진적 마이그레이션 전략 — **Feature flag 미사용, Single Cut-over**

**확정 결정**: feature flag 없이 한 번에 전환.

**이유**:
- Backward compat 유지 비용이 설계 단순성을 해침
- 테스트 250개+가 자동 회귀 방지
- D3 결정(깔끔한 cut-over)과 일치
- HarnessAI 자체는 프로덕션 운영 중이 아님 — 실수해도 복구 쉬움

**안전장치** — Phase 2를 10개 커밋으로 쪼갬:
1. `profile_loader.py` + 단위 테스트 (기존 코드 X)
2. `skeleton_assembler.py` + 단위 테스트 (기존 코드 X)
3. `plan_manager.py` + 단위 테스트 (기존 코드 X)
4. `context.py` 리팩터 + 기존 테스트 수정
5. `orchestrate.py::materialize_skeleton` 교체
6. `output_parser.py` 섹션 ID 기반 전환
7. `agents/*/CLAUDE.md` 섹션 ID 참조
8. `security_hooks.py` 프로파일 whitelist 읽기
9. `backend/docs/skeleton_template.md` 삭제
10. 전체 테스트 실행 + 통과 검증

각 커밋 이후 `uv run pytest tests/` 통과 필수. 실패 시 `git revert` 즉시 가능.

---

## 8. gstack 연동

### 8.1 프로파일 선언

```yaml
gstack_mode: manual                      # 기본값
gstack_recommended:
  before_design: [office-hours]          # /ha-design 전에 제안
  after_design: [plan-eng-review, plan-design-review]
  after_build: [review]
  before_ship: [qa]
  after_ship: [retro]
```

### 8.2 각 모드 동작

**manual** (기본):
- 스킬 단계 완료 시 stdout에 제안만 출력
- 예: "/ha-design 완료. 다음 권장: /plan-eng-review, /plan-design-review"
- 사용자가 직접 실행

**prompt**:
- `AskUserQuestion` 으로 "지금 /plan-eng-review 실행할까요? (y/n)"
- y 선택 시 `Skill` tool로 호출

**auto**:
- `Skill` tool로 즉시 호출
- 실패 시 사용자에게 보고, 이후 manual로 전환

### 8.3 현재 Claude Code 제약 확인 필요

`Skill` tool을 `/ha-*` 스킬 안에서 호출할 수 있는지:
- 가능하면 **auto/prompt 모드 완전 지원**
- 불가능하면 **manual만 지원** + auto/prompt는 향후 과제

**검증 방법**: PoC — `/ha-init` 내부에서 `Skill(skill: "office-hours")` 호출 시도.

---

## 9. 실패/재시작/롤백 경로

### 9.1 실패 유형별 처리

| 실패 | 스킬 | 기본 대응 |
|------|------|----------|
| 자동 감지 실패 | `/ha-init` | `fallback.action: prompt_user` |
| 사용자 "취소" | `/ha-init` | 저장 없이 종료 |
| `skeleton.md` 파싱 실패 | `/ha-design`, `/ha-plan` | 에러 + "현재 파일 복구 또는 `/ha-init --reset`" |
| 태스크 의존성 순환 | `/ha-plan` | 에러 + 순환 참여 노드 출력 |
| `/ha-build` 3회 재시도 실패 | `/ha-build` | 태스크 상태 "blocked", 이유 기록, 사용자 개입 요청 |
| `toolchain.test` 실패 | `/ha-verify` | 현재 단계 유지, 실패 리포트, `/ha-build T-XXX` 재실행 권장 |
| `/ha-review` REJECT | `/ha-review` | current_step을 "building"으로 되돌림, 이슈 목록 제공 |

### 9.2 롤백 명령

사용자가 `/ha-<X> --reset` 또는 대화에서 "다시":

```
1. 현재 상태 백업 (harness-plan.md.backups에 기록)
2. harness-plan.md.current_step 이전 단계로 되돌림
3. 관련 파일 백업 + 삭제
   - ha-design --reset: skeleton.md → .backup/
   - ha-plan --reset: tasks.md → .backup/
   - ha-build T-XXX --reset: 해당 태스크 상태 pending
4. 사용자 안내: "<X> 단계 재시작 준비. 진행하세요."
```

### 9.3 전체 리셋

`/ha-init --reset-all`:
- 모든 상태 초기화
- `docs/harness-plan.md`, `docs/skeleton.md`, `docs/tasks.md` → `.backup/<ts>/`
- 빈 상태에서 `/ha-init` 새로 시작
- 경고: "모든 진행 상태가 백업됩니다. 계속할까요?"

---

## 10. 즉석 프로파일 품질 보장

### 10.1 생성 게이트 (draft)

**허용 조건** (모두 만족):
1. `_registry.yaml` 매칭 0개
2. 사용자 설명이 구체적 (50자 이상 + 기술 스택 언급)
3. Claude가 제안한 프로파일이 `harness validate` 통과

**거부 조건**:
- 사용자 설명이 모호 → 추가 질문 (대화 루프 안에서 해결)
- 기존 프로파일 중 70% 이상 일치하는 게 있음 → 그걸 extend 하도록 제안

### 10.2 승급 게이트 (draft → confirmed) — 엄격

**필수 조건 5개 모두 충족해야 승급**:

1. **전체 프로젝트 완주**
   - `current_step ∈ {reviewed, shipped}`
   - 즉 `/ha-init` 부터 `/ha-review` APPROVE까지 완료

2. **`/ha-verify` 누적 통과율 ≥ 80%**
   - `verify_history`에 최소 3회 기록
   - 그중 80% 이상 `passed=true`

3. **`/ha-review` 최종 APPROVE**
   - draft 프로파일 쓴 태스크들 APPROVE

4. **`harness validate` 통과**
   - 스키마 위반 없음

5. **사용자 checklist 기반 동의 — 4개 질문 전부 "yes"**:
   - [ ] 파일 구조가 실제로 적절했나?
   - [ ] 화이트리스트 의존성이 맞았나? (과하거나 부족하지 않았나?)
   - [ ] toolchain 명령이 정확히 작동했나?
   - [ ] 다음 유사 프로젝트에서 그대로 재사용할 만한가?

**거부 경로**: 승급 실패 시 프로파일은 **프로젝트 로컬에만** 남음. 다음 프로젝트에선 재사용 안 됨 — 새 프로젝트 시작하면 다시 draft 생성.

**편집 경로**: 사용자가 "일부 문제 있었음"이라고 하면 → 에디터로 수정 → `harness validate` 재검증 → 통과 시 승급.

**승급 절차**:
```
/ha-review 종료 시:
  if has_draft_profile(harness-plan):
      check: 조건 1~4 자동 검증
      if 자동 검증 통과:
          ask: "<id> 프로파일 승급 체크리스트 (4개 질문)"
          if 4개 모두 yes:
              복사 ~/.claude/harness/profiles/ + status: confirmed
          else:
              edit 경로 또는 유지
      else:
          "승급 조건 미달. 프로젝트 로컬에 유지."
```

### 10.3 draft 프로파일 주석

생성 시 파일 상단에 강제 주석:
```yaml
---
id: my-new-stack
status: draft
created_at: <ts>
created_by: ha-init
---

# DRAFT PROFILE — 실제 동작 확인 전
# 이 프로파일은 ha-init이 즉석에서 생성했습니다.
# /ha-review 단계에서 승급 여부 결정됩니다.
# 수동 편집 가능 — 수정 후 harness validate 실행 권장.

...
```

---

## 11. 마이그레이션 계획

### 11.1 삭제 대상

**`/my-*` 스킬 (12개)**:
```
~/.claude/skills/my-db/
~/.claude/skills/my-db-design/
~/.claude/skills/my-architect/
~/.claude/skills/my-designer/
~/.claude/skills/my-skeleton-check/
~/.claude/skills/my-tasks/
~/.claude/skills/my-api/
~/.claude/skills/my-ui/
~/.claude/skills/my-logic/
~/.claude/skills/my-type-check/
~/.claude/skills/my-review/
~/.claude/skills/my-lessons/
```

**구 템플릿**:
```
backend/docs/skeleton_template.md
```

### 11.2 신규 대상

**`/ha-*` 스킬 (6개)**:
```
~/.claude/skills/ha-init/SKILL.md
~/.claude/skills/ha-design/SKILL.md
~/.claude/skills/ha-plan/SKILL.md
~/.claude/skills/ha-build/SKILL.md
~/.claude/skills/ha-verify/SKILL.md
~/.claude/skills/ha-review/SKILL.md
```

**프로파일 초기 세트 (5개 먼저, 나머지는 필요 시)**:
```
~/.claude/harness/profiles/_base.md          ✅ (이미 작성)
~/.claude/harness/profiles/_registry.yaml    ✅ (이미 작성)
~/.claude/harness/profiles/fastapi.md
~/.claude/harness/profiles/react-vite.md
~/.claude/harness/profiles/python-cli.md
~/.claude/harness/profiles/python-lib.md
~/.claude/harness/profiles/claude-skill.md
```

**skeleton 조각 (20개)**:
```
~/.claude/harness/templates/skeleton/{overview,requirements,stack,errors,
  auth,persistence,interface.http,interface.cli,interface.ipc,interface.sdk,
  view.screens,view.components,state.flow,core.logic,
  observability,deployment,tasks,notes}.md
```

**Orchestra 신규 모듈**:
```
backend/src/orchestrator/profile_loader.py
backend/src/orchestrator/skeleton_assembler.py
backend/src/orchestrator/plan_manager.py
```

**검증 CLI**:
```
~/.claude/harness/bin/harness               # Python shebang 스크립트
```

### 11.3 변경 대상

**Orchestra 리팩터**:
```
backend/src/orchestrator/context.py          # 하드코딩 제거
backend/src/orchestrator/orchestrate.py      # materialize_skeleton 교체
backend/src/orchestrator/output_parser.py    # section ID 기반
backend/src/orchestrator/security_hooks.py   # 프로파일 whitelist 읽기
backend/agents/*/CLAUDE.md                   # 섹션 ID 참조
backend/tests/**/*.py                        # 픽스처 교체
```

**프로젝트 CLAUDE.md**:
```
CLAUDE.md                                    # v2 아키텍처 반영, /my-* → /ha-*
```

### 11.4 기존 프로젝트 영향

| 프로젝트 | 영향 | 대응 |
|---------|------|------|
| HabitFlow (완료) | 없음 — 이미 완성 | 변경 없음 |
| 금칙어게임 (완료) | 없음 — 이미 완성 | 변경 없음 |
| Personal Jira (설계만) | 구현 시작 시 `/ha-*` 사용 | harness-plan.md 새로 작성 |
| 새 프로젝트 | `/ha-*` 만 사용 | N/A |
| code-hijack (CLI) | `/ha-*`로 검증 대상 | `/ha-init`부터 |

### 11.5 실행 순서 (단계별 커밋)

```
Phase 1 — 기반 작성 (변경 없이 추가) ✅ 완료 (커밋: 3be75f7, e5c4dbf)
  [x] 1.1 _registry.yaml 확장
  [x] 1.2 skeleton 조각 20개 작성
  [x] 1.3 프로파일 5개 작성
  [x] 1.4 harness validate CLI 작성
  [x] 1.5 커밋
  [x] 1.6 테스트: harness validate 27개 파일 통과

Phase 2 — Orchestra 리팩터 (기존 테스트 계속 통과) ✅ 완료 (커밋 10개)
  [x] 2.1 profile_loader.py + 단위 14개          (6d1905d)
  [x] 2.2 skeleton_assembler.py + 단위 10개      (f51b792)
  [x] 2.3 plan_manager.py + 단위 22개            (45e4b62)
  [x] 2.4 context.py 리팩터 + 14개               (73cc8b5)
  [x] 2.5 orchestrate.assemble_skeleton + 5개    (f664f2a)
  [x] 2.6 output_parser 섹션 ID + 6개            (924446a)
  [x] 2.7 agents/*/CLAUDE.md 섹션 ID 전환        (6749c9f)
  [x] 2.8 security_hooks 프로파일 whitelist + 5개(cc954ac)
  [x] 2.9 skeleton_template.md 삭제              (595ef88)
  [x] 2.10 전체 테스트 327개 통과 (E2E 3개 포함, 회귀 0건)

Phase 2 후처리 — PoC 리뷰 반영
  [x] runner.py 의 build_context use_section_ids=True
  [x] orchestrate._extract_allowed_endpoints 가 ID 우선 + 번호 폴백
  [x] E2E 통합 테스트 3개 (test_v2_integration.py)
  [x] backend/docs/skeleton.md untrack + .gitignore
  [x] 사전 존재 lint 6건 정리 (B904, SIM105, SIM117, F401, F541, I001)
  [x] 설계 문서 Phase 1~2 체크리스트 갱신

Phase 3 — 스킬 작성
  [ ] 3.1 /ha-init 구현 + 동작 테스트
  [ ] 3.2 /ha-design 구현
  [ ] 3.3 /ha-plan 구현
  [ ] 3.4 /ha-build 구현
  [ ] 3.5 /ha-verify 구현
  [ ] 3.6 /ha-review 구현
  [ ] 3.7 커밋: "feat: /ha-* 스킬 6개 추가"

Phase 4 — 구 스킬 삭제
  [ ] 4.1 /my-* 12개 삭제
  [ ] 4.2 CLAUDE.md 업데이트
  [ ] 4.3 커밋: "chore: 구 /my-* 스킬 삭제"

Phase 5 — 검증
  [ ] 5.1 code-hijack에서 /ha-init 부터 /ha-review 까지 완주
  [ ] 5.2 새 샘플 웹앱 프로젝트에서 완주
  [ ] 5.3 새 샘플 라이브러리에서 완주
  [ ] 5.4 "Claude 스킬 만들기" 메타 프로젝트에서 draft 프로파일 생성 + 승급 경로 검증
  [ ] 5.5 회고 + 문서 보강
```

**예상 기간**: Phase 1 하루 + Phase 2 이틀 + Phase 3 이틀 + Phase 4 반나절 + Phase 5 하루 = **약 6.5일**.

### 11.6 Phase 1~2 회고 (실측)

**커밋 11개** (`3be75f7` ~ Phase 2 후처리 단일 커밋):

| 측면 | 계획 | 실측 |
|------|------|------|
| Phase 1 일정 | 1일 | 부분 (PoC 포함 시 + 0.5일) |
| Phase 2 일정 | 2일 | 1일 (10 커밋 + 후처리 1) |
| 신규 테스트 | 30~40 | **79** (단위 76 + E2E 3) |
| 전체 테스트 | 250+ | **327** |
| 회귀 | 0 | 0 |

**잘된 것**:
- 커밋 단위 작게 (Phase별 1커밋) → 회귀 즉시 발견 가능
- Additive refactor (legacy 보존) → 안전. 일부는 Phase 4에서 정리 예정
- 모든 신규 모듈 hermetic 단위 테스트 (tmp_path)
- E2E 통합 테스트가 detect → assemble → context 흐름 정합 보장

**Phase 2 PoC 리뷰에서 발견한 추가 이슈** (모두 후처리 커밋에 반영):
- runner.py 가 ID 기반 매핑 미사용 — agents/CLAUDE.md 와 불일치 가능성
- E2E 테스트 부재 → test_v2_integration.py 추가
- 사전 존재 lint 6건 (B904/SIM/F401 등) 누적 → 정리
- 운영 artifact (skeleton.md) 추적 → .gitignore 추가
- 설계 문서 진척 미반영

**미완 (의도적 leftover, Phase 4에서 처리)**:
- `materialize_skeleton`, `fill_skeleton_template`, `extract_section`, `SECTION_MAP` 레거시 잔존
- Phase 3 (`/ha-init`) 가 신 시스템 첫 호출자가 되면 Phase 4에서 일괄 제거

---

## 12. 검증 계획

### 12.1 테스트 매트릭스

| # | 프로젝트 | 프로파일 | 예상 섹션 수 | 파이프라인 | 검증 포인트 |
|---|---------|---------|-------------|-----------|-----------|
| 1 | code-hijack (CLI) | python-cli | 6 | /ha-init → /ha-review | 매뉴얼 모드 완주 |
| 2 | 새 샘플 풀스택 웹앱 | fastapi + react-vite | 13 | 전체 | 모노레포 + 다중 프로파일 |
| 3 | 새 샘플 Python 라이브러리 | python-lib | 5 | /ha-init → /ha-review | 최소 파이프라인 |
| 4 | "Claude 스킬 만들기" | claude-skill (draft) | 3 | /ha-init → /ha-build → 승급 | 즉석 프로파일 생성 + 승급 |
| 5 | 감지 실패 프로젝트 (고의) | 없음 | — | /ha-init 에서 draft 생성 | fallback 경로 |

### 12.2 Orchestra 테스트 (자동 모드)

- 기존 208개 테스트가 리팩터 후 **모두 통과**
- 신규 모듈 단위 테스트 40+개 추가
- 프로파일 기반 재귀 실행 테스트 (HabitFlow 재현) 1개
- **목표: 250+ 개 전체 통과**

### 12.3 수동 검증 체크리스트

```
[ ] /ha-init 자동 감지 성공 (python-cli, fastapi, react-vite 각각)
[ ] /ha-init 감지 실패 → fallback 경로
[ ] /ha-init 대화 루프 3턴 이상 수정 반영
[ ] /ha-init이 제안한 파이프라인에 사용자가 수정 요청 → 반영
[ ] 프로젝트 로컬 override가 글로벌 덮어씀
[ ] /ha-design이 Architect/Designer 역할 분리 제대로 수행
[ ] /ha-design 에서 Designer ↔ Architect 충돌 → 재협의 (최대 3회)
[ ] /ha-plan 의존성 그래프 정확
[ ] /ha-build가 프로파일의 whitelist 외 의존성 감지
[ ] /ha-verify 프로파일 toolchain 정확히 호출
[ ] /ha-review 가 security_hooks + LESSON + convention 전부 체크
[ ] /ha-review 에서 draft 프로파일 승급 flow
[ ] 중단된 세션 복구 (harness-plan.md 읽어 current_step 복원)
[ ] /ha-<X> --reset 동작
[ ] /ha-init --reset-all 동작
[ ] gstack_mode: manual 에서 다음 스킬 제안만 출력
[ ] gstack_mode: prompt 에서 질문 출력
[ ] gstack_mode: auto 에서 직접 호출 (가능 시)
[ ] 모노레포: 한 /ha-build T-XXX가 올바른 프로파일 선택
```

### 12.4 회귀 방지

- `harness validate` 는 CI에서 모든 프로파일 자동 검증
- `~/.claude/harness/` 변경 시마다 실행
- 스키마 위반 → 경고 + 수정 요청

---

## 13. 열린 질문

### 13.1 구현 전 결정 필요 — 3개 (Phase 0)

| # | 질문 | 확정 결정 | 결정 시점 |
|---|------|-----------|----------|
| A | Skill tool을 `/ha-*` 스킬 안에서 호출 가능한가? | Phase 3 시작 전 **PoC 1회** 필수. 가능 → auto/prompt 모드 지원. 불가 → manual만 지원 | Phase 3 전 |
| B | Windows 경로 처리 | **forward slash + `~/` 경로만 사용**. `C:\...` 금지. 스크립트 내부는 `$HOME`, `$PROJECT_ROOT` 변수 사용. bash 호환성 보장 | Phase 1 시작 전 (확정됨) |
| C | 프로젝트 `.claude/harness/` git 커밋 여부 | **커밋**. 팀 공유 필요. 단 개인 메모(`lessons-personal-*.md`)는 `.gitignore` | Phase 1 시작 전 (확정됨) |

PoC A는 Phase 3 시작 직전 30분 소요 예상. 테스트 스킬 하나 만들어 `Skill(skill: "office-hours")` 호출.

### 13.2 구현 중 결정 — 3개 (Phase 5 이후)

| # | 질문 | 연기 이유 |
|---|------|----------|
| 1 | LESSON 파일 스택별 분리 | 단일 파일로 시작. 30+ LESSON 쌓이면 분리 |
| 2 | 프로파일 v1 → v2 마이그레이션 | 현재 스키마 v1. v2 나올 때 결정 |
| 3 | 다국어 프로파일 (영어 병기) | 한국어로 시작. 필요 시 번역 |

---

## 14. 참고 — 기존 시스템 매핑

| 현재 | v2 |
|------|-----|
| `backend/docs/skeleton_template.md` | `~/.claude/harness/templates/skeleton/*.md` (조각화) |
| 섹션 번호 (1~19) | 섹션 ID (`overview`, `persistence`, ...) |
| `/my-db`, `/my-api`, `/my-ui`, `/my-logic` | `/ha-build` (프로파일별 컴포넌트 기반) |
| `/my-db-design`, `/my-architect`, `/my-designer` | `/ha-design` |
| `/my-skeleton-check` | `/ha-design` 내장 + `harness validate` |
| `/my-tasks` | `/ha-plan` |
| `/my-type-check` | `/ha-verify` |
| `/my-review` | `/ha-review` |
| `/my-lessons` | (없음 — gstack `/retro` 사용) |
| 스택 하드코딩 (fastapi/nextjs/rn/electron) | 프로파일 파일 |
| `backend/src/orchestrator/context.py::_AGENT_SECTION_MAP` | 프로파일의 `agent_sections` 선언 |

---

## 승인 체크리스트

이 설계 문서를 기반으로 구현 시작하기 전 확인:

```
[ ] 결정사항 D1~D6 최종 확정
[ ] 섹션 ID 20개 목록 확정 (§4.1)
[ ] 프로파일 frontmatter 스키마 확정 (§3.1)
[ ] harness-plan.md frontmatter 스키마 확정 (§6.1)
[ ] /ha-* 스킬 6개 역할 확정 (§5)
[ ] Phase 1~5 순서 동의 (§11.5)
[ ] 열린 질문 6개 중 구현 전 결정 필요한 것 선별 (§13)
```

승인 후 Phase 1 부터 시작.
