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
/ha-build T-001     # 태스크 구현 (병렬: --parallel T-001,T-002)
/ha-verify          # 프로파일 toolchain 실행 (test/lint/type)
/ha-review          # 보안/LESSON/AI-slop 종합 리뷰
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

> **주의**: 허용 라이브러리를 변경하면 `backend/docs/skeleton_template.md`의 섹션 3(기술 스택)도 함께 수정해야 Architect가 올바른 기술 스택으로 설계한다.

### 방법 B: 프로젝트 계약서 템플릿 수정

`backend/docs/skeleton_template.md`는 Architect + Designer가 채우는 19개 섹션의 구조를 정의한다.
프로젝트 유형에 맞게 섹션을 추가하거나 기본 제약을 바꿀 수 있다.

**예시 — 모든 프로젝트에 WebSocket 섹션 추가:**

```markdown
<!-- skeleton_template.md 에 섹션 추가 -->
## 18. WebSocket 이벤트 스키마
- 실시간 알림이 필요한 이벤트 목록
- 클라이언트 → 서버 / 서버 → 클라이언트 페이로드 타입
```

### 커스터마이징 후 확인 사항

```
[ ] agents/[에이전트]/CLAUDE.md 수정 완료
[ ] skeleton_template.md 섹션 3(기술 스택) 업데이트 (라이브러리 변경 시)
[ ] agents.yaml 모델/타임아웃 조정 (필요 시)
[ ] uv run pytest tests/ 통과 확인
```

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
/my-review    # 보안 14항목 + LESSON 패턴
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
