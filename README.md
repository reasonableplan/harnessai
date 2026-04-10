# HarnessAI

AI가 코드를 잘 짜는 건 알겠는데, **내 스타일대로 짜지 않는다**. 기획 범위를 넘어서고, 허용하지 않은 라이브러리를 쓰고, 에러 처리 방식이 내 기준과 다르다.

직접 고치다 보면 결국 내가 다 짜는 거랑 다르지 않았다.

HarnessAI는 이 문제를 해결하기 위해 만들었다. **AI가 짜되, 내 규칙대로 짜게 하는 것.**

- `agents/*/CLAUDE.md` — 에이전트마다 코딩 규칙을 직접 정의한다
- skeleton 계약서 — 기획 범위를 19개 섹션으로 못 박는다. 벗어나면 Reviewer가 즉시 reject
- shared-lessons — 한 번 발생한 실수는 시스템에 기록해 반복을 막는다

AI를 대체하는 게 아니라 **통제하는** 오케스트레이터다.

---

AI 에이전트 팀이 **하네스 엔지니어링**(skeleton 계약서 + 검증 파이프라인)을 기반으로 자율적으로 소프트웨어를 개발하는 멀티 에이전트 오케스트레이션 시스템.

자연어 요구사항을 입력하면 7개의 전문화된 에이전트가 설계 → 태스크 분해 → 구현 → 리뷰 → QA까지 처리한다. 사람은 각 Phase 사이의 게이트에서 결과물을 검토하고 승인/거절한다.

---

## 핵심 개념: Skeleton 계약서

모든 구현의 출발점. Architect + Designer가 코드 한 줄 쓰기 전에 19개 섹션을 채운다.

```
섹션 1  — 프로젝트 개요 / 요구사항
섹션 2  — 기능 요구사항 (MVP / 확장)
섹션 3  — 기술 스택 + 허용 라이브러리 화이트리스트
섹션 5  — 인증/권한 (JWT access/refresh 흐름)
섹션 6  — DB 스키마 (테이블, 관계, 인덱스, 제약)
섹션 7  — API 스키마 (Method, Path, Request/Response 타입)
섹션 8  — UI/UX (화면 목록, 사용자 흐름, 컴포넌트 트리, 상태 관리 설계)
섹션 9  — 에러 핸들링 (에러 코드 체계, 프론트 처리 규칙)
섹션 10 — 상태 흐름 (비즈니스 로직 전이 규칙)
섹션 11 — 테스트 전략
섹션 17 — 태스크 목록 (Phase 분해 후 Orchestrator가 채움)
...
```

이 계약서가 에이전트들의 공통 기준이다.
화이트리스트에 없는 라이브러리는 Architect 승인 없이 추가 불가.
skeleton에 없는 API/화면은 구현 불가. Reviewer가 즉시 reject한다.

---

## 파이프라인 흐름

