# Setup Guide — HarnessAI

처음 설치하는 사람을 위한 가이드.

---

## 🚀 v2 Quick Start (`/ha-*` 스킬 7종)

v2 흐름이 **권장 경로**. v1 (`/my-*`) 은 레거시.

### 설치 (1회)

```bash
git clone https://github.com/reasonableplan/harnessai.git
cd harnessai

# 1) 스킬 + 프로파일을 ~/.claude/ 로 설치 (SHA256 manifest 기반, 재실행 시 diff 감지)
./install.sh              # Unix / WSL / macOS / Git Bash
# .\install.ps1           # Windows PowerShell (UTF-8 BOM 으로 한글 깨짐 방지)

# 2) 환경변수 (install 스크립트가 끝에 안내)
export HARNESS_AI_HOME="$(pwd)"

# 3) backend 의존성 (서버/테스트용)
cd backend && uv sync

# 4) v2 스키마 무결성 확인
python ../harness/bin/harness validate
```

**install 스크립트 옵션**:
- `--force` — 기존 설치 확인 생략
- `--dry-run` — 실제 복사 없이 diff 만 출력
- `CLAUDE_HOME=/custom/.claude ./install.sh` — 타겟 디렉토리 override

상세: [install.sh](install.sh) · [install.ps1](install.ps1) · 회귀 테스트 [tests/install/](tests/install/)

### 프로젝트 시작 (어떤 프로젝트든)

```bash
cd <my-project>
claude   # Claude Code 실행

# 세션 안에서:
/ha-init            # 프로파일 자동감지 + 인터뷰 → harness-plan.md + skeleton.md
/ha-design          # Architect+Designer 역할로 skeleton 채움
/ha-plan            # Orchestrator 역할로 tasks.md
/ha-build T-001     # 태스크 구현 (병렬: --task T-001,T-002 콤마 구분)
/ha-verify          # 프로파일 toolchain 실행 (test/lint/type)
/ha-review          # 보안/LESSON/AI-slop 종합 리뷰
/ha-smoke           # 런타임 기동 검증 (advisory) — 앱이 실제로 뜨는지
```

### 기존 코드베이스 도입

```bash
/ha-deepinit        # 코드 분석 → hierarchical AGENTS.md 자동 생성 (선택)
/ha-init            # 이어서 v2 흐름 시작
```

---

## v1 (레거시) — 목차

