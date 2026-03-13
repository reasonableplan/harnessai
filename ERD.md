# Entity Relationship Diagram

## 데이터베이스 ERD

```mermaid
erDiagram
    agents ||--o{ tasks : "assigned to"
    agents ||--o| agent_config : "has config"
    agents ||--o{ agents : "parent-child"
    agents ||--o{ artifacts : "created by"
    agents ||--o{ messages : "sent by"

    epics ||--o{ tasks : "contains"

    tasks ||--o{ artifacts : "produces"
    tasks ||--o{ messages : "related to"

    agents {
        text id PK "에이전트 고유 ID (e.g. director, backend-1)"
        text domain "NOT NULL — 도메인 (director, git, backend, frontend, docs)"
        integer level "NOT NULL DEFAULT 2 — 계층 (0=Director, 1=Manager, 2=Worker)"
        text status "NOT NULL DEFAULT 'idle' — idle | busy | paused | error"
        text parent_id FK "NULLABLE — 상위 에이전트 (self-reference)"
        timestamp created_at "NOT NULL DEFAULT now()"
        timestamp last_heartbeat "NULLABLE — 마지막 heartbeat"
    }

    epics {
        text id PK "에픽 ID (e.g. epic-shopping-mall)"
        text title "NOT NULL — 에픽 제목"
        text description "NULLABLE — 에픽 설명"
        text status "NOT NULL DEFAULT 'draft' — draft | active | completed | cancelled"
        integer github_milestone_number "NULLABLE — GitHub Milestone 번호"
        real progress "NOT NULL DEFAULT 0.0 — 진행률 (0.0 ~ 1.0)"
        timestamp created_at "NOT NULL DEFAULT now()"
        timestamp completed_at "NULLABLE — 완료 시각"
    }

    tasks {
        text id PK "태스크 ID"
        text epic_id FK "NULLABLE — 소속 에픽"
        text title "NOT NULL — 태스크 제목"
        text description "NULLABLE — 태스크 설명"
        text assigned_agent FK "NULLABLE — 담당 에이전트"
        text status "NOT NULL DEFAULT 'backlog'"
        integer github_issue_number "NULLABLE — GitHub Issue 번호"
        text board_column "NOT NULL DEFAULT 'Backlog'"
        integer priority "NOT NULL DEFAULT 3 — (1=최고, 5=최저)"
        text complexity "NULLABLE DEFAULT 'medium'"
        jsonb dependencies "DEFAULT [] — 의존 태스크 ID 배열"
        jsonb labels "DEFAULT [] — GitHub 라벨 배열"
        integer retry_count "NOT NULL DEFAULT 0"
        timestamp created_at "NOT NULL DEFAULT now()"
        timestamp started_at "NULLABLE"
        timestamp completed_at "NULLABLE"
        text review_note "NULLABLE — 리뷰 피드백"
    }

    messages {
        uuid id PK "DEFAULT random() — 메시지 UUID"
        text type "NOT NULL — 메시지 타입 (board.move, review.request 등)"
        text from_agent "NOT NULL — 발신 에이전트"
        text to_agent "NULLABLE — 수신 에이전트 (null=broadcast)"
        jsonb payload "NOT NULL DEFAULT {} — 메시지 페이로드"
        text trace_id "NULLABLE — 추적 ID (Epic 단위)"
        timestamp created_at "NOT NULL DEFAULT now()"
        timestamp acked_at "NULLABLE — 수신 확인 시각"
    }

    artifacts {
        uuid id PK "DEFAULT random() — 산출물 UUID"
        text task_id FK "NOT NULL — 소속 태스크"
        text file_path "NOT NULL — 파일 경로"
        text content_hash "NOT NULL — 내용 해시 (SHA-256)"
        text created_by FK "NOT NULL — 생성 에이전트"
        timestamp created_at "NOT NULL DEFAULT now()"
    }

    agent_config {
        text agent_id PK_FK "에이전트 ID → agents.id"
        text claude_model "NOT NULL DEFAULT 'claude-sonnet-4-20250514'"
        integer max_tokens "NOT NULL DEFAULT 4096"
        real temperature "NOT NULL DEFAULT 0.7"
        integer token_budget "NOT NULL DEFAULT 10000000"
        integer task_timeout_ms "NOT NULL DEFAULT 300000 (5분)"
        integer poll_interval_ms "NOT NULL DEFAULT 10000 (10초)"
        timestamp updated_at "NOT NULL DEFAULT now()"
    }

    hooks {
        text id PK "훅 ID (e.g. log-task-complete)"
        text event "NOT NULL — 이벤트 (hook.task.completed 등)"
        text name "NOT NULL — 훅 이름"
        text description "NULLABLE — 설명"
        boolean enabled "NOT NULL DEFAULT true"
        timestamp created_at "NOT NULL DEFAULT now()"
    }
```

## 테이블 관계 요약

| 관계 | 카디널리티 | 설명 |
|------|-----------|------|
| `agents` → `agents` | self 1:N | Director(L0) → Worker(L2) 계층 |
| `agents` → `agent_config` | 1:0..1 | 에이전트별 동적 설정 (없으면 기본값) |
| `epics` → `tasks` | 1:N | 에픽은 여러 태스크 포함 |
| `agents` → `tasks` | 1:N | 에이전트에 태스크 할당 |
| `tasks` → `artifacts` | 1:N | 태스크 실행 결과 파일들 |
| `agents` → `artifacts` | 1:N | 어떤 에이전트가 생성했는지 |
| `agents` → `messages` | 1:N | 에이전트가 발신한 메시지 |
| `hooks` | standalone | MessageBus 이벤트 훅 (agent와 직접 FK 없음) |

## 인덱스 전략

| 테이블 | 인덱스 | 용도 |
|--------|--------|------|
| `tasks` | `idx_tasks_board_column` | BoardWatcher 동기화 시 컬럼별 조회 |
| `tasks` | `idx_tasks_assigned_agent` | `getReadyTasksForAgent()` — 에이전트별 태스크 |
| `tasks` | `idx_tasks_epic_id` | 에픽별 태스크 목록, 진행률 계산 |
| `tasks` | `idx_tasks_status` | `claimTask()` WHERE status='ready' |
| `tasks` | `idx_tasks_github_issue` | BoardWatcher — issue번호로 task 매핑 |
| `messages` | `idx_messages_type` | 메시지 타입별 조회 |
| `messages` | `idx_messages_trace_id` | Epic 단위 추적 |

## Board ↔ DB 매핑

```
GitHub Board Column    DB status        DB boardColumn
─────────────────────────────────────────────────────
Backlog            →   backlog          Backlog
Ready              →   ready            Ready
In Progress        →   in-progress      In Progress
Review             →   review           Review
Failed             →   failed           Failed
Done               →   done             Done
```

> `boardColumn`은 GitHub Board의 원본 컬럼명을 그대로 저장하고,
> `status`는 정규화된 소문자 kebab-case 값을 사용한다.
> BoardWatcher가 `COLUMN_TO_STATUS` 맵으로 변환한다.
