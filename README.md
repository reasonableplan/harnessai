# Agent Orchestration System

AI 에이전트 팀이 GitHub Project Board를 기반으로 자율적으로 소프트웨어를 개발하는 멀티 에이전트 오케스트레이션 시스템.

실시간 오피스 시각화 대시보드에서 에이전트들의 작업 현황을 모니터링하고, 자연어로 명령을 내릴 수 있습니다.

## Architecture

```
사용자 (CLI / Dashboard)
        │
        ▼
   ┌─────────┐
   │ Director │ ── 계획 수립, 태스크 분배, 코드 리뷰
   │  (L0)    │
   └────┬─────┘
        │ GitHub Project Board (Backlog → Ready → In Progress → Review → Done)
   ┌────┴──────────────────────┐
   │            │              │              │
┌──▼──┐   ┌────▼───┐   ┌─────▼────┐   ┌────▼──┐
│ Git │   │Frontend│   │ Backend  │   │ Docs  │
│Agent│   │ Agent  │   │  Agent   │   │ Agent │
└─────┘   └────────┘   └──────────┘   └───────┘
  (L2)       (L2)          (L2)          (L2)
```

### 에이전트 역할

| Agent | Domain | 역할 |
|-------|--------|------|
| **Director** | orchestration | 사용자 요청을 Epic/Task로 분해, 에이전트에 할당, 코드 리뷰 |
| **Git** | git | 브랜치 생성, 커밋, PR 관리, 충돌 해결 |
| **Frontend** | frontend | React/UI 코드 생성, 컴포넌트 작성 |
| **Backend** | backend | API, 서버 로직, DB 스키마 코드 생성 |
| **Docs** | docs | README, API 문서, 주석 생성 |

### 핵심 설계

- **Board-Driven 자율 실행**: 에이전트들이 GitHub Project Board를 폴링하며 자기 태스크를 가져감
- **Board-First 원칙**: 외부(Board) 변경 후 내부(DB) 반영 (실패 시 DB 무결성 유지)
- **낙관적 잠금**: `claimTask()` — `UPDATE WHERE status='ready'` + rowCount 체크로 경합 방지
- **회복력**: Circuit Breaker, API Retry, Orphan Cleaner 내장
- **프롬프트 시스템**: 에이전트별 전문 프롬프트 (Markdown) + 공유 표준 (코드/워크플로우/품질/커뮤니케이션)

### Director 워크플로우 (Epic → Story → Sub-task 3계층)

```
사용자 ↔ Director: 아키텍처 논의       [GATHERING]
  스켈레톤(ProjectContext) 채워가며 요구사항 수집
         │
         ▼
Director: 초기 태스크 분해              [STRUCTURING]
  + Worker 에이전트 4명과 순차 상담
  (Backend/Frontend/DevOps/Docs 각각 검토·보강)
         │
         ▼
사용자: 계획 승인 (1차 허가)            [CONFIRMING]
         │
         ▼
Director: GitHub Project Board에        [COMMITTED]
  3계층 이슈 자동 생성:
  Epic → Stories → Sub-tasks
  라벨 자동 부여 + 프로젝트 보드 배치
  서브이슈 연결 (진행률 추적)
  플랜 상태 DB에 persist (서버 재시작 복원)
         │
         ▼
사용자: "시작해" (2차 허가)             [EXECUTING]
  의존성 없는 태스크 → Ready 전환
  에이전트 폴링 → 작업 시작
```

### Director와 아키텍처 정할 때 팁

- **구체적으로 말하기**: "Jira 만들어줘" 보다 "에이전트가 API로 폴링하는 태스크 관리 시스템" 처럼 핵심 동작을 설명
- **기술 스택 미리 정하기**: Director가 물어보기 전에 "FastAPI + React + PostgreSQL" 처럼 명시하면 빠름
- **MVP 경계 명확히**: 포함/제외 기능을 구분해주면 Director가 스코프를 정확히 잡음
- **한 번에 lock 요청**: 요구사항이 충분하면 "lock하고 태스크 분해해줘"로 GATHERING을 빠르게 통과

### 이슈 형식 커스터마이징

`prompts/expectations/` 디렉토리에 에이전트별 MD 파일로 기대사항을 정의할 수 있습니다:

```
prompts/expectations/
  agent-backend.md    ← 백엔드 에이전트 기대사항
  agent-frontend.md   ← 프론트엔드 에이전트 기대사항
  agent-git.md        ← Git/인프라 에이전트 기대사항
  agent-docs.md       ← 문서 에이전트 기대사항
```

