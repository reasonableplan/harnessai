# Agent Architecture — 에이전트별 로직 상세 문서

## 개요

5개 에이전트가 협력하여 소프트웨어를 자율 개발하는 멀티 에이전트 시스템.

```
사용자
  │
  ▼
Director (L0) ──── 계획·상담·리뷰
  │
  ├── Git Agent (L2) ──── 저장소·브랜치·PR
  ├── Backend Agent (L2) ──── API·DB·비즈니스 로직
  ├── Frontend Agent (L2) ──── UI·컴포넌트·상태관리
  └── Docs Agent (L2) ──── 문서·가이드
```

---

## 1. Director Agent (`director_agent.py`)

### 역할
- 사용자와 대화하며 프로젝트 아키텍처 설계
- Worker 에이전트들과 상담하여 태스크 보강
- GitHub Project Board에 3계층 이슈 생성 (Epic → Story → Sub-task)
- Worker 작업 결과 리뷰 (approve/reject)

### 상태 머신 (PlanStage)

```
GATHERING → STRUCTURING → CONFIRMING → COMMITTED → EXECUTING
   │              │              │           │           │
   │              │              │           │           └── 에이전트 작업 중
   │              │              │           └── 이슈 생성 완료, "시작해" 대기
   │              │              └── 사용자 최종 확인
   │              └── 태스크 분해 + Worker 상담
   └── 스켈레톤(ProjectContext) 채우기
```

### 핵심 메서드

| 메서드 | 역할 |
|--------|------|
| `handle_user_input()` | 사용자 메시지 수신 → stage별 라우팅 |
| `_handle_gathering()` | 스켈레톤 채우기 (topic, purpose, tech_stack 등) |
| `_generate_task_breakdown()` | LLM으로 초기 태스크 분해 (3계층) |
| `_consult_workers()` | 4개 Worker 에이전트와 순차 상담 → 태스크 보강 |
| `_handle_confirming()` | 사용자 최종 확인 (commit/revise) |
| `_commit_plan()` | GitHub에 Epic+Story+Sub-task 이슈 생성 + 보드 배치 |
| `_start_execution()` | 의존성 없는 태스크를 Ready로 전환 |
| `_handle_review()` | Worker 완료 태스크 리뷰 (Done/재작업) |
| `_persist_plan()` | 현재 plan 상태를 DB에 저장 |
| `restore_plan_from_db()` | 서버 시작 시 마지막 plan 복원 |

### 스켈레톤 (ProjectContext)

Director가 GATHERING에서 대화로 채우는 구조체:

```python
class ProjectContext:
    topic: str          # 무엇을 만드는가
    purpose: str        # 왜 만드는가
    target_users: str   # 누가 쓰는가
    scope: str          # MVP / 프로덕션
    tech_stack: TechStack  # frontend, backend, database, infra
    existing_system: str   # 기존 시스템 유무
    constraints: list[str] # 제약 조건
    non_goals: list[str]   # 명시적 제외 항목
```

### Worker 상담 흐름

```
Director: 초기 태스크 분해 (LLM 1회)
  │
  ├── DevOps Agent에게: "인프라 태스크 1개 검토해줘"
  │   ← "Docker 설정 분리 권장, 개발 스크립트 추가"
  │
  ├── Backend Agent에게: "API 태스크 20개 검토해줘"
  │   ← "횡단 관심사 누락, DB 세션 관리 태스크 추가"
  │
  ├── Frontend Agent에게: "UI 태스크 10개 검토해줘"
  │   ← "상태 관리 전략 태스크 추가, 드래그앤드롭 분리"
  │
  └── Docs Agent에게: "문서 태스크 2개 검토해줘"
      ← "API 문서 범위 축소, 다이어그램 별도 분리"
  │
  ▼
  통합된 최종 태스크 → 사용자에게 제시
```

### 3계층 이슈 생성 (_commit_plan)

```
Phase 0: 라벨 확보 (epic, story, backend, frontend, infra, docs)
Phase 1: Sub-task 이슈 생성 (개별 작업 단위)
Phase 2: Story 이슈 생성 (기능 그룹, Sub-task 참조)
Phase 3: Epic 이슈 생성 (프로젝트 전체, Story 참조)
Phase 4: 서브이슈 연결 (Story→Epic, Sub-task→Story)
Phase 5: 프로젝트 보드에 전체 추가 (Backlog)
Phase 6: DB 저장 (Epic + Tasks)
Phase 7: COMMITTED 상태 전환 + plan DB persist
```

### Plan 영속성

- 모든 stage 변경 시 `_persist_plan()` → DB에 자동 저장
- 서버 재시작 시 `restore_plan_from_db()` → 마지막 plan 복원
- 세션 초기화 시 `_reset_session()` → DB에서 plan 삭제

---

## 2. BaseAgent (공통 추상 클래스, `base_agent.py`)

### 역할
- 모든 Worker 에이전트의 부모 클래스
- 폴링 루프, 태스크 선점, 상태 관리 제공

### 폴링 루프 (`_poll_loop`)

```
while polling:
  if status == IDLE or ERROR:
    task = _find_next_task()     # DB에서 ready 태스크 조회
    if task:
      claim_task()               # 원자적 선점 (WHERE status='ready')
      move_to_board("In Progress")  # Board-first
      result = execute_task()    # 서브클래스 구현
      on_task_complete()         # Review/Failed로 전환
    sleep(interval + backoff)
```

