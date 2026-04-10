# Project Skeleton

## 1. Overview
- **프로젝트명**:
- **한 줄 설명**:
- **목적**: (왜 만드는가?)
- **타겟 사용자**:

## 2. 기능 요구사항
### 핵심 기능 (MVP)
- [ ]
- [ ]
- [ ]

### 추가 기능 (후순위)
- [ ]
- [ ]

## 3. 기술 스택

### 프론트엔드 (TypeScript)
- **프레임워크**: React / Next.js (프로젝트 성격에 따라 결정)
- **상태 관리**: Zustand (UI/클라이언트 상태)
- **서버 상태**: TanStack Query (React Query)
- **HTTP 클라이언트**: axios (통일)
- **스타일링**: Tailwind CSS + CSS Modules
- **폼**: React Hook Form
- **라우팅**: React Router (React) / 내장 (Next.js)
- **UI 컴포넌트**: shadcn/ui 기반, 직접 구현 최소화

### 백엔드 (Python)
- **프레임워크**: FastAPI
- **ORM**: SQLModel
- **마이그레이션**: Alembic
- **인증**: python-jose (JWT) + passlib (해싱)
- **유효성 검증**: Pydantic (FastAPI 내장)
- **테스트**: pytest + httpx (AsyncClient)
- **DB**: (PostgreSQL / SQLite 등 프로젝트에 따라)

### 허용 라이브러리 화이트리스트
> 아래 목록에 없는 라이브러리는 Architect 승인 필요