이 파일에 작성한 내용은 Worker 상담 시 자동으로 프롬프트에 반영됩니다.
예: "API 설계 시 RESTful 원칙 준수", "shadcn/ui 컴포넌트 우선 사용" 등.

### 상담 로그 보는 법

Director가 Worker 에이전트와 상담하는 과정은 실시간으로 확인 가능합니다:

1. **서버 로그**: `Director says` 키워드로 필터링 — 각 에이전트 상담 시작/피드백 요약 표시
2. **WebSocket**: `director.message` 타입 메시지로 실시간 수신
3. **Dashboard**: (프론트엔드 연결 시) 채팅 패널에서 Director 메시지 확인

### 이슈 검수할 때 팁

- **3계층 확인**: Epic → Story → Sub-task 구조가 제대로 연결되었는지 GitHub에서 확인
- **의존성 체크**: Sub-task의 Dependencies 필드가 올바른지 검토
- **에이전트 배정**: 각 Sub-task의 라벨(backend/frontend/infra/docs)이 적절한지 확인
- **수정 요청**: STRUCTURING 단계에서 "이 태스크 분리해줘", "이 기능 추가해줘" 등 자유롭게 수정 가능
- **Story 단위 검토**: Story별로 기능 그룹이 논리적인지 확인 — 너무 크면 분리 요청

## Tech Stack

- **Backend**: Python 3.12 + FastAPI + asyncpg (PostgreSQL 비동기)
- **Package Manager**: uv (Python 의존성 관리)
- **LLM**: 3종 백엔드 지원 (아래 참조)
- **VCS/Board**: GitHub API + GitHub Projects V2 (GraphQL)
- **DB**: PostgreSQL 16 + SQLAlchemy ORM + Alembic 마이그레이션
- **Frontend**: TypeScript + React + Vite + Canvas (Stardew Valley 스타일 오피스)
- **Server**: FastAPI + WebSocket
- **Test**: pytest (59+ tests)

### LLM 백엔드 (3종 지원)

| 백엔드 | 설정 | 용도 |
|--------|------|------|
| **Anthropic API** | `ANTHROPIC_API_KEY=sk-ant-...` | 프로덕션 (API 크레딧) |
| **Claude Code CLI** | `USE_CLAUDE_CLI=true` | Claude Max 구독자 (무료) |
| **OpenAI 호환 모델** | `USE_LOCAL_MODEL=true` | 로컬 모델 (Ollama, LM Studio) 또는 클라우드 (HuggingFace, OpenRouter) |

> 자세한 설정: [docs/llm-backends.md](docs/llm-backends.md)

## Quick Start

### 1. 사전 요구사항