```
요구사항 입력 (자연어)
        │
        ▼
  ┌─────────────┐
  │   GATE 0    │  요구사항 리뷰 — 핵심 가치, MVP 범위, 기술 리스크 점검
  └──────┬──────┘
         │ 사람이 y/n 승인
         ▼
  ┌──────────────────────────────────────────────────┐
  │  DESIGNING                                        │
  │                                                   │
  │  Architect                                        │
  │  ├─ DB 스키마 설계 (TIMESTAMPTZ, onupdate, 인덱스) │
  │  ├─ API 설계 (camelCase 응답 / snake_case 내부)    │
  │  ├─ 에러 코드 체계 정의 (AUTH_001, RESOURCE_001…) │
  │  └─ 상태 흐름 정의                                │
  │                                                   │
  │  Designer (Architect 출력 기반으로)                │
  │  ├─ 화면 목록 + 라우팅 정의                        │
  │  ├─ 사용자 흐름도 (에러 케이스 포함)               │
  │  ├─ 컴포넌트 트리 (shadcn/ui 우선)                 │
  │  └─ 상태 관리 설계 (Zustand / useState 분리)       │
  └──────────────────────────────────────────────────┘
         │
         ▼
  ┌─────────────┐
  │   GATE 1    │  엔지니어링 리뷰 — DB/API/아키텍처 검증 (Reviewer 에이전트)
  └──────┬──────┘
         │ 사람이 y/n 승인
         ▼
  ┌──────────────────────────────────────────────────┐
  │  TASK_BREAKDOWN                                   │
  │                                                   │
  │  Orchestrator                                     │
  │  ├─ Phase 1 = MVP (없으면 핵심 흐름이 막히는 것만) │
  │  ├─ Phase 2+ = 확장 (필터, 통계, 알림 등)          │
  │  └─ 태스크 분해: DB모델 → API → 프론트 컴포넌트    │
  │     → 페이지 조합 (의존성 순서 강제)               │
  └──────────────────────────────────────────────────┘
         │
         ▼
  ┌─────────────┐
  │   GATE 2    │  태스크 목록 검토 — Phase 분해 / 의존성 검증
  └──────┬──────┘
         │ 사람이 y/n 승인
         ▼
  ┌──────────────────────────────────────────────────┐
  │  IMPLEMENTING                                     │
  │                                                   │
  │  Backend Coder (claude-cli / claude-sonnet-4-6)   │
  │  ├─ SQLModel ORM 기반 DB 모델                     │
  │  ├─ FastAPI 엔드포인트 (skeleton 섹션 7 정확히)    │
  │  ├─ alias_generator=to_camel (응답 camelCase)     │
  │  ├─ pytest + httpx 테스트 필수                    │
  │  └─ 허용 라이브러리: fastapi, uvicorn, sqlmodel,  │
  │     sqlalchemy, alembic, python-jose, passlib     │
  │                                                   │
  │  Frontend Coder (claude-cli / claude-haiku-4-5)   │
  │  ├─ React + TypeScript                            │
  │  ├─ Zustand store action에서만 API 호출            │
  │  ├─ CVA + index.style.ts 패턴 (JSX 인라인 금지)   │
  │  ├─ Tailwind v4 (@layer base 안에 리셋)            │
  │  ├─ axios interceptor (401→토큰 갱신, 403→토스트) │
  │  ├─ vitest 테스트 필수                            │
  │  └─ 허용: react, zustand, react-query, axios,     │
  │     tailwindcss, shadcn/ui, react-hook-form, zod  │
  │                                                   │
  │  SecurityHooks (모든 생성 코드 자동 검사)           │
  │  ├─ BLOCK: 하드코딩 시크릿                        │
  │  ├─ BLOCK: 위험 shell 명령 (rm -rf, DROP TABLE)   │
  │  ├─ BLOCK: 화이트리스트 외 패키지                  │
  │  ├─ WARN: 빈 except 블록                          │
  │  ├─ WARN: raw SQL 쿼리                            │
  │  └─ WARN: any 타입                               │
  └──────────────────────────────────────────────────┘
         │
         ▼
  ┌──────────────────────────────────────────────────┐
  │  VERIFYING                                        │
  │                                                   │
  │  Reviewer (claude-cli / claude-opus-4-6)          │
  │  ├─ grep 기반 자동 탐지 (눈으로만 보지 않음)       │
  │  ├─ 골든 원칙 7개 위반 시 즉시 reject             │
  │  │  1. skeleton에 없는 API/타입 구현 → reject     │
  │  │  2. 화이트리스트 외 라이브러리 → reject        │
  │  │  3. 백엔드 Pydantic ↔ 프론트 TS 타입 불일치    │
  │  │  4. 에러 응답 형식 위반                        │
  │  │  5. 테스트 없는 PR → merge 불가               │
  │  │  6. 네이밍 규칙 위반 (camelCase/snake_case)    │
  │  │  7. 하드코딩 시크릿, raw SQL, any 타입         │
  │  └─ shared-lessons 반복 패턴 탐지                 │
  │                                                   │
  │  QA (claude-cli / claude-opus-4-6)                │
  │  ├─ Reviewer APPROVE 이후 실행                    │
  │  ├─ API 계약 일치 검증 (skeleton 섹션 7 대조)      │
  │  ├─ 상태 흐름 정합성 검증 (섹션 10 대조)           │
  │  ├─ 프론트↔백엔드 TypeScript/Pydantic 타입 대조   │
  │  ├─ 문서↔코드 불일치 탐지 (가비지 컬렉션)          │
  │  └─ health score 0-10 (7 미만 시 Phase 재시도)    │
  └──────────────────────────────────────────────────┘
         │
         ▼
        DONE
```

---

## 에이전트 7개

