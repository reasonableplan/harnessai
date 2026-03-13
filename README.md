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

## Tech Stack

- **Runtime**: Node.js 20+, TypeScript, pnpm workspace (모노레포)
- **LLM**: Claude API (Anthropic)
- **VCS/Board**: GitHub API + GitHub Projects V2 (GraphQL)
- **DB**: PostgreSQL 16 + Drizzle ORM
- **Dashboard**: React + Vite + Canvas (Stardew Valley 스타일 오피스)
- **Server**: Express + WebSocket
- **Test**: Vitest (386+ tests)

## Quick Start

### 1. 사전 요구사항

- **Node.js** 20 이상
- **pnpm** 10 이상 (`corepack enable && corepack prepare pnpm@latest --activate`)
- **Docker** (PostgreSQL용)
- **GitHub 계정** + Personal Access Token (repo, project 권한)
- **Anthropic API Key** (Claude API)

### 2. 저장소 클론 및 의존성 설치

```bash
git clone https://github.com/reasonableplan/agent-orchestration.git
cd agent-orchestration
pnpm install
```

### 3. 환경 변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 열어 아래 값을 설정합니다:

```env
# 필수 — Claude API 키
ANTHROPIC_API_KEY=sk-ant-...

# 필수 — GitHub Personal Access Token (repo, project 스코프)
GITHUB_TOKEN=ghp_...

# 필수 — 에이전트가 작업할 GitHub 저장소
GITHUB_OWNER=your-username
GITHUB_REPO=your-repo-name

# 필수 — GitHub Projects V2 프로젝트 번호 (URL의 숫자: /projects/2 → 2)
GITHUB_PROJECT_NUMBER=2

# 필수 — PostgreSQL 연결 문자열
DATABASE_URL=postgresql://agent:agent@localhost:5433/agent

# 선택 — 대시보드 포트 (기본값: 3000)
DASHBOARD_PORT=3000

# 선택 — 에이전트가 코드를 작성할 작업 디렉토리
GIT_WORK_DIR=./workspace

# 선택 — 로그 레벨 (debug, info, warn, error)
LOG_LEVEL=info

# 선택 — CORS 허용 오리진 (쉼표 구분)
CORS_ORIGINS=http://localhost:3000,http://localhost:5173

# 선택 — 대시보드 인증 토큰 (비어 있으면 인증 비활성화)
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
pnpm db:migrate
```

### 6. GitHub Project Board 준비

에이전트가 사용할 GitHub 저장소에 **Project (V2)** 를 생성합니다:

1. GitHub에서 새 Repository 생성 (또는 기존 repo 사용)
2. 해당 repo의 **Projects** 탭 → **New project** → **Board** 선택
3. Board에 아래 6개 컬럼을 생성:
   - `Backlog` → `Ready` → `In Progress` → `Review` → `Failed` → `Done`
4. URL에서 프로젝트 번호 확인 (예: `github.com/users/you/projects/2` → `2`)
5. `.env`의 `GITHUB_PROJECT_NUMBER`에 입력

**레이블 생성** (에이전트 라우팅에 필요):

```bash
# GitHub CLI로 한 번에 생성
gh label create "agent:frontend" --color 61DAFB --repo OWNER/REPO
gh label create "agent:backend"  --color 68A063 --repo OWNER/REPO
gh label create "agent:docs"     --color F7DF1E --repo OWNER/REPO
gh label create "agent:git"      --color F05032 --repo OWNER/REPO
```

### 7. 빌드 및 실행

```bash
# 전체 빌드
pnpm build

# 시스템 시작
pnpm --filter @agent/main run start
```

시스템이 시작되면:
- CLI 프롬프트 (`agent>`)에서 직접 명령 입력 가능
- 대시보드: `http://localhost:3000` 접속

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

#### 캐릭터 변경