- **Python** 3.12 이상
- **uv** (Python 패키지 매니저, https://docs.astral.sh/uv/getting-started/)
- **Docker** (PostgreSQL용)
- **Node.js** 20 이상 (대시보드 프론트엔드용)
- **GitHub 계정** + Personal Access Token (repo, project 권한)
- **LLM 백엔드** — 아래 3가지 중 하나:
  - Anthropic API Key (`sk-ant-...`)
  - Claude Max 구독 + Claude Code CLI 설치
  - Ollama 등 로컬 모델 서버

### 2. 저장소 클론 및 의존성 설치

```bash
git clone https://github.com/reasonableplan/agent-orchestration.git
cd agent-orchestration

# Python 백엔드 의존성
cd backend
uv sync

# TypeScript 프론트엔드 의존성
cd ../packages/dashboard-client
pnpm install
cd ../..
```

### 3. 환경 변수 설정

```bash
cp backend/.env.example backend/.env
```

`backend/.env` 파일을 열어 아래 값을 설정합니다:

```env
# ===== LLM 백엔드 (3가지 중 택 1) =====

# 옵션 A — Anthropic API (기본값)
ANTHROPIC_API_KEY=sk-ant-...

# 옵션 B — Claude Code CLI (Max 구독자)
# USE_CLAUDE_CLI=true

# 옵션 C — 로컬/클라우드 모델 (Ollama, HuggingFace, OpenRouter 등)
# USE_LOCAL_MODEL=true
# LOCAL_MODEL_BASE_URL=http://localhost:11434/v1
# LOCAL_MODEL_NAME=llama3.1
# LOCAL_MODEL_API_KEY=              # 클라우드 서비스만 필요

# ===== GitHub 설정 (필수) =====
GITHUB_TOKEN=ghp_...
GITHUB_OWNER=your-username
GITHUB_REPO=your-repo-name
GITHUB_PROJECT_NUMBER=2

# ===== PostgreSQL (필수) =====
DATABASE_URL=postgresql://agent:agent@localhost:5433/agent

# ===== 선택 사항 =====
DASHBOARD_PORT=3000
GIT_WORK_DIR=./workspace
LOG_LEVEL=info
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
DASHBOARD_AUTH_TOKEN=
```

### 4. PostgreSQL 시작

Docker Compose로 PostgreSQL을 실행합니다:

```bash
docker compose up -d
```

PostgreSQL이 `localhost:5433`에서 실행됩니다 (user/password/db: `agent`).

> 이미 로컬에 PostgreSQL이 있다면 `DATABASE_URL`을 해당 연결 문자열로 변경하세요.

### 5. DB 마이그레이션

```bash
cd backend
uv run alembic upgrade head
cd ..
```

### 6. GitHub Project Board 준비

에이전트가 사용할 GitHub 저장소에 **Project (V2)** 를 생성합니다:

1. GitHub에서 새 Repository 생성 (또는 기존 repo 사용)
2. 해당 repo의 **Projects** 탭 → **New project** → **Board** 선택
3. Board에 아래 6개 컬럼을 생성:
   - `Backlog` → `Ready` → `In Progress` → `Review` → `Failed` → `Done`
4. URL에서 프로젝트 번호 확인 (예: `github.com/users/you/projects/2` → `2`)
5. `backend/.env`의 `GITHUB_PROJECT_NUMBER`에 입력

**레이블 생성** (에이전트 라우팅에 필요):

```bash
# GitHub CLI로 한 번에 생성
gh label create "agent:frontend" --color 61DAFB --repo OWNER/REPO
gh label create "agent:backend"  --color 68A063 --repo OWNER/REPO
gh label create "agent:docs"     --color F7DF1E --repo OWNER/REPO
gh label create "agent:git"      --color F05032 --repo OWNER/REPO
```

### 7. 시스템 시작

```bash
# 백엔드 (FastAPI + WebSocket)
cd backend
uv run python -m src.main
```

별도 터미널에서 프론트엔드:

```bash
cd packages/dashboard-client
pnpm dev
```

시스템이 시작되면:
- 대시보드: `http://localhost:5173` (Vite 개발 서버) 또는 `http://localhost:3000` (프로덕션)
- 백엔드 API: `http://localhost:3000/api`
- WebSocket: `ws://localhost:3000/ws`

## Usage

### CLI 사용법

시스템 시작 후 `agent>` 프롬프트에서 자연어로 명령합니다:

```
agent> 로그인 페이지를 만들어줘. 이메일/비밀번호 폼이 있어야 하고, 유효성 검사도 해줘.
```

Director가 요청을 분석하여 Epic과 Task를 생성하고, 적절한 에이전트에 할당합니다.

**시스템 명령어:**

| 명령어 | 설명 |
|--------|------|
| `/status` | 전체 에이전트 상태 조회 |
| `/pause` | 전체 시스템 일시정지 |
| `/resume` | 전체 시스템 재개 |
| `/pause @frontend` | 특정 에이전트 일시정지 |
| `/resume @frontend` | 특정 에이전트 재개 |
| `/retry <task-id>` | 실패한 태스크 재시도 |

### Dashboard 사용법

브라우저에서 `http://localhost:3000`에 접속합니다.

#### 메인 화면

Stardew Valley 스타일의 오피스에서 에이전트들이 실시간으로 움직입니다:

- **책상에 앉아 있음** → working / thinking / error / waiting
- **돌아다님** → idle (휴식 구역)
- **책장 쪽으로 이동** → searching (코드 검색 중)
- **디렉터 쪽으로 이동** → delivering (결과물 전달) / reviewing (코드 리뷰)

에이전트 상태별 색상:
- 초록: WORKING
- 노랑: THINKING
- 파랑: SEARCHING
- 보라: DELIVERING
- 주황: WAITING / REVIEWING
- 빨강: ERROR
- 회색: IDLE

#### 커맨드 바 (하단)

화면 하단의 `>` 입력창에서 명령을 입력합니다:

```
> 사용자 프로필 API를 만들어줘
```

자연어 입력은 Director 에이전트에게 전달됩니다.

**슬래시 명령어** (`/` 입력 시 자동완성):

| 명령어 | 설명 |
|--------|------|
| `/plan` | 현재 계획 조회 |
| `/status` | 에이전트 상태 조회 |
| `/pause [@agent]` | 전체 또는 특정 에이전트 일시정지 |
| `/resume [@agent]` | 전체 또는 특정 에이전트 재개 |
| `/retry <task-id>` | 실패한 태스크 재시도 |
| `/assign` | 태스크 수동 할당 |
| `/cancel` | 태스크 취소 |
| `/help` | 도움말 |

**에이전트 멘션** (`@` 입력 시 자동완성):

```
> @frontend 버튼 색상을 파란색으로 바꿔줘
> @backend API 응답에 pagination 추가해줘
```

#### 오른쪽 사이드바

3개의 탭으로 전환합니다:

- **ACTIVITY**: 실시간 에이전트 활동 로그
- **TOKENS**: 에이전트별 토큰 사용량, 예산 대비 비율
- **STATS**: 전체 시스템 통계 (완료율, 평균 소요시간, 실패 수)

#### 에이전트 상세 패널

캔버스에서 에이전트 캐릭터를 **클릭**하면 사이드바가 상세 패널로 전환됩니다:

- 현재 상태 및 진행 중인 태스크
- 토큰 사용량 (입력/출력 분리, 전체 대비 비율)
- 성능 지표 (완료율, 평균 소요시간, 실패/재시도 횟수)
- 할당된 태스크 목록 (컬럼별 색상 표시)
- 최근 활동 로그

하단 버튼:
- **SETTINGS**: 에이전트별 설정 (모델, 토큰 예산, 타임아웃, 폴링 간격)
- **CHARACTER**: 에이전트 캐릭터 외형 변경 (4종 캐릭터 선택)

### 대시보드 인증 (프로덕션)

네트워크에 대시보드를 노출할 경우, 인증 토큰을 설정합니다:

```env
# backend/.env
DASHBOARD_AUTH_TOKEN=your-secret-token
```

**인증 방식:**

REST API 호출 시 Authorization 헤더 사용:
```bash
curl -H "Authorization: Bearer your-secret-token" http://localhost:3000/api/agents
```

WebSocket 연결 시 인증 토큰 전송:
```javascript
// 연결 후 첫 메시지로 인증
ws.send(JSON.stringify({
  type: 'auth',
  token: 'your-secret-token'
}));
```

미설정 시 개발 모드로 동작하며 인증 없이 접근 가능합니다.

## Workflow: 에이전트가 일하는 과정

```
1. 사용자 요청       CLI/Dashboard에서 자연어 입력
       ↓
2. Director 계획     Claude로 분석 → Epic 생성, Task DAG 분해
       ↓
3. Board 배치        GitHub Issues 생성 (agent:* 레이블), 의존성 없는 태스크 → Ready
       ↓
4. Worker 선점       에이전트가 DB 폴링 → claimTask() 낙관적 잠금 → In Progress
       ↓
5. 코드 생성         Claude/로컬 모델로 코드 생성, workspace/에 파일 작성
       ↓
6. 리뷰 요청         Board → Review 이동, review.request 메시지 발행
       ↓
7. Director 리뷰     Claude로 코드 품질 검사 (director + qa 프롬프트)
       ↓
8. 승인/거절         승인 → Done + 후속 의존성 Ready 승격
                     거절 → Ready로 회귀 + 피드백 (최대 3회 재시도)
       ↓
9. 후속 작업         Follow-up Issues 자동 생성 (백엔드→프론트엔드/문서)
       ↓
10. Epic 완료        모든 Task Done → Epic 종료
```

## Prompt System

에이전트별 전문화된 시스템 프롬프트가 마크다운 파일로 관리됩니다:

```
prompts/
  shared/                    ← 모든 에이전트 공통
    code-standards.md        ← TypeScript, SOLID, API, DB, 보안 표준
    quality-gates.md         ← 성능 예산, OWASP, 테크 데빗 관리
    workflow.md              ← 6단계 워크플로우, 3단계 리뷰 파이프라인
    communication.md         ← 10종 메시지 타입, 커뮤니케이션 규칙
  director.md                ← 인터뷰 프로토콜, 아키텍처, 태스크 분해
  backend.md                 ← API/DB/인증/보안 전문성
  frontend.md                ← 컴포넌트/상태/스타일/접근성
  git.md                     ← 브랜칭/CI/PR/커밋 전략
  docs.md                    ← 문서 생성 + 작업 이력 기록
  qa.md                      ← 테스팅 전략, 에지 케이스, Definition of Done
```

에이전트 시작 시 `PromptLoader`가 shared + agent-specific 프롬프트를 결합하여 시스템 프롬프트로 사용합니다. 코드 변경 없이 프롬프트만 수정하여 에이전트 행동을 조정할 수 있습니다.

> 자세한 구조: [docs/prompt-system.md](docs/prompt-system.md)

## Project Structure

```
backend/                         — Python/FastAPI 백엔드
  src/
    agents/                      — 에이전트 구현 (director, git, backend, frontend, docs)
    core/
      agent/                     — BaseAgent, BaseCodeGenerator
      board/                     — BoardWatcher (GitHub Projects V2 폴링)
      config.py                  — AppConfig (환경변수 중앙화)
      db/                        — SQLAlchemy 스키마, DB 세션
      errors.py                  — 에러 타입
      git_service/               — GitHub API 퍼사드 (Issue, Board, Git)
      hooks/                     — HookRegistry, built-in 훅
      io/                        — FileWriter, FollowUpCreator
      llm/                       — ClaudeClient, ClaudeCliClient, LocalModelClient, PromptLoader
      logging/                   — structlog 기반 로깅
      messaging/                 — MessageBus (이벤트 발행/구독)
      resilience/                — CircuitBreaker, withRetry, OrphanCleaner
      state/                     — StateStore (DB 쿼리), TaskStateMachine
      types.py                   — 공유 타입 정의
    dashboard/
      server.py                  — FastAPI 앱 생성, REST 라우트
      event_mapper.py            — MessageBus → WebSocket 브로드캐스트
      ws_manager.py              — WebSocket 연결 관리
    bootstrap.py                 — 시스템 초기화 (에이전트 생성, 리소스 설정)
    main.py                      — 진입점 (uvicorn + 에이전트 폴링)
  tests/                         — pytest 기반 테스트 (59+)
  alembic/                       — SQLAlchemy 마이그레이션
  pyproject.toml                 — uv 의존성 관리
packages/
  dashboard-client/              — TypeScript + React + Vite + Canvas
    src/
      components/                — UI 컴포넌트
      engine/                    — Canvas 렌더링 (character, tile, tilemap)
      hooks/                     — WebSocket 훅 (useWebSocket)
      store.ts                   — Zustand 상태관리
    public/assets/               — 캐릭터, 타일셋 이미지
prompts/                         — 마크다운 기반 시스템 프롬프트
  shared/                        — 모든 에이전트 공통 (코딩 표준, 워크플로우, 품질 기준)
  director.md, backend.md, ...   — 에이전트별 특화 프롬프트
docs/                            — 설계 문서
  implementation-spec.md         — DB 스키마, 타입, 부트스트랩 명세
  llm-backends.md                — LLM 백엔드 설정 가이드
  prompt-system.md               — 프롬프트 로더 아키텍처
  workflow-*.md                  — 워크플로우 상세
```

## Development

### 백엔드

```bash
cd backend

# 의존성 설치
uv sync

# 테스트 실행 (59+ tests)
uv run pytest

# 테스트 워치 모드 (선택적)
uv run pytest --tb=short -v

# 포맷 + 린트 (ruff)
uv run ruff check . --fix
uv run ruff format .

# 린트만 (에러만 표시)
uv run ruff check .

# DB 마이그레이션 생성 (스키마 변경 후)
uv run alembic revision --autogenerate -m "description"

# DB 마이그레이션 적용
uv run alembic upgrade head

# 마이그레이션 롤백
uv run alembic downgrade -1

# 백엔드 실행 (개발 모드)
uv run python -m src.main
```

### 프론트엔드

```bash
cd packages/dashboard-client

# 의존성 설치
pnpm install

# 개발 서버 (HMR)
pnpm dev

# 프로덕션 빌드
pnpm build

# 프로덕션 미리보기
pnpm preview

# 린트
pnpm lint

# 포맷 체크
pnpm format:check
```

### 대시보드 데모 모드

서버 없이 대시보드만 확인하고 싶다면:

```bash
cd packages/dashboard-client
pnpm dev
```

3초 내에 WebSocket 연결이 안 되면 자동으로 데모 모드로 전환됩니다.
에이전트들이 랜덤으로 움직이며 UI를 미리 볼 수 있습니다.

## Documentation

| 문서 | 설명 |
|------|------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 시스템 아키텍처, 컴포넌트 관계, 통신 경로 |
| [docs/llm-backends.md](docs/llm-backends.md) | LLM 백엔드 3종 설정 가이드 |
| [docs/prompt-system.md](docs/prompt-system.md) | 프롬프트 시스템 구조와 커스터마이징 |
| [docs/implementation-spec.md](docs/implementation-spec.md) | DB 스키마, 타입, 부트스트랩 구현 명세 |
| [docs/deployment.md](docs/deployment.md) | Docker, CI/CD, 프로덕션 배포 |
| [docs/error-handling.md](docs/error-handling.md) | 에러 복구 전략, Circuit Breaker |
| [docs/security.md](docs/security.md) | 보안 정책, 프롬프트 인젝션 방어 |

## License

MIT