| 에이전트 | Provider | 모델 | 역할 |
|---------|---------|------|------|
| **architect** | claude-cli | claude-opus-4-6 | skeleton 섹션 5/6/7/10 설계 (DB/API/인증/상태흐름) |
| **designer** | claude-cli | claude-opus-4-6 | skeleton 섹션 8 설계 (화면, 컴포넌트, 상태관리) |
| **orchestrator** | claude-cli | claude-opus-4-6 | skeleton → Phase/태스크 분해, 의존성 순서 결정 |
| **backend_coder** | claude-cli | claude-sonnet-4-6 | Python/FastAPI 구현, pytest 테스트 |
| **frontend_coder** | claude-cli | claude-haiku-4-5 | React/TS 구현, vitest 테스트 |
| **reviewer** | claude-cli | claude-opus-4-6 | PR 리뷰 + Phase 리뷰 + GATE 엔지니어링 리뷰, 골든 원칙 강제 |
| **qa** | claude-cli | claude-opus-4-6 | API 계약·상태흐름·타입 통합 검증, health score 산출 |

에이전트별 provider/model/timeout은 `backend/agents.yaml`에서 독립적으로 변경 가능.

---

## 스킬 파이프라인

HarnessAI는 Claude Code 스킬(`my-*`)과 gstack 스킬을 조합해 전체 개발 사이클을 자동화한다.

### 전체 흐름

```
[설계]
  /my-db-design          ← DB 스키마 설계 (skeleton 섹션 6)
  /my-architect          ← API·인증·상태흐름·에러코드 설계 (섹션 5,7,9,10)
  /my-designer           ← UI/UX·화면·컴포넌트 설계 (섹션 8)
  /my-skeleton-check     ← 19개 섹션 완성도 검증 (누락·불일치 탐지)
       │
       ▼
  /plan-eng-review       ← (선택) gstack: 아키텍처·DB·API 심층 리뷰
  /plan-design-review    ← (선택) gstack: UI/UX 설계 심층 리뷰
       │
       ▼
[태스크 분해]
  /my-tasks              ← skeleton → tasks.md 자동 생성 (의존성 그래프 포함)
       │
       ▼
[구현]
  /my-db                 ← DB 모델 + 마이그레이션 구현
  /my-api                ← API 엔드포인트 구현 (/my-db 이후)
  /my-ui                 ← UI 컴포넌트 구현 (/my-designer 이후)
  /my-logic              ← 상태관리 + API 연동 (/my-api + /my-ui 이후)
       │
       ▼
[검증]
  /my-type-check         ← tsc / pyright / ruff 타입·린트 검사
  /my-review             ← 보안 14항목 + LESSON 패턴 자동 탐지
  /review                ← (선택) gstack: SQL injection·레이스컨디션 심층 리뷰
       │
       ▼
[배포·회고]
  /ship                  ← (선택) gstack: PR 자동 생성
  /my-lessons            ← 실수 패턴 → shared-lessons.md 자동 추가
  /retro                 ← (선택) gstack: 주간 회고
```

### my-* 스킬 상세

| 스킬 | 단계 | 입력 | 출력 |
|------|------|------|------|
| `/my-db-design` | 설계 | 요구사항 | skeleton 섹션 6 (테이블·관계·인덱스) |
| `/my-architect` | 설계 | skeleton 섹션 6 | 섹션 5,7,9,10 (API·인증·에러코드·상태흐름) |
| `/my-designer` | 설계 | 요구사항 | skeleton 섹션 8 (화면·컴포넌트·상태관리) |
| `/my-skeleton-check` | 검증 | skeleton.md | 누락 섹션·API↔UI 불일치 리포트 |
| `/my-tasks` | 분해 | skeleton.md | docs/tasks.md (Phase별 태스크 + 의존성) |
| `/my-db` | 구현 | skeleton 섹션 6 | DB 모델 + 마이그레이션 코드 |
| `/my-api` | 구현 | skeleton 섹션 7 | API 엔드포인트 + 서비스 레이어 |
| `/my-ui` | 구현 | skeleton 섹션 8 | 화면·컴포넌트 코드 |
| `/my-logic` | 구현 | skeleton 섹션 7,8,10 | 상태관리(Zustand/store) + API 연동 |
| `/my-type-check` | 검증 | 현재 코드베이스 | tsc/pyright/ruff 에러 0개 확인 |
| `/my-review` | 검증 | 현재 코드베이스 | 보안 14항목 + LESSON 패턴 pass/fail |
| `/my-lessons` | 회고 | git log + 코드 | shared-lessons.md 신규 LESSON 추가 |