1. 에이전트 클릭 → 상세 패널 열기
2. **CHARACTER** 버튼 클릭
3. Adam / Alex / Amelia / Bob 중 선택
4. 선택 즉시 반영 (localStorage에 저장, 새로고침 후에도 유지)

#### 에이전트 설정

1. 에이전트 클릭 → 상세 패널 열기
2. **SETTINGS** 버튼 클릭
3. 설정 변경:
   - **Model**: Claude 모델 선택
   - **Token Budget**: 최대 토큰 사용량
   - **Timeout**: 태스크 타임아웃 (ms)
   - **Poll Interval**: Board 폴링 간격 (ms)
4. SAVE로 저장 (에이전트에 핫 리로드)

#### 키보드 단축키

| 키 | 동작 |
|----|------|
| `/` | 커맨드 바 포커스 + 슬래시 명령 모드 |
| `Arrow Up/Down` | 명령 히스토리 탐색 |
| `Tab` | 자동완성 선택 |
| `Esc` | 자동완성 닫기 |

### 대시보드 인증 (프로덕션)

네트워크에 대시보드를 노출할 경우, 인증 토큰을 설정합니다:

```env
# 서버 .env
DASHBOARD_AUTH_TOKEN=your-secret-token

# 클라이언트 (Vite 빌드 시)
VITE_DASHBOARD_AUTH_TOKEN=your-secret-token
```

## Workflow: 에이전트가 일하는 과정

1. **사용자가 요청** → CLI 또는 Dashboard에서 자연어 입력
2. **Director가 계획 수립** → Epic 생성, Task로 분해, `agent:frontend` 등 레이블로 에이전트 할당
3. **GitHub Board에 Issue 생성** → `Ready` 컬럼에 배치
4. **에이전트가 폴링** → 자기 도메인 레이블이 붙은 `Ready` 태스크를 발견
5. **태스크 선점** → `claimTask()`로 낙관적 잠금, `In Progress`로 이동
6. **코드 작성** → Claude API로 코드 생성, `workspace/` 디렉토리에 파일 작성
7. **결과물 제출** → Git 커밋, Board를 `Review`로 이동
8. **Director 리뷰** → 코드 품질 검사, 통과 시 `Done`, 수정 필요 시 피드백과 함께 `Ready`로 회귀
9. **반복** → 모든 Task 완료 시 Epic 종료

## Project Structure

```
packages/
  core/             — 공통 타입, DB 스키마, BaseAgent, MessageBus, StateStore,
                      GitService, Claude Client, 회복력 모듈
  agent-director/   — Director 에이전트 (계획, 디스패치, 리뷰)
  agent-git/        — Git 에이전트 (브랜치, 커밋, PR, 충돌 해결)
  agent-frontend/   — Frontend 에이전트 (React/UI 코드 생성)
  agent-backend/    — Backend 에이전트 (API/서버 코드 생성)
  agent-docs/       — Docs 에이전트 (문서 생성)
  dashboard-client/ — React + Canvas 오피스 시각화 대시보드
  dashboard-server/ — Express + WebSocket 대시보드 서버
  main/             — 부트스트랩, 에이전트 팩토리, 어댑터
```

## Development

```bash
# 의존성 설치
pnpm install

# 전체 빌드
pnpm build

# 테스트 실행
pnpm test

# 테스트 워치 모드
pnpm test:watch

# 린트
pnpm lint

# 포맷 체크
pnpm format:check

# DB 마이그레이션 생성 (스키마 변경 후)
pnpm db:generate

# DB 마이그레이션 적용
pnpm db:migrate

# 대시보드만 개발 모드로 실행 (HMR)
pnpm --filter @agent/dashboard-client run dev
```

### 대시보드 데모 모드

서버 없이 대시보드만 확인하고 싶다면:

```bash
pnpm --filter @agent/dashboard-client run dev
```

3초 내에 서버 연결이 안 되면 자동으로 데모 모드로 전환됩니다.
에이전트들이 랜덤으로 움직이며 UI를 미리 볼 수 있습니다.

## License

MIT