1. [사전 요구사항](#1-사전-요구사항)
2. [저장소 클론 및 의존성 설치](#2-저장소-클론-및-의존성-설치)
3. [LLM 설정](#3-llm-설정)
4. [에이전트 설정](#4-에이전트-설정-agentsyaml)
5. [코딩 스타일 커스터마이징](#5-코딩-스타일-커스터마이징)
6. [환경변수 설정](#6-환경변수-설정)
7. [실행](#7-실행)
8. [gstack 연동 (선택)](#8-gstack-연동-선택)
9. [트러블슈팅](#9-트러블슈팅)

---

## 1. 사전 요구사항

| 도구 | 버전 | 용도 |
|------|------|------|
| **Python** | 3.12+ | 서버 실행 |
| **uv** | 최신 | Python 패키지 매니저 |
| **Claude CLI** | 최신 | 에이전트 실행 (claude-cli provider 사용 시) |

### 설치 확인

```bash
python --version   # 3.12 이상
uv --version
claude --version   # claude-cli provider 사용 시
```

### uv 설치 (없는 경우)

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

---

## 2. 저장소 클론 및 의존성 설치

```bash
git clone https://github.com/reasonableplan/harnessai.git
cd harnessai/backend

uv sync
```

---

## 3. LLM 설정

에이전트는 `agents.yaml`의 `provider` 설정에 따라 LLM을 호출한다.
지원 provider는 4가지다.

### Provider 비교

| Provider | 설정 | 비용 | 권장 용도 |
|----------|------|------|----------|
| **claude-cli** | Claude CLI 설치 + 로그인 | Max/Pro 구독 포함 | 기본값. 가장 안정적 |
| **gemini-cli** | Gemini CLI 설치 + 로그인 | 무료 티어 있음 | 선택적 대안 |
| **gemini** | `GEMINI_API_KEY` | API 사용량 과금 | Gemini REST API 직접 호출 |
| **local** | `LOCAL_MODEL_BASE_URL` | 무료 (로컬 실행) | Ollama, LM Studio 등 |

### claude-cli 설정 (기본값)

Claude Max 또는 Pro 구독자라면 API 크레딧 없이 사용 가능.

```bash
# Claude CLI 설치 (없는 경우)
npm install -g @anthropic-ai/claude-code

# 로그인
claude login
```

### 로컬 모델 (Ollama)

```bash
# Ollama 실행
ollama serve
ollama pull llama3.1
```

`agents.yaml`에서 해당 에이전트의 provider를 `local`로 설정하고 `.env`에:

```env
LOCAL_MODEL_BASE_URL=http://localhost:11434/v1
LOCAL_MODEL_NAME=llama3.1
```

---

## 4. 에이전트 설정 (agents.yaml)

`backend/agents.yaml`에서 에이전트별로 provider와 모델을 독립적으로 지정할 수 있다.

```yaml
# 동시 실행 에이전트 수 제한
max_concurrent: 2

architect:
  provider: claude-cli
  model: claude-opus-4-6
  timeout_seconds: 300
  on_timeout: escalate
  max_retries_on_timeout: 1
  max_tokens: 8192

backend_coder:
  provider: claude-cli
  model: claude-sonnet-4-6   # 더 저렴한 모델로 교체 가능
  timeout_seconds: 600
  on_timeout: retry
  max_retries_on_timeout: 1
  max_tokens: 16384

frontend_coder:
  provider: claude-cli
  model: claude-haiku-4-5    # 빠르고 저렴 — 프론트 코딩에 충분
  timeout_seconds: 600
  on_timeout: retry
  max_retries_on_timeout: 1
  max_tokens: 16384
```

### on_timeout 옵션

| 값 | 동작 |
|----|------|
| `retry` | `max_retries_on_timeout`만큼 재시도 |
| `escalate` | 즉시 사람에게 에스컬레이션 (게이트에서 멈춤) |
| `log_only` | 로그만 남기고 계속 진행 |

---

## 5. 코딩 스타일 커스터마이징

에이전트가 생성하는 코드의 스타일과 패턴은 두 가지 방법으로 바꿀 수 있다.

### 방법 A: 에이전트 시스템 프롬프트 수정

각 에이전트의 `backend/agents/[에이전트명]/CLAUDE.md`가 해당 에이전트의 시스템 프롬프트다.
이 파일을 수정하면 에이전트가 쓰는 코드 스타일이 즉시 바뀐다.

**예시 1 — 백엔드 ORM을 SQLModel → SQLAlchemy 2.0으로 변경:**

```markdown
<!-- backend/agents/backend_coder/CLAUDE.md 에서 수정 -->
## DB
- SQLAlchemy 2.0 Core 사용 (SQLModel 금지)
- 모든 쿼리는 select() / insert() / update() / delete()
```

**예시 2 — 프론트엔드를 Next.js App Router로 변경:**

```markdown
<!-- backend/agents/frontend_coder/CLAUDE.md 에서 수정 -->
## 스택
- Next.js 15 App Router
- Server Components 우선, 필요한 경우만 'use client'
- TanStack Query로 서버 상태 관리
```

**예시 3 — 허용 라이브러리(화이트리스트) 변경:**

```markdown
<!-- backend/agents/backend_coder/CLAUDE.md 에서 수정 -->
## 허용 라이브러리 (화이트리스트)
- fastapi, uvicorn, sqlalchemy, alembic
- redis          ← 캐시 레이어 추가
- celery         ← 백그라운드 작업 추가
```

> **주의**: 허용 라이브러리를 변경하면 해당 프로파일 (`~/.claude/harness/profiles/<stack>.md`) 의 `whitelist.runtime` / `whitelist.dev` 도 함께 수정해야 `SecurityHooks` 가 올바른 의존성을 허용한다.

### 방법 B: 프로파일 / skeleton 조각 수정 (v2)

HarnessAI v2 는 프로파일 + 재사용 가능한 skeleton 조각 구조.

**1. 프로파일** (`~/.claude/harness/profiles/<stack>.md`) — 스택별 규칙 전체:
- 감지 규칙, 컴포넌트, `skeleton_sections.required/optional/order`, `toolchain`, `whitelist`, `lessons_applied`

**2. Skeleton 조각** (`~/.claude/harness/templates/skeleton/<section_id>.md`) — 36개 표준 섹션 템플릿:
- `overview.md`, `interface.http.md`, `core.logic.md`, `persistence.md` 등

**예시 — 새 스택 지원 추가:**

```yaml
# ~/.claude/harness/profiles/my-stack.md (frontmatter 부분)
---
id: my-stack
extends: _base
skeleton_sections:
  required: [overview, stack, interface.http, persistence, errors, tasks, notes]
  order:    [overview, stack, persistence, interface.http, errors, tasks, notes]
toolchain:
  test: "uv run pytest tests/"
  lint: "uv run ruff check src/"
  type: "uv run pyright src/"
whitelist:
  runtime: [my_custom_lib]
  dev: [pytest, ruff, pyright]
---
```

**검증:**
```bash
python ~/.claude/harness/bin/harness validate   # 프로파일 스키마 체크
```

### 커스터마이징 후 확인 사항

```
[ ] agents/[에이전트]/CLAUDE.md 수정 완료
[ ] 프로파일 whitelist 업데이트 (라이브러리 변경 시)
[ ] agents.yaml 모델/타임아웃 조정 (필요 시)
[ ] harness validate — 50 files, 0 errors
[ ] cd backend && uv run pytest tests/ — 939 pass
```

---

## harness CLI 서브커맨드 레퍼런스 (v0.8.0+)

`harness/bin/harness` 가 제공하는 전체 서브커맨드 목록.

```bash
# 스키마 검증
python harness/bin/harness validate

# skeleton ↔ FS 정합성 + placeholder 잔존 검사
python harness/bin/harness integrity --project <path>

# tasks.md → Mermaid 의존성 그래프 (v0.9.1+)
python harness/bin/harness graph docs/tasks.md
python harness/bin/harness graph docs/tasks.md --inject      # tasks.md 에 그래프 삽입
python harness/bin/harness graph docs/tasks.md --no-phases   # Phase 구분 없이 플랫

# legacy harness-plan.md 마이그레이션 (v0.8.0+)
python harness/bin/harness migrate-plan docs/harness-plan.md              # dry-run
python harness/bin/harness migrate-plan docs/harness-plan.md --apply      # 실제 갱신
python harness/bin/harness migrate-plan docs/harness-plan.md --apply --mark-skeleton-stale

# skeleton_hash 필드 마이그레이션 (v0.9.0+)
python harness/bin/harness migrate-skeleton-hash docs/harness-plan.md              # dry-run
python harness/bin/harness migrate-skeleton-hash docs/harness-plan.md --apply      # 실제 갱신

# 빌드 실패 원인 분류 + 권고 (v0.9.0+)
python harness/bin/harness analyze-failure
```

### 언제 쓰는가

| 상황 | 명령 |
|---|---|
| v0.7.0 이하 → v0.8.0 업그레이드 후 기존 plan | `migrate-plan --apply` |
| `skeleton_hash` 없다는 경고가 뜰 때 | `migrate-skeleton-hash --apply` |
| `/ha-build` 가 실패했는데 원인 불명 | `analyze-failure` |
| tasks.md 의존성을 시각적으로 확인 | `graph docs/tasks.md` |
| v0.9.x → v0.10.0 업그레이드 후 기존 plan | `migrate-v10 --apply` |

---

## v0.10.0 마이그레이션 (v0.9.x → v0.10.0)

v0.10.0 은 `harness-plan.md` frontmatter 에 lock 필드 4 개 (`frozen_status`, `frozen_at`, `locked_sections`, `ai_drafted_sections`) 를 추가한다. legacy plan 은 `frozen_status` 가 없으면 default `"drafting"` 으로 자동 로드되므로 즉시 crash 는 없다. 그러나 `/ha-build` 진입 게이트가 `frozen_status="frozen"` 을 요구하므로 아래 흐름을 따라야 한다.

### 권장 흐름

```bash
# 1. lock 필드를 frontmatter 에 명시적으로 박음 (drafting default)
python ~/.claude/harness/bin/harness migrate-v10 docs/harness-plan.md           # dry-run
python ~/.claude/harness/bin/harness migrate-v10 docs/harness-plan.md --apply   # 실제 갱신

# 옵션: 기존 plan 을 검토 없이 곧바로 frozen 으로 올리기 (사용자 책임)
python ~/.claude/harness/bin/harness migrate-v10 docs/harness-plan.md --apply --auto-freeze

# 2. /ha-design 재실행 — LOCKED 섹션 HITL 인터뷰 통과 + freeze
/ha-design

# 3. /ha-build 정상 진행
/ha-build T-001
```

### escape hatch (개발 / CI 환경)

```bash
# frozen_status 게이트 건너뜀 (개발용 — 사용자 책임)
/ha-build T-001 --skip-frozen-gate

# PreToolUse hook 임시 비활성 (lock 검사 건너뜀)
HARNESS_SKIP_LOCK_HOOK=1 claude
```

### LOCKED 섹션 등록 (`<repo>/.claude/settings.json`)

외부 프로젝트에서 check_locked.py hook 을 적용하려면 `.claude/settings.json` 에 추가:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "python ~/.claude/harness/bin/check_locked.py"
          }
        ]
      }
    ]
  }
}
```

### 마이그레이션 전후 확인 사항

```
[ ] migrate-v10 --apply 실행 완료 (또는 --auto-freeze 로 즉시 frozen)
[ ] /ha-design 재실행 — LOCKED 섹션 인터뷰 완료 + frozen_status="frozen" 확인
[ ] harness validate — 0 errors
[ ] cd backend && uv run pytest tests/ — 939 pass
[ ] .claude/settings.json 에 check_locked.py hook 등록 (선택)
```

---

## 모바일 프로젝트 시작하기 (v0.6.0+)

HarnessAI 는 4개 모바일 스택을 지원합니다:
- React Native + Expo (`react-native-expo`)
- Flutter (`flutter`)
- Android Native (Kotlin + Jetpack Compose, `android-kotlin`)
- iOS Native (Swift + SwiftUI, `ios-swift`)

### 빠른 시작 (Flutter 예시)

```bash
# 1. HarnessAI clone + install
git clone https://github.com/reasonableplan/harnessai.git
cd harnessai && ./install.sh   # Windows: .\install.ps1
export HARNESS_AI_HOME=$(pwd)   # PowerShell: $env:HARNESS_AI_HOME='...'

# 2. Flutter 프로젝트 디렉토리로 이동 (또는 신규 생성)
cd ~/my-flutter-app
# 최소 pubspec.yaml 만 있으면 감지됨:
#   name: my_app
#   flutter:
#     sdk: flutter

# 3. /ha-init 호출 (Claude Code 세션에서)
# → detect 출력의 is_mobile: true 확인
# → guideline_paths 4개 모두 읽기
# → 6축 답변 시 data_sensitivity=pii 면 audit_log/threat_model 자동 활성

# 4. 이후 흐름: /ha-design → /ha-plan → /ha-build → /ha-verify → /ha-review → /ha-smoke
```

### iOS 개발 환경 제약

iOS native (`ios-swift`) 는 **macOS 가 권장 환경**:
- Windows 호스트: SwiftLint + `swift build` dry-run 만 가능
- 시뮬레이터 / 실기기 / `xcodebuild test` 는 macOS 에서만
- 호환성 문제 발생 시 `/ha-verify` 의 `platform_warnings` 가 친절 안내

### Android 개발 환경

- JAVA_HOME 환경변수 필수 (JDK 17+)
- `JAVA_HOME` 미설정 시 `/ha-verify` 의 `platform_warnings` 안내

### 모노레포 (모바일 + 백엔드 페어링)

`apps/mobile/` (Flutter) + `apps/api/` (FastAPI) 같은 monorepo 도 자동 감지. `/ha-init detect` 가 두 프로파일 모두 매칭 → `/ha-build` 가 task 별로 mobile_coder_flutter / backend_coder 분배.

### 4 프레임워크 비교 (어떤 걸 선택?)

| 스택 | 장점 | 적합 케이스 |
|---|---|---|
| react-native-expo | TypeScript / web 개발자 친숙 / 빠른 배포 | MVP / 모바일 우선 |
| flutter | 단일 코드베이스 / 풍부한 위젯 | 고품질 UI 우선 |
| android-kotlin | Material 3 네이티브 / 최고 성능 | Android 전용 / 성능 critical |
| ios-swift | iOS 통합 / Apple 생태계 | iOS 전용 / Apple 표준 |

---

## 6. 환경변수 설정

```bash
cp .env.example .env
```

최소 설정 (claude-cli 사용 시):

```env
# LLM — claude-cli는 별도 API 키 불필요

# Gemini API (gemini provider 사용 시에만 필요)
# GEMINI_API_KEY=your_key

# 로컬 모델 (local provider 사용 시에만 필요)
# LOCAL_MODEL_BASE_URL=http://localhost:11434/v1
# LOCAL_MODEL_NAME=llama3.1

# 대시보드
DASHBOARD_PORT=3002
DASHBOARD_HOST=127.0.0.1
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
LOG_LEVEL=info
```

> `DATABASE_URL`, `GITHUB_TOKEN` 등 `.env.example`의 다른 항목들은 HarnessAI 자체에서 사용하지 않는다. 에이전트가 생성하는 프로젝트가 이런 값들을 필요로 할 때 참고용으로 남겨둔 것이다.

---

## 7. 실행

### 대시보드 서버 (REST + WebSocket)

```bash
cd backend
uv run python -m src.main
```

서버 시작 후:
- REST API: `http://localhost:3002/api`
- WebSocket: `ws://localhost:3002/ws`
- 헬스체크: `http://localhost:3002/health`

### 인터랙티브 파이프라인 (CLI)

별도 터미널에서:

```bash
cd backend
uv run python -m src.orchestrator.pipeline_runner
```

실행 흐름:

```
1. 요구사항 입력 (자연어)
   예: "사용자가 할 일 목록을 관리하는 앱. FastAPI + React + SQLite."

2. [GATE 0] 요구사항 리뷰 결과 출력 → 승인 여부 입력 (y/n)

3. DESIGNING: Architect → Designer 순서로 skeleton 작성
   출력: backend/docs/skeleton.md

4. [GATE 1] Reviewer 엔지니어링 리뷰 결과 출력 → 승인 여부 입력 (y/n)

5. TASK_BREAKDOWN: Orchestrator가 태스크 목록 생성

6. [GATE 2] 태스크 목록 출력 → 승인 여부 입력 (y/n)

7. IMPLEMENTING: Backend Coder, Frontend Coder 순차 실행
   (SecurityHooks 자동 검사)

8. VERIFYING: Reviewer 코드 리뷰 → QA 통합 검증 (health score 0-10)

9. 완료
```

### skeleton.md가 이미 있을 때 (설계 단계 건너뛰기)

```bash
cd backend
uv run python -m src.orchestrator.pipeline_runner --from-skeleton
```

`/office-hours` 등으로 skeleton.md를 미리 작성한 경우 설계 단계를 건너뛰고 태스크 분해부터 시작한다.

### 대시보드 API로 직접 실행

```bash
# 에이전트 실행 명령
curl -X POST http://localhost:3002/api/command \
  -H "Content-Type: application/json" \
  -d '{"command": "start", "requirements": "할 일 관리 앱..."}'

# Phase 상태 조회
curl http://localhost:3002/api/tasks

# WebSocket 연결 (wscat 필요)
wscat -c ws://localhost:3002/ws
```

---

## 8. gstack 연동 (선택)

gstack 스킬을 함께 사용하면 각 게이트에서 AI 보조 검토를 추가할 수 있다.

### 설치

Claude Code가 설치된 환경에서:

```bash
claude   # Claude Code 실행
```

Claude Code 세션 내에서 gstack 설치 (별도 가이드 참조).

### 권장 워크플로우

```bash
# 1. 요구사항 분석 (HarnessAI 실행 전)
/office-hours
# → 핵심 가치, MVP 범위, 기술 리스크 구조화 출력

# 2. HarnessAI DESIGNING 완료 후 — skeleton 리뷰
/plan-eng-review
# → DB 정규화, API 일관성, 누락 엔드포인트 탐지

# 3. IMPLEMENTING 완료 후 — 코드 리뷰
/ha-review    # 보안훅 7 + LESSON 31 + ai-slop 7 + 테스트 분포
/ha-smoke     # 런타임 기동 probe (advisory)
/review       # SQL injection, 레이스 컨디션, 동시성

# 4. 배포
/ship         # PR 자동 생성

# 5. 회고
/retro        # 개선 사항 기록
```

gstack 없이도 HarnessAI는 완전히 동작한다. gstack은 각 게이트의 검토 품질을 높이는 선택적 레이어다.

---

## 9. 트러블슈팅

### claude: command not found

```bash
npm install -g @anthropic-ai/claude-code
claude login
```

### 에이전트 타임아웃

`agents.yaml`의 `timeout_seconds`를 늘리거나 `on_timeout: retry`로 변경.

```yaml
backend_coder:
  timeout_seconds: 900   # 기본 600 → 900으로 늘리기
  on_timeout: retry
  max_retries_on_timeout: 2
```

### 포트 충돌 (3002)

```bash
# .env에서 포트 변경
DASHBOARD_PORT=3003
```

또는 기존 프로세스 종료:

```bash
# macOS / Linux
lsof -i :3002 | grep LISTEN
kill <PID>

# Windows
netstat -ano | findstr :3002
taskkill /PID <PID> /F
```

### 상태 초기화 (처음부터 다시 시작)

```bash
rm -rf backend/.orchestra/
```

### 테스트 실행

```bash
cd backend
uv run pytest tests/ --rootdir=.
```

### QA health score가 낮아서 Phase가 계속 재시도됨

QA 임계값은 `backend/src/orchestrator/output_parser.py`의 `QA_PASS_THRESHOLD`(기본 7)로 조정한다.

```python
# output_parser.py
QA_PASS_THRESHOLD = 6   # 7 → 6으로 낮추면 통과 기준 완화
```