**스택 자동 감지**: 모든 `my-*` 스킬은 `package.json` / `pyproject.toml`을 읽어 스택(fastapi / nextjs / react-native / electron)을 자동으로 판별한다. 설정 없이 그냥 실행하면 된다.

---

## 코딩 스타일 커스터마이징

**에이전트의 코딩 방식은 두 곳에서 제어한다.**

### 1. `backend/agents.yaml` — 실행 환경 설정

provider, 모델, 타임아웃, 병렬 수를 조정한다. 코드 한 줄 없이 변경 가능.

```yaml
# 동시 실행 에이전트 수 제한 (기본: 2)
max_concurrent: 2

backend_coder:
  provider: claude-cli
  model: claude-sonnet-4-6   # 더 저렴한 모델로 교체 가능
  timeout_seconds: 600        # 복잡한 프로젝트라면 늘리기
  on_timeout: retry
  max_retries_on_timeout: 1

frontend_coder:
  provider: claude-cli
  model: claude-haiku-4-5    # 빠르고 저렴 — 프론트 코딩에 충분
  timeout_seconds: 600
```

`on_timeout` 옵션:

| 값 | 동작 |
|----|------|
| `retry` | `max_retries_on_timeout`만큼 재시도 |
| `escalate` | 즉시 사람에게 에스컬레이션 (게이트에서 멈춤) |
| `log_only` | 로그만 남기고 계속 진행 |

### 2. `backend/agents/[에이전트명]/CLAUDE.md` — 코딩 규칙 설정

각 에이전트의 시스템 프롬프트. 이 파일을 수정하면 에이전트가 쓰는 코드 스타일이 바뀐다.

**예시 — ORM을 SQLModel에서 SQLAlchemy로 바꾸고 싶다면:**

```markdown
<!-- backend/agents/backend_coder/CLAUDE.md 수정 전 -->
## DB
- SQLModel ORM 사용
- SQLite (개발) / PostgreSQL (프로덕션)

<!-- 수정 후 -->
## DB
- SQLAlchemy 2.0 Core 사용 (ORM 금지)
- PostgreSQL only
```

**예시 — 프론트엔드를 Next.js App Router로 바꾸고 싶다면:**

```markdown
<!-- backend/agents/frontend_coder/CLAUDE.md 수정 전 -->
## 스택
- React + Vite + Zustand

<!-- 수정 후 -->
## 스택
- Next.js 15 App Router
- Server Components 우선, 필요한 경우만 'use client'
- TanStack Query로 서버 상태 관리
```

**예시 — 허용 라이브러리(화이트리스트) 변경:**

```markdown
<!-- backend/agents/backend_coder/CLAUDE.md -->
## 허용 라이브러리 (화이트리스트)
- fastapi, uvicorn
- sqlalchemy, alembic      ← sqlmodel 대신
- python-jose, passlib
- redis                    ← 캐시 레이어 추가
```

> 화이트리스트를 변경하면 `backend/docs/skeleton_template.md`의 섹션 3도 함께 수정해야 Architect가 올바른 기술 스택으로 설계한다.

### 3. `backend/docs/skeleton_template.md` — 프로젝트 계약서 템플릿

Architect가 채우는 19개 섹션의 구조를 정의한다. 프로젝트 유형에 맞게 섹션을 추가/수정할 수 있다.

---

## 코딩 컨벤션 (에이전트 기본 설정)

### 백엔드 (Python/FastAPI)

```python
# ✅ API 응답: camelCase (alias_generator)
class IssueResponse(BaseModel):
    model_config = {"alias_generator": to_camel, "populate_by_name": True}
    project_id: int        # 내부 snake_case
    created_at: datetime   # 응답 시 자동으로 projectId, createdAt

# ✅ Query params: snake_case (alias_generator 미적용)
@router.get("/issues")
async def list_issues(project_id: int, sprint_id: int | None = None): ...
# ❌ projectId: int — URL query params는 alias 변환 안 됨

# ✅ 날짜: TIMESTAMPTZ (timezone=True 필수)
created_at = Column(DateTime(timezone=True), server_default=func.now())
updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

# ✅ 에러 응답
{ "error": "메시지", "code": "AUTH_001", "details": {} }

# ✅ 페이지네이션
{ "items": [], "total": N, "page": N, "limit": N }
# limit 상한: 보드/백로그=500, 단순목록=50
```