### 태스크 선점 (Optimistic Locking)

```sql
UPDATE tasks SET status='in-progress', started_at=NOW()
WHERE id=:id AND status='ready'
-- rowCount == 1이면 성공, 0이면 다른 에이전트가 선점
```

### 상태 전이

```
IDLE → BUSY (태스크 실행 중) → IDLE (완료)
  └→ ERROR (실패) → IDLE (복구, 다음 폴링)
```

---

## 3. Git Agent (`git_agent.py`)

### 역할
- Git 저장소 초기화, 브랜치 생성
- 커밋, PR 생성/관리
- 프로젝트 구조 스캐폴딩

### 실행 흐름
1. 태스크 수신 (e.g., "모노레포 초기화")
2. LLM에 코드 생성 요청
3. `git_service`로 브랜치 생성 → 파일 생성 → 커밋 → PR

---

## 4. Backend Agent (`backend_agent.py`)

### 역할
- FastAPI 엔드포인트, Pydantic 스키마 생성
- SQLAlchemy 모델, Alembic 마이그레이션
- 비즈니스 로직, 서비스 계층 코드

### 실행 흐름
1. 태스크 수신 (e.g., "Task CRUD API")
2. 코드베이스 RAG 검색 (기존 코드 참조)
3. LLM에 코드 생성 요청 (시스템 프롬프트 + 컨텍스트)
4. 생성된 파일을 워크스페이스에 저장
5. 결과 보고 (artifacts: 파일 경로, diff)

---

## 5. Frontend Agent (`frontend_agent.py`)

### 역할
- React 컴포넌트, 페이지 생성
- shadcn/ui 기반 UI 구현
- API 연동 (TanStack Query hooks)
- 상태 관리 (Zustand store)

### 실행 흐름
1. 태스크 수신 (e.g., "칸반보드 UI")
2. 기존 컴포넌트 구조 RAG 검색
3. LLM에 코드 생성 (React + TypeScript)
4. 컴포넌트/페이지 파일 생성
5. 결과 보고

---

## 6. Docs Agent (`docs_agent.py`)

### 역할
- README, API 문서 생성
- 아키텍처 다이어그램 (Mermaid)
- 에이전트 통합 가이드

### 실행 흐름
1. 태스크 수신 (e.g., "API 문서 작성")
2. 기존 코드/라우트 분석
3. LLM에 문서 생성 요청
4. Markdown 파일 생성

---

## 공통 인프라

### GitService (`git_service.py`)

GitHub API 래퍼. 모든 에이전트가 공유.

| 메서드 | 역할 |
|--------|------|
| `create_issue()` | GitHub Issue 생성 (REST API) |
| `add_issue_to_project()` | Project V2에 이슈 추가 + 상태 설정 (GraphQL) |
| `link_sub_issue()` | 부모-자식 서브이슈 연결 (GraphQL) |
| `move_issue_to_column()` | Board 컬럼 이동 (GraphQL) |
| `ensure_label()` | 라벨 생성 (없으면 생성, 있으면 무시) |
| `create_branch()` / `create_pr()` | Git 브랜치/PR 관리 |

### StateStore (`state_store.py`)

PostgreSQL DB 래퍼. CRUD + 원자적 상태 전이.

| 카테고리 | 주요 메서드 |
|----------|------------|
| Agent | `register_agent`, `update_heartbeat`, `claim_task` |
| Task | `create_task`, `update_task`, `get_ready_tasks_for_agent` |
| Epic | `create_epic`, `update_epic` |
| Plan | `save_plan`, `get_latest_plan`, `delete_plan` |

### OrphanCleaner (`orphan_cleaner.py`)

백그라운드 태스크. 30분 이상 in-progress인 태스크를 ready로 롤백.
Board-first: GitHub Board → DB 순서로 복구.

### MessageBus (`message_bus.py`)

에이전트 간 비동기 메시지 전달. Pub/Sub 패턴.
메시지 타입: `agent.status`, `review.request`, `director.message`, `director.plan` 등.

---

## 에이전트 기대사항 커스터마이징

`prompts/expectations/` 디렉토리에 MD 파일로 각 에이전트에 대한 기대사항 정의:

```
prompts/expectations/
  agent-backend.md    ← "RESTful 원칙", "Pydantic 스키마 필수" 등
  agent-frontend.md   ← "shadcn/ui 우선", "TypeScript strict" 등
  agent-git.md        ← "Conventional Commits", "Docker Compose" 등
  agent-docs.md       ← "Quick Start 포함", "curl 예제" 등
```

Director가 Worker 상담 시 이 파일을 자동 로드하여 프롬프트에 반영.

---

## 태스크 상태 흐름

```
Backlog ──→ Ready ──→ In Progress ──→ Review ──→ Done
   │          │           │              │
   └── Failed ←───────────┘              └── Ready (거절 시 재작업)
                     │
                     └── Ready (OrphanCleaner: 30분 timeout)
```

## 데이터 흐름

```
사용자 요청
  → Director GATHERING (스켈레톤 채우기)
  → Director STRUCTURING (LLM 분해 + Worker 상담)
  → 사용자 CONFIRMING (승인)
  → Director COMMITTED (GitHub 이슈 생성)
  → 사용자 "시작해" EXECUTING (Ready 전환)
  → Worker 폴링 → claim → execute → 결과 보고
  → Director 리뷰 → Done / 재작업
  → 의존 태스크 해제 → 다음 Worker 작업
  → Epic 완료
```