**프론트엔드:**
- react, react-dom
- zustand
- @tanstack/react-query
- axios
- tailwindcss, postcss, autoprefixer
- react-hook-form
- react-router-dom (React 사용 시)
- @radix-ui/* (shadcn 의존성)
- class-variance-authority, clsx, tailwind-merge (shadcn 유틸)
- lucide-react (아이콘)
- zod (스키마 검증)

**백엔드:**
- fastapi, uvicorn
- sqlmodel, sqlalchemy
- alembic
- python-jose, passlib, bcrypt
- pydantic, pydantic-settings
- httpx
- pytest, pytest-asyncio

## 4. 에이전트 운영 설정
> 각 에이전트의 provider, 모델, 프롬프트 경로 등 **운영/인프라** 설정.
> 행동 규칙과 가드레일은 [14. 하네스 설계](#14-하네스-설계-harness-engineering) 참조.

```yaml
# agents.yaml — 에이전트 런타임 설정
# provider: claude-cli | gemini | openai | local
# model: 각 provider별 모델명
# prompt_path: 에이전트별 시스템 프롬프트 파일

architect:
  provider: claude-cli
  model: opus
  prompt_path: agents/architect/CLAUDE.md
  timeout_seconds: 300
  on_timeout: escalate          # escalate | retry | log_only
  max_retries_on_timeout: 1     # retry일 때만 적용
  max_tokens: 8192

designer:
  provider: claude-cli
  model: opus
  prompt_path: agents/designer/CLAUDE.md
  timeout_seconds: 300
  on_timeout: escalate
  max_retries_on_timeout: 1
  max_tokens: 8192

orchestrator:
  provider: claude-cli
  model: opus
  prompt_path: agents/orchestrator/CLAUDE.md
  timeout_seconds: 180
  on_timeout: retry             # Orchestrator는 가벼운 작업이므로 재시도
  max_retries_on_timeout: 2
  max_tokens: 4096

backend_coder:
  provider: claude-cli
  model: sonnet
  prompt_path: agents/backend_coder/CLAUDE.md
  timeout_seconds: 600
  on_timeout: retry             # Coder는 긴 작업이므로 1회 재시도 후 에스컬레이션
  max_retries_on_timeout: 1
  max_tokens: 16384

frontend_coder:
  provider: claude-cli
  model: sonnet
  prompt_path: agents/frontend_coder/CLAUDE.md
  timeout_seconds: 600
  on_timeout: retry
  max_retries_on_timeout: 1
  max_tokens: 16384

reviewer:
  provider: claude-cli
  model: opus
  prompt_path: agents/reviewer/CLAUDE.md
  timeout_seconds: 300
  on_timeout: escalate          # 리뷰 타임아웃은 바로 PM에 알림
  max_retries_on_timeout: 0
  max_tokens: 8192

qa:
  provider: claude-cli
  model: opus
  prompt_path: agents/qa/CLAUDE.md
  timeout_seconds: 600
  on_timeout: retry
  max_retries_on_timeout: 1
  max_tokens: 8192
```

### 에이전트 교체 예시
```yaml
# 예: 백엔드 코더를 로컬 LLM으로 교체
backend_coder:
  provider: local
  model: qwen-2.5-coder-32b
  prompt_path: agents/backend_coder/CLAUDE.md
  api_base: http://localhost:11434/v1

# 예: Architect를 Gemini로 교체
architect:
  provider: gemini
  model: gemini-2.5-pro
  prompt_path: agents/architect/CLAUDE.md
```

## 5. 인증/권한
- **인증 방식**: (JWT / 세션 / OAuth)
- **토큰 전달**: (Authorization 헤더 / 쿠키)
- **역할(Role)**:
- **권한 매트릭스**:

| 역할 | 리소스 A | 리소스 B | 리소스 C |
|------|---------|---------|---------|
|      |         |         |         |

### JWT 토큰 전략 (Architect 작성)
- **Access Token 만료**: (예: 15분)
- **Refresh Token 만료**: (예: 7일)
- **갱신 플로우**:
```
1. 클라이언트가 API 요청
2. 401 응답 (Access Token 만료)
3. axios interceptor가 자동으로 /auth/refresh 호출
4. 새 Access Token 발급 → 원래 요청 재시도
5. Refresh Token도 만료 → 로그아웃 처리
```
- **로그아웃 처리**: (블랙리스트 / DB 무효화 / 프론트만 삭제)
- **토큰 저장 위치**: (localStorage / httpOnly cookie)

## 6. DB 스키마 (Architect 작성)

### DB 설계 필수 규칙 (Architect가 채우기 전 확인)
- **ID 타입**: Integer auto-increment / UUID 중 선택 명시 (SQLModel 기본값 = Integer)
- **datetime**: 모든 컬럼 `DateTime(timezone=True)` — timezone-naive TIMESTAMP 금지
- **`updated_at` 갱신 방식**: `onupdate=func.now()` 또는 서비스 명시적 갱신 중 선택 명시
- **FK ondelete**: CASCADE / SET NULL / RESTRICT 중 명시 필수
- **index**: 자주 조회하는 FK 컬럼에 `index=True`
- **limit 상한**: 화면별 최대 표시 개수 API 설계 시 명시 (보드/백로그 ≥ 500, 일반 목록 ≤ 50)

### 테이블
| 테이블명 | 컬럼 | 타입 | 제약조건 | 설명 |
|---------|------|------|---------|------|
|         |      |      |         |      |

### 관계도
(Architect가 채움)

## 7. API 스키마 (Architect 작성)

### 공통 규칙
- **네이밍**: API 응답은 `camelCase` (프론트 친화), 백엔드 내부는 `snake_case`
  - FastAPI `model_config = {"alias_generator": to_camel, "populate_by_name": True}`
- **에러 응답 형식**:
```json
{
  "error": "에러 메시지",
  "code": "ERROR_CODE",
  "details": {}
}
```
- **날짜/시간**: ISO 8601 (`2026-04-01T09:00:00Z`)
- **페이지네이션**:
```json
{
  "items": [],
  "total": 100,
  "page": 1,
  "limit": 20
}
```

### 엔드포인트
| Method | Path | Request | Response | 설명 |
|--------|------|---------|----------|------|
|        |      |         |          |      |

### 공유 타입 (프론트↔백엔드 계약)
```typescript
// Architect가 정의 — 프론트엔드 타입의 source of truth
// 백엔드 Pydantic 모델은 이 타입과 1:1 매칭되어야 함
```

## 8. UI/UX (Designer 작성)

### 화면 목록
| 화면 | 경로 | 핵심 컴포넌트 | 설명 |
|------|------|-------------|------|
|      |      |             |      |

### 사용자 흐름
(Designer가 채움)

### 컴포넌트 트리
(Designer가 채움)

### 상태 관리 설계
- **서버 데이터 + UI 상태 (Zustand)**: store action이 API 직접 호출. per-feature store는 `containers/feature/store/`
- **전역 상태 (shared/store)**: 인증 정보, 앱 전반 UI 상태만 (사이드바, 전역 필터 등)
- **로컬 상태**: 폼 입력, 모달, 드롭다운 등
- **URL params = source of truth**: projectId/issueId 등 영구 컨텍스트는 useParams()로. Zustand는 폴백만

### 디자인 가이드
- **디자인 시스템 소스**: (shadcn/ui 기본 테마 / 커스텀 — 커스텀 시 Mobbin/Dribbble 레퍼런스 URL 첨부 필수)
  > Designer가 직접 색상/간격을 정의하면 시각적 품질 보장 불가 (LESSON-014). shadcn/ui 기본 테마 권장.
- **색상 팔레트**:
- **폰트**:
- **레이아웃 방향**:
- **반응형 기준**:

## 9. 에러 핸들링 전략

### 백엔드 (Architect 작성)
- **글로벌 예외 핸들러**: FastAPI exception_handler로 일관된 에러 응답
- **에러 코드 체계**:
```
AUTH_001: 인증 실패
AUTH_002: 토큰 만료
AUTH_003: 권한 없음
VALIDATION_001: 입력값 검증 실패
RESOURCE_001: 리소스 없음
RESOURCE_002: 중복 리소스
SERVER_001: 내부 서버 에러
```
- **로깅**: 에러 발생 시 트레이스 포함 로깅 (사용자에겐 코드만 노출)

### 프론트엔드 (Designer 작성)
- **React Error Boundary**: 페이지 레벨 / 컴포넌트 레벨 분리
- **axios interceptor 에러 처리**:
  - 401 → 토큰 갱신 시도 → 실패 시 로그인 페이지
  - 403 → "권한 없음" 토스트
  - 404 → Not Found 페이지
  - 422 → 폼 필드별 에러 표시
  - 500 → "잠시 후 다시 시도" 토스트
- **React Query 에러 처리**:
  - retry: 네트워크 에러만 3회 재시도
  - 비즈니스 에러 (4xx): 재시도 안 함
- **에러 UI 가이드라인**:
  - 토스트: 일시적 에러 (네트워크, 서버)
  - 인라인: 폼 검증 에러
  - 전체 페이지: 404, 500, 인증 만료

## 10. 상태 흐름 (비즈니스 로직)
> 핵심 엔티티의 상태 전이 규칙. 프론트↔백엔드가 동일하게 따라야 함.

### 상태 전이도
```
예: OPEN → IN_PROGRESS → REVIEW → DONE
                ↑                   |
                └───── REJECTED ←───┘
```

### 전이 규칙
| From | To | 조건 | 트리거 |
|------|----|------|--------|
|      |    |      |        |

## 11. 외부 연동
| 서비스 | 용도 | 연동 방식 | 필요한 키 |
|--------|------|----------|----------|
|        |      |          |          |

## 12. 환경 설정 / DevOps

### 환경변수 구조
```env
# .env.example — 프로젝트 셋업 시 복사해서 .env로 사용
# === App ===
APP_NAME=
APP_ENV=development          # development | staging | production

# === Database ===
DATABASE_URL=postgresql://user:pass@localhost:5432/dbname

# === Auth ===
JWT_SECRET_KEY=
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# === External Services ===
GITHUB_TOKEN=
GITHUB_REPO=

# === Agent Config ===
ARCHITECT_PROVIDER=claude-cli
ARCHITECT_MODEL=opus
```

### Docker
```yaml
# docker-compose.yml 구조 (Architect가 작성)
services:
  backend:
  frontend:
  db:
```

### CI/CD
- **린트/테스트**: PR 생성 시 자동 실행
- **배포**: (수동 / 자동 — 프로젝트에 따라)

### 로컬 개발 셋업
```bash
# 1. 클론
# 2. 환경변수 설정 (.env.example → .env)
# 3. DB 마이그레이션
# 4. 백엔드 실행 (Architect가 채움 — 반드시 실제 명령어 명시)
#    예: uv run uvicorn main:app --reload --port 8000
# 5. 프론트엔드 실행
#    예: npm run dev
```
> ⚠️ 실행 명령어 미명시는 LESSON-012 위반. Backend Coder는 `main.py`에 uvicorn 블록 추가 필수.

### 테스트 전략 (Architect 작성)
> 이 섹션이 비어있으면 Orchestrator는 테스트 태스크를 task breakdown에 포함하지 않음 → 프론트 테스트 0개로 완료됨 (LESSON-013)

**백엔드:**
- 테스트 프레임워크: pytest + httpx AsyncClient
- 커버리지 목표:
- 필수 테스트 범위: (예: 모든 API 엔드포인트 happy path + 주요 에러 케이스)

**프론트엔드:**
- 테스트 프레임워크: vitest + @testing-library/react
- 커버리지 목표:
- 필수 테스트 범위: (예: store action, 핵심 비즈니스 로직 계산 함수)
- 화이트리스트 추가: `vitest`, `@testing-library/react`, `@testing-library/user-event`, `jsdom`

## 13. 비기능 요구사항
- **동시 사용자**:
- **응답 속도 목표**:
- **배포 환경**:
- **모니터링**:

## 14. 하네스 설계 (Harness Engineering)

### 14-1. 에이전트 행동 규칙 & 가드레일
> 운영 설정(provider, model)은 [4. 에이전트 운영 설정](#4-에이전트-운영-설정) 참조.
> 이 섹션은 각 에이전트의 **행동 범위, 권한, 제약** 을 정의한다.

| 에이전트 | 할 수 있는 것 | 할 수 없는 것 (가드레일) |
|---------|-------------|----------------------|
| Architect | skeleton 수정, DB/API 스키마 정의, ADR 작성, 기술 결정 | 코드 직접 구현, 화이트리스트 외 기술 도입 |
| Designer | UI/UX 설계, 컴포넌트 구조, 상태 관리 설계, 디자인 가이드 | Architect 승인 없이 API/DB 스키마 변경 |
| Orchestrator | 태스크 분해, Board 관리, 에이전트 할당, 에스컬레이션 | 태스크 직접 구현, skeleton 수정 |
| Backend Coder | skeleton 계약 범위 내 백엔드 코드 작성, 테스트 작성 | skeleton에 없는 API 추가, 화이트리스트 외 라이브러리 설치 |
| Frontend Coder | skeleton 계약 범위 내 프론트 코드 작성, 테스트 작성 | skeleton에 없는 컴포넌트/페이지 추가, 화이트리스트 외 라이브러리 설치 |
| Reviewer | PR diff 검토, skeleton 대비 검증, reject/approve | 코드 직접 수정 (리뷰 코멘트만 가능) |
| QA | 통합 테스트 작성/실행, 불일치 탐지, 이슈 생성 | 기능 코드 수정 (테스트 코드만 작성 가능) |

### 14-2. 검증 파이프라인 (생성 → 검증 → 수정 루프)
```
Coder가 코드 생성 → branch + PR
    ↓
[자동 검증 — 1차]
  ├─ 린터 (Black/ESLint)
  ├─ 타입 체크 (mypy/tsc)
  ├─ 테스트 (pytest/vitest)
  └─ 스키마 검증 (skeleton 계약 대비 API 응답 형식 체크)
    ↓
  실패 → Coder에 에러 로그 전달 → 수정 → 재검증 (최대 3회)
    ↓
[코드 리뷰 + 보안 — 2차] (/review + /cso)
  /review — PR diff 분석:
  ├─ skeleton 계약 준수 여부
  ├─ SQL 안전성, 조건부 부수효과
  ├─ 코딩 컨벤션 준수 여부
  └─ 버그 탐지 + 자동 수정
  /cso — 보안 감사:
  ├─ OWASP Top 10 체크
  ├─ 하드코딩 시크릿 탐지
  ├─ 의존성 공급망 검사
  └─ STRIDE 위협 모델링
    ↓
  Reviewer 에이전트가 /review + /cso 결과 종합 판단:
  reject → 사유 + 수정 가이드 → Coder 재작업 (최대 2회)
  approve → merge 대기
    ↓
  ※ /review는 직접 수정 가능, Reviewer 에이전트는 리뷰 코멘트만 (역할 분리)
    ↓
[시각 검증 — 3차] (/browse — 프론트 변경 시에만)
  /browse — 헤드리스 Chromium (~100ms):
  ├─ 해당 페이지 스크린샷
  ├─ 레이아웃 깨짐 확인
  ├─ 반응형 체크
  └─ 콘솔 에러 체크
    ↓
  실패 → Coder에 스크린샷 + 에러 로그 전달 → 수정
    ↓
[통합 검증 — 4차] (/qa)
  merge 후 /qa 실행:
  ├─ 실제 브라우저로 E2E 시나리오 테스트
  ├─ 프론트↔백엔드 API 계약 일치 검증
  ├─ 상태 흐름 정합성
  ├─ 버그 발견 시 직접 수정 + 커밋
  └─ before/after health score 리포트
    ↓
  실패 → 이슈 생성 → Orchestrator가 재분배
```

### 스킬 ↔ Phase 매핑 테이블
| Phase | 스킬 | 실행 시점 | 역할 |
|-------|------|----------|------|
| 1. 기획 | `/office-hours` | PM 요구사항 전달 후 | 아이디어 검증, "이거 정말 필요해?" |
| 2. 설계 | `/plan-eng-review` | Architect contract v1 후 | 아키텍처/데이터/엣지케이스 검증 |
| 2. 설계 | `/plan-design-review` | Designer UI/UX 후 | 디자인 품질 0~10점 평가 |
| 2. 설계 | `/plan-ceo-review` | Architect ↔ Designer 합의 후 | 전체 제품 관점 최종 확인 |
| 4. 구현 | `/review` | 매 PR마다 | 코드 버그 탐지 + 자동 수정 |
| 4. 구현 | `/cso` | 매 PR마다 | OWASP + STRIDE 보안 감사 |
| 5. 검증 | `/browse` | 프론트 변경 PR | 헤드리스 브라우저 시각 검증 |
| 5. 검증 | `/qa` | merge 후 | 실제 브라우저 E2E + 버그 수정 |
| 6. 배포 | `/ship` | 전체 태스크 완료 후 | 테스트 → VERSION → PR 생성 |
| 6. 배포 | `/land-and-deploy` | /ship 후 | PR 머지 → 배포 → canary 검증 |
| 주기적 | `/retro` | 매주 | 커밋/테스트/성과 분석 + 트렌드 추적 |

### 에스컬레이션 정책

**자동 검증 (1차) 실패:**
```
시도 1~3: Coder가 에러 로그 보고 자체 수정
시도 3 실패 → Reviewer에 에스컬레이션
  → Reviewer가 원인 분석 + 구체적 수정 지침 제공
  → Coder 재시도 (추가 2회)
시도 5 실패 → Orchestrator에 에스컬레이션
  → 태스크를 더 작은 단위로 분할
  → 또는 다른 Coder(다른 모델/provider)로 재배정
최종 실패 → PM(사용자)에 에스컬레이션
  → 사용자가 판단: 직접 수정 / 요구사항 변경 / 태스크 폐기
```

**LLM 리뷰 (2차) 실패:**
```
reject 1~2: Coder가 리뷰 코멘트 반영해서 재작업
reject 3: Architect에 에스컬레이션
  → skeleton 계약이 모호한 건 아닌지 확인
  → 계약 보강 or Coder에 더 구체적 지침
최종 실패 → PM(사용자)에 에스컬레이션
```

**통합 검증 (3차) 실패:**
```
실패 → QA가 이슈 생성 (원인 분류: 프론트/백엔드/스키마 불일치)
  → Orchestrator가 해당 Coder에 수정 태스크 배정
  → 수정 후 재검증
2회 연속 같은 원인 실패 → Architect에 에스컬레이션
  → skeleton 계약 수정 필요 여부 판단
```

### 14-3. 컨텍스트 아키텍처
> 레포지토리가 유일한 진실의 원천 (Single Source of Truth)

```
project-root/
  docs/
    skeleton.md          ← 프로젝트 계약서 (이 파일)
    architecture.md      ← 시스템 아키텍처 (Architect 관리)
    conventions.md       ← 코딩 컨벤션 상세 (Architect 관리)
    adr/                 ← Architecture Decision Records
      001-auth-jwt.md
      002-state-zustand.md
    shared-lessons.md    ← 에이전트들의 실수/학습 기록
  agents/
    architect/CLAUDE.md  ← 역할별 시스템 프롬프트
    designer/CLAUDE.md
    orchestrator/CLAUDE.md
    backend_coder/CLAUDE.md
    frontend_coder/CLAUDE.md
    reviewer/CLAUDE.md
    qa/CLAUDE.md
```

**컨텍스트 주입 매핑 테이블:**
> 각 에이전트에 skeleton의 어떤 섹션을 주입할지 정의. 불필요한 섹션은 주입하지 않아 컨텍스트를 절약한다.

| 에이전트 | 주입 섹션 | 추가 문서 |
|---------|----------|----------|
| Architect | 전체 (1~19) | `conventions.md`, `adr/`, `shared-lessons.md` |
| Designer | 1, 2, 3(프론트), 7, 8, 9(프론트), 10, 14-1, 14-4 | `shared-lessons.md` |
| Orchestrator | 1, 2, 4, 14-1, 14-2, 15, 16, 17 | `shared-lessons.md` |
| Backend Coder | 1, 2, 3(백엔드), 5, 6, 7, 9(백엔드), 10, 14-4, 18 | `conventions.md`, `shared-lessons.md` |
| Frontend Coder | 1, 2, 3(프론트), 7, 8, 9(프론트), 10, 14-4, 18 | `conventions.md`, `shared-lessons.md` |
| Reviewer | 전체 (요약 버전) | `conventions.md`, `adr/`, `shared-lessons.md` |
| QA | 1, 2, 7, 9, 10, 14-2, 14-4, 14-5, 18 | `shared-lessons.md` |

**지식 베이스 관리 규칙:**
- 슬랙/노션/구글닥스에만 있는 결정 → 반드시 `docs/`에 문서화
- 구두 합의 → ADR로 기록
- 에이전트가 실수한 패턴 → `shared-lessons.md`에 추가

### shared-lessons.md 구조
```markdown
# Shared Lessons — 에이전트 학습 기록

## 형식
각 항목은 아래 구조를 따른다. 자유 형식 금지.

### [LESSON-001] 패턴 이름
- **발생 에이전트**: backend_coder
- **날짜**: 2026-04-01
- **분류**: schema_mismatch | convention_violation | test_failure | security | library
- **원인**: API 응답에 snake_case 사용 — skeleton 계약의 camelCase 규칙 미확인
- **해결책**: FastAPI 모델에 `alias_generator=to_camel` 설정 추가
- **방지 규칙**: 모든 Pydantic 모델에 `model_config` 필수 확인
- **관련 파일**: `src/api/models/issue.py`

### [LESSON-002] ...
```

### 14-4. 골든 원칙 (Golden Principles)
> Reviewer/QA가 자동으로 시행하는 절대 규칙

1. **계약 우선**: skeleton에 정의되지 않은 API/타입은 구현 금지
2. **화이트리스트 강제**: 승인 없는 라이브러리 설치 = 즉시 reject
3. **타입 동기화**: 백엔드 Pydantic ↔ 프론트 TypeScript 타입 불일치 = reject
4. **에러 형식 통일**: 에러 코드 체계를 벗어난 응답 = reject
5. **테스트 필수**: 테스트 없는 PR = merge 불가
6. **네이밍 규칙**: API camelCase / 백엔드 snake_case 위반 = reject
7. **보안**: 하드코딩 시크릿, raw SQL, any 타입 = 즉시 reject

### 14-5. 가비지 컬렉션 (자동 정리)
> 주기적으로 코드↔문서 불일치를 탐지하고 수정하는 프로세스

**자동 검사 항목:**
- skeleton의 API 엔드포인트 목록 vs 실제 라우터 파일
- skeleton의 DB 스키마 vs 실제 모델 파일
- skeleton의 공유 타입 vs 실제 타입 정의
- `shared-lessons.md`에 기록된 패턴이 코드에서 반복되는지

**실행 주기:**
- PR 생성 시: Reviewer가 해당 PR 범위 내 검사
- 주 1회: QA가 전체 레포 대상 불일치 스캔 → 이슈 생성 or 자동 수정 PR

### 14-6. 관찰성 (Observability)

**에이전트 행동 로깅:**
```
logs/
  agents/
    2026-04-01_architect.log
    2026-04-01_backend_coder.log
    ...
```

**로그 포맷:**
```json
{
  "timestamp": "2026-04-01T09:00:00Z",
  "agent": "backend_coder",
  "action": "file_write",
  "target": "src/api/routes/issues.py",
  "status": "success",
  "duration_ms": 1200,
  "token_usage": { "input": 3500, "output": 800 },
  "error": null
}
```

**추적 항목:**
- 에이전트별 성공/실패율
- 평균 검증 루프 횟수 (1차에 통과? 3차까지 갔나?)
- reject 사유 분류 (스키마 불일치, 컨벤션 위반, 테스트 미작성 등)
- 토큰 사용량 / 비용
- 태스크 완료 시간

**실패 클러스터 분석:**
- 같은 에이전트가 같은 사유로 3회 이상 reject → 해당 에이전트 CLAUDE.md에 규칙 추가
- 같은 파일에서 반복 충돌 → skeleton 계약 보강 필요 신호

## 15. 워크플로우 (프로젝트 시작 → 배포)
> 에이전트들이 어떤 순서로 움직이는지 정의. Orchestrator가 이 흐름을 따라 태스크를 분배한다.

```
┌─────────────────────────────────────────────────────────────────┐
│ Phase 1: 기획 (Planning)                                        │
│                                                                 │
│  PM(사용자)                                                      │
│    → skeleton 섹션 1~2 작성 (Overview, 기능 요구사항)               │
│    → 기술 스택 선호 전달                                           │
│    → /office-hours 실행 — 아이디어 검증 + 리프레이밍                 │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│ Phase 2: 설계 (Design)                                          │
│                                                                 │
│  Architect                                                      │
│    → 섹션 5(인증), 6(DB), 7(API), 10(상태흐름) 작성                 │
│    → contract v1 생성                                            │
│    → /plan-eng-review 실행 — 아키텍처/데이터/엣지케이스 검증          │
│                                                                 │
│  Designer                                                       │
│    → 섹션 8(UI/UX) 작성 — Architect의 API 스키마 참조              │
│    → 화면 목록, 사용자 흐름, 컴포넌트 트리, 상태 관리 설계            │
│    → /plan-design-review 실행 — 디자인 품질 0~10점 평가             │
│                                                                 │
│  Architect ↔ Designer 합의                                       │
│    → Designer 요구로 DB/API 수정 필요 시 반영                       │
│    → 합의 사항 섹션 16에 기록                                      │
│    → contract v2 (최종) 확정                                      │
│    → /plan-ceo-review 실행 — 전체 제품 관점 최종 확인                │
│                                                                 │
│  PM 확인                                                         │
│    → contract v2 검토 → 승인 or 피드백                             │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│ Phase 3: 태스크 분해 (Task Breakdown)                             │
│                                                                 │
│  Orchestrator                                                   │
│    → contract v2 기반으로 섹션 17(태스크 분해) 작성                  │
│    → GitHub repo 생성 + Board에 태스크 등록                        │
│    → 의존성 순서 결정 (DB 모델 → API → 프론트 순)                   │
│    → 에이전트 배정                                                │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│ Phase 4: 구현 (Implementation)                                   │
│                                                                 │
│  Backend Coder                                                  │
│    → DB 모델 → API 엔드포인트 → 비즈니스 로직 → 테스트              │
│    → branch + PR 생성                                            │
│    → /review 실행 — 코드 버그 탐지 + 자동 수정                      │
│    → /cso 실행 — OWASP + STRIDE 보안 감사                         │
│                                                                 │
│  Frontend Coder (백엔드 API 준비 후)                               │
│    → 컴포넌트 → 페이지 → API 연동 → 상태 관리 → 테스트              │
│    → branch + PR 생성                                            │
│    → /review 실행 — 코드 버그 탐지 + 자동 수정                      │
│    → /cso 실행 — 보안 감사                                        │
│    → /browse 실행 — 헤드리스 브라우저 시각 검증                      │
│                                                                 │
│  (병렬 가능: 독립적 모듈은 동시 작업)                                │
│                                                                 │
│  Reviewer 병렬 처리 규칙:                                          │
│    → 동시 리뷰 최대 2개 PR (품질 유지)                               │
│    → 우선순위: ① 의존성 있는 태스크 ② 백엔드 PR ③ 프론트 PR           │
│    → 같은 파일을 수정하는 PR이 2개 이상이면 순차 리뷰 (충돌 방지)       │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│ Phase 5: 검증 (Verification)                                     │
│                                                                 │
│  Reviewer                                                       │
│    → PR별 검증 (14-2 검증 파이프라인 따름)                          │
│    → /review + /cso 결과를 종합 판단                               │
│    → skeleton 계약 대비 diff 검토                                  │
│    → approve / reject + 사유                                     │
│                                                                 │
│  QA                                                             │
│    → merge 후 /qa 실행 — 실제 브라우저 E2E + 버그 수정              │
│    → 프론트↔백엔드 API 계약 일치 검증                               │
│    → before/after health score 리포트                             │
│    → 불일치 발견 시 이슈 생성                                      │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│ Phase 6: 배포 (Deployment)                                       │
│                                                                 │
│  Orchestrator                                                   │
│    → 모든 태스크 완료 + QA 통과 확인                                │
│    → /ship 실행 — 테스트 → VERSION 범프 → PR 생성                  │
│                                                                 │
│  PM(사용자)                                                      │
│    → 최종 확인 → 배포 승인                                        │
│    → /land-and-deploy 실행 — PR 머지 → 배포 → canary 검증         │
│                                                                 │
│  주기적:                                                         │
│    → /retro 매주 실행 — 커밋/테스트/성과 분석 + 트렌드 추적          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Phase 전이 조건
| From | To | 조건 |
|------|----|------|
| Phase 1 → 2 | PM이 섹션 1~2 작성 완료 |
| Phase 2 → 3 | Architect ↔ Designer 합의 완료 + PM 승인 |
| Phase 3 → 4 | Orchestrator가 태스크 분해 + Board 등록 완료 |
| Phase 4 → 5 | Coder가 PR 생성 (태스크 단위로 Phase 4↔5 반복) |
| Phase 5 → 6 | 모든 태스크 merge + QA 통과 |
| Phase 6 → 완료 | PM 배포 승인 |

## 16. 합의 사항 (Architect ↔ Designer)

### 스키마 변경 이력
| 날짜 | 변경 | 사유 | 요청자 |
|------|------|------|--------|
|      |      |      |        |

## 17. 태스크 분해 (Orchestrator 작성)

### Phase 구조

| Phase | 범위 | 목표 |
|-------|------|------|
| Phase 1 | MVP — 핵심 기능만 | 이 Phase만으로 사용자가 핵심 흐름 완료 가능 |
| Phase 2+ | 확장 — MVP 이후 | Phase 1 완료 + Phase 리뷰 통과 후 시작 |

> **Phase 완료 조건**: 해당 Phase 전체 태스크 merge + Reviewer Phase 리뷰 APPROVE → 다음 Phase 시작

### Phase 1 태스크 (MVP)
| ID | 담당 | 의존성 | 설명 | 참조 파일 | 상태 |
|----|------|--------|------|-----------|------|
|    |      |        |      |           |      |
| P1-REVIEW | Reviewer | Phase 1 전체 | Phase 1 리뷰 | — | 대기 |

### Phase 2 태스크 (Phase 1 리뷰 통과 후 시작)
| ID | 담당 | 의존성 | 설명 | 참조 파일 | 상태 |
|----|------|--------|------|-----------|------|
|    |      |        |      |           |      |
| P2-REVIEW | Reviewer | Phase 2 전체 | Phase 2 리뷰 | — | 대기 |

## 18. 규칙 (Rules)

### 코딩 컨벤션
- Python: snake_case, Black 포맷터, type hint 필수
- TypeScript: camelCase, ESLint + Prettier

### 금지 패턴
- 화이트리스트에 없는 라이브러리 설치
- API 응답에 snake_case 직접 노출 (alias 사용)
- any 타입 사용 (TypeScript)
- 빈 catch 블록
- 테스트 없는 코드 머지

### 테스트 요구사항
- 백엔드: 모든 엔드포인트에 최소 1개 테스트
- 프론트엔드: 핵심 비즈니스 로직 테스트
- 통합: API 계약 일치 검증

## 19. 향후 확장 (Future)
> 현재는 로컬 파일 시스템 + CLI subprocess 기반. 규모가 커지면 아래 도입 검토.

### MCP (Model Context Protocol)
- **도입 시점**: Phase 3(태스크 분해) 시점에 도입 여부 판단 — GitHub API + DB + 슬랙만으로도 이미 3개이므로, 프로젝트 초기부터 필요할 수 있음
- **효과**: 에이전트가 도구에 접근하는 방식을 표준화 → 에이전트 교체 시 도구 연동 코드 재작성 불필요
- **구현 방향**:
```yaml
# 예: MCP 서버 매니페스트
mcp_servers:
  github:
    tools: [create_issue, create_pr, list_issues]
    permissions: [read, write]
  database:
    tools: [query, migrate]
    permissions: [read]  # write는 Architect 승인 필요
  slack:
    tools: [send_message]
    permissions: [write]
    channels: [agent-notifications]
```

### A2A (Agent2Agent Protocol)
- **도입 시점**: 다른 팀/서비스의 에이전트와 협업해야 할 때, 또는 에이전트를 원격 분산 실행할 때
- **효과**: 에이전트 간 통신 표준화 → 프레임워크/provider가 달라도 협업 가능
- **구현 방향**: 각 에이전트가 Agent Card를 발행하고, A2A 프로토콜로 태스크 위임

### 오케스트레이션 프레임워크 (LangGraph / CrewAI)
- **도입 시점**: 직접 구현한 Orchestrator의 한계가 보일 때 (복잡한 조건 분기, 병렬 실행 관리 등)
- **후보**: LangGraph (그래프 기반, Python 네이티브), CrewAI (역할 기반, 현재 구조와 유사)