### 프론트엔드 (TypeScript/React)

```typescript
// ✅ 상태 관리 분리
// Zustand: 인증, 전역 UI 상태, store action에서 API 호출
// useState: 폼 입력, 모달 열림/닫힘
// useParams: 현재 리소스 ID (새로고침 시 유지)

// ✅ store action 패턴
fetchIssues: async (projectId) => {
  set({ isLoading: true })
  try {
    const data = await issueApi.getList(projectId)
    set({ issues: data.items })
  } catch (e) {
    set({ error: e.message })
  } finally {
    set({ isLoading: false })
  }
}

// ✅ CVA + index.style.ts 패턴 (JSX 직접 클래스 조합 금지)
// index.style.ts
export const button = cva('base-class', {
  variants: { variant: { primary: 'bg-[var(--color-primary)]' } }
})
// JSX
<button className={button({ variant: 'primary' })} />

// ✅ Tailwind v4 리셋 — @layer 안에 작성
@layer base {
  * { margin: 0; box-sizing: border-box; }
}
// ❌ @layer 밖 리셋 — mx-auto 등 유틸리티 무력화됨

// ✅ 숫자 입력 (CJK IME 호환)
<input type="text" inputMode="numeric" />
// ❌ type="number" — 한글 IME 충돌
```

### Shared Lessons (반복 금지 패턴)

과거 프로젝트에서 실제로 발생한 실수 모음. 모든 에이전트가 참조한다 (`backend/docs/shared-lessons.md`).

| 번호 | 문제 | 규칙 |
|------|------|------|
| LESSON-001 | Query params camelCase 전달 | FastAPI Query params는 snake_case만 |
| LESSON-002 | limit 상한 100 기본값 | 백로그/보드는 500, 단순목록은 50 |
| LESSON-003 | updated_at 자동 갱신 누락 | `onupdate=func.now()` 필수 |
| LESSON-004 | timezone-naive TIMESTAMP | `DateTime(timezone=True)` 강제 |
| LESSON-005 | 리소스 ID를 store에만 저장 | `useParams()`가 source of truth |
| LESSON-006 | `input type="number"` CJK 충돌 | `type="text" inputMode="numeric"` |
| LESSON-011 | Tailwind 리셋을 @layer 밖에 | `@layer base {}` 안에 작성 |
| LESSON-015 | RN 비동기 루프 동시 진입 | 모듈 레벨 boolean 플래그로 재진입 방지 |
| LESSON-016 | await 후 stale reference | await 후 store 상태 재확인 필수 |
| LESSON-017 | float 임계값 비교 불일치 | 정수 변환 후 비교 |

새 실수를 발견하면 `backend/docs/shared-lessons.md`에 추가하면 다음 프로젝트부터 자동으로 적용된다.

---

## gstack 없이 사용할 때

HarnessAI 단독으로 완전히 동작한다.

```
사용자가 요구사항 텍스트 작성
    ↓
pipeline_runner 실행
    ↓
Architect + Designer → skeleton 초안 자동 생성
    ↓
[GATE] 사람이 skeleton 검토 → y/n 입력
    ↓
Orchestrator → 태스크 목록 생성
    ↓
[GATE] 사람이 태스크 목록 검토 → y/n 입력
    ↓
Backend Coder + Frontend Coder 순차 구현
    ↓
Reviewer 코드 리뷰 (골든 원칙 + grep 검사)
    ↓
QA 통합 검증 (API 계약 + 상태흐름 + 타입 대조)
    ↓
완료
```

각 게이트에서 사람이 직접 skeleton/태스크를 읽고 판단한다.

---

## gstack과 함께 사용할 때

[gstack](https://github.com/garrynsk/gstack)은 Claude Code용 AI 보조 스킬 모음이다.
각 게이트 전후에 스킬을 실행해 검토 품질을 높인다. 최종 결정은 여전히 사람이 한다.

### 강화된 플로우

```
/office-hours             ← 요구사항 분석 먼저
    ↓
HarnessAI: DESIGNING
    ↓
/plan-eng-review          ← skeleton 엔지니어링 리뷰
/plan-ceo-review          ← 스코프 / 비즈니스 전략 리뷰
    ↓
[GATE 1] 더 많은 정보로 승인 판단
    ↓
HarnessAI: TASK_BREAKDOWN
    ↓
[GATE 2] 태스크 목록 검토
    ↓
HarnessAI: IMPLEMENTING
    ↓
/my-review                ← 보안 + LESSON 패턴 자동 탐지
/review                   ← 구조적 이슈 심층 리뷰
    ↓
HarnessAI: VERIFYING (Reviewer + QA)
    ↓
/ship                     ← PR 자동 생성
/retro                    ← 회고 기록
```

### gstack 스킬 상세

#### `/office-hours` — 요구사항 분석

HarnessAI를 시작하기 전에 실행. GATE 0를 사람 대신 AI가 먼저 분석한다.

- **핵심 사용자 가치**: 이 제품이 없으면 사용자가 어떻게 해결하는가? 만들 가치가 있는가?
- **MVP 범위 검증**: Phase 1만으로 핵심 흐름이 완성되는가? 범위가 너무 넓지 않은가?
- **기술적 리스크**: 구현 불가능하거나 과도하게 복잡한 요구사항이 있는가?
- **누락 요구사항**: 없으면 시스템이 불완전해지는 항목이 빠졌는가?

#### `/plan-eng-review` — 엔지니어링 리뷰

GATE 1에서 skeleton을 검토할 때 실행.

- **아키텍처 결정**: DB/API 설계가 요구사항을 충족하는가? 빠진 테이블/엔드포인트가 있는가?
- **기술 스택 적합성**: 선택된 기술이 요구사항 규모에 맞는가?
- **데이터 흐름**: API ↔ DB ↔ 프론트엔드 흐름이 일관성 있는가?
- **엣지케이스**: 인증, 에러 처리, 동시성 문제가 고려됐는가?

#### `/my-review` — 보안 + LESSON 패턴 검사

IMPLEMENTING 완료 후, `/review` 전에 실행. 코드를 자동으로 스캔한다.

보안 훅 14개:
- 하드코딩 시크릿 (API 키, 패스워드, 토큰)
- HTTP 500 응답에 내부 에러 상세 노출
- Path traversal 취약점 (파일명 sanitize 누락)
- `asyncio.create_task()` 참조 미보존 (GC 취소 위험)
- 에이전트 프롬프트에 사용자 입력 무방비 삽입
- `eval()` 사용, `dangerouslySetInnerHTML` (XSS)
- 빈 `except: pass` 블록, CLI 인자에 시크릿 전달
- Deep link 파라미터 검증 없는 네비게이션
- Electron `nodeIntegration: true` / `contextIsolation: false`
- Route Handler / Server Action 인증 누락
- React Native 소스코드 하드코딩 시크릿

LESSON 패턴 자동 탐지: LESSON-001~007

#### `/review` — 심층 구조 리뷰

`/my-review` 통과 후 실행. `/my-review`가 안 잡는 영역을 담당한다.

- **SQL & 데이터 안전**: SQL injection, N+1 쿼리
- **레이스 컨디션**: check-then-set 패턴, 비원자적 상태 전이
- **Enum/값 완전성**: 새 enum 값 추가 시 모든 소비처 추적
- **성능/번들**: 무거운 패키지, 이미지 lazy loading 누락

#### `/ship` — PR 생성

커밋 히스토리 + diff 분석 후 PR 제목/설명 자동 작성.

#### `/retro` — 회고

반복된 실수를 shared-lessons에 추가해 다음 프로젝트에 자동 반영.

### 단계별 비교

| Phase | gstack 없을 때 | gstack 있을 때 |
|-------|--------------|--------------|
| 요구사항 | 사람이 직접 판단 | `/office-hours` — 가치/MVP/리스크 구조화 분석 |
| skeleton 리뷰 | 사람이 직접 읽음 | `/plan-eng-review` — DB 정규화, 누락 엔드포인트 자동 탐지 |
| 전략 검토 | 없음 | `/plan-ceo-review` — 스코프/비즈니스 관점 |
| 코드 리뷰 1차 | Reviewer만 | `/my-review` — 보안 14항목 + LESSON 패턴 자동 스캔 |
| 코드 리뷰 2차 | 없음 | `/review` — SQL injection, 레이스 컨디션, 동시성 |
| 배포 | 수동 | `/ship` — PR 자동 생성 |
| 학습 | 없음 | `/retro` — 반복 실수 기록 |

---

## Tech Stack

- **언어**: Python 3.12
- **서버**: FastAPI + WebSocket (포트 3002)
- **패키지 매니저**: uv
- **에이전트 실행**: Claude CLI subprocess / Gemini API / 로컬 모델 (OpenAI 호환)
- **상태 저장**: JSON 파일 (`.orchestra/`) — DB 없음
- **테스트**: pytest (236개)

---

## Quick Start

> 상세 가이드: [SETUP.md](SETUP.md)

```bash
git clone https://github.com/reasonableplan/harnessai.git
cd harnessai/backend

uv sync
cp .env.example .env   # LLM 설정 편집

# 서버 실행
uv run python -m src.main

# 인터랙티브 파이프라인 (별도 터미널)
uv run python -m src.orchestrator.pipeline_runner
```

---

## Project Structure

```
backend/
  agents.yaml                    — 에이전트별 provider/model/timeout 설정 + max_concurrent
  agents/
    architect/CLAUDE.md          — DB/API/인증/상태흐름 설계 규칙  ← 수정 가능
    designer/CLAUDE.md           — UI/UX/컴포넌트/상태관리 설계 규칙  ← 수정 가능
    orchestrator/CLAUDE.md       — Phase 분해 / 태스크 분배 규칙  ← 수정 가능
    backend_coder/CLAUDE.md      — Python/FastAPI 코딩 컨벤션 + 허용 라이브러리  ← 수정 가능
    frontend_coder/CLAUDE.md     — React/TS 코딩 컨벤션 + CVA 패턴 + 허용 라이브러리  ← 수정 가능
    reviewer/CLAUDE.md           — 골든 원칙 7개 + grep 체크 + Phase 리뷰 기준  ← 수정 가능
    qa/CLAUDE.md                 — 통합 테스트 검증 기준  ← 수정 가능
  docs/
    skeleton_template.md         — 프로젝트 계약서 템플릿 (19개 섹션)  ← 수정 가능
    shared-lessons.md            — 과거 실수 패턴 (LESSON-001~017)  ← 수정 가능
    skeleton.md                  — 실행 시 생성 (Architect+Designer 출력)
  src/
    main.py                      — FastAPI 서버 진입점 (포트 3002)
    dashboard/
      server.py                  — FastAPI 앱, WebSocket 핸들러, 미들웨어
      event_mapper.py            — Orchestra 이벤트 → WebSocket 브로드캐스트
      routes/                    — REST API (command, agents, tasks, hooks, stats)
      websocket_manager.py       — WebSocket 연결 관리
    orchestrator/
      orchestrate.py             — Orchestra 클래스 (전체 워크플로우)
      pipeline_runner.py         — 인터랙티브 CLI 러너 (게이트 승인)
      runner.py                  — AgentRunner (타임아웃/재시도/에스컬레이션)
      security_hooks.py          — 보안 훅 6개
      state.py                   — StateManager (.orchestra/ JSON 저장)
      output_parser.py           — LLM 출력 파싱 (phases, review, qa, tasks)
      config.py                  — agents.yaml 파싱/검증 (Pydantic)
      pipeline.py                — ValidationPipeline (lint/type/test)
      context.py                 — skeleton 섹션 매핑 + 컨텍스트 주입
      phase.py                   — Phase 상태 머신
      providers/
        base.py                  — BaseProvider 추상 인터페이스
        claude_cli.py            — Claude CLI subprocess
        gemini_cli.py            — Gemini CLI subprocess
        gemini_api.py            — Gemini REST API
  tests/
    orchestrator/                — 236개 테스트
    dashboard/                   — EventMapper 테스트
```

---

## Development

```bash
cd backend

# 테스트
uv run pytest tests/ --rootdir=.

# 린트
uv run ruff check src/

# 서버 실행
uv run python -m src.main
```

---

## Documentation

| 문서 | 설명 |
|------|------|
| [SETUP.md](SETUP.md) | 처음부터 끝까지 설치/실행 가이드 |
| [TODOS.md](TODOS.md) | 향후 개선 항목 |

## License

MIT
