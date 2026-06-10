---
name: ha-plan
description: |
  HarnessAI v2 — 채워진 skeleton 으로부터 태스크 분해 (Orchestrator 역할).
  의존성 그래프 + 컴포넌트별 구현 태스크 → tasks.md 생성.
  Use when: /ha-design 완료 후, "태스크 분해", "/ha-plan"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - AskUserQuestion
---

## 역할

채워진 skeleton 을 읽어 구현 태스크 목록 (`tasks.md`) 을 생성. 또한 skeleton 의 `tasks` 섹션도 동시 갱신.

**입력**: `docs/skeleton.md` (designed)
**출력**: `docs/tasks.md` + skeleton.md 의 `tasks` 섹션
**다음**: `/ha-build T-XXX`

## 실행 순서

### 1. 사전 조건 + 컨텍스트
```bash
python ~/.claude/skills/ha-plan/run.py prepare
```
JSON 출력: profile components, skeleton 섹션 채워짐 여부, orchestrator 프롬프트 경로.

추가 출력 필드:
- `consistency_violations`: list — 각 항목 `{section_id, trigger_expression, missing_atom, expected_providers}` 형식.
  - 빈 list = 이상 없음.
  - 비어있지 않으면 plan 의 included 섹션이 활성 profile 셋과 정합하지 않음 (stale plan 상태).

### 1.5 Plan consistency 검토 (cross-check)

prepare 출력의 `consistency_violations` 가 있으면:

- 각 violation: `{section_id, trigger_expression, missing_atom, expected_providers}` 형식
- 의미: plan 의 included 섹션이 활성 profile 셋과 정합하지 않음 — 본질적으로 stale plan 상태
- 처리:
  1. AskUserQuestion 으로 사용자에게 보여줌 (해당 섹션들이 backend 가정인 경우 paired profile 추가 권고)
  2. 사용자 선택:
     - 그대로 진행 — 의도적 mismatch (외부 backend / BaaS 가정). task 분해에 반영 (해당 capability 작업은 외부 책임 명시)
     - 취소 → `/ha-redesign` 으로 plan 재정렬 후 다시 ha-plan
     - 수동 정정 → `/ha-redesign` 사용 안내

본 검증은 advisory — 차단 안 함. 다만 violations 가 있으면 task 분해 시 그 영향을 §19 구현 노트의 "결정 로그" 에 기록 권고.

**가드레일**: consistency_violations 를 자동으로 무시하지 말 것 — 사용자에게 반드시 보여주거나 §19 에 기록.

### 2. Orchestrator 프롬프트 + skeleton 로드
- `<HARNESS_AI_HOME>/backend/agents/orchestrator/CLAUDE.md` 읽기
- 채워진 `docs/skeleton.md` 전체 읽기
- 활성 프로파일들의 `components` (각 component 가 한 태스크 후보)

### 3. 태스크 분해 (Orchestrator 역할)

**Phase 분리 우선** (orchestrator/CLAUDE.md 의 Phase 1=MVP / Phase 2+=확장 규칙):
- Phase 1: 핵심 사용자 흐름이 동작하는 최소 기능
- Phase 2+: 부가 기능

**각 Phase 내 태스크 순서**:
1. persistence 모델 (해당 시)
2. interface.* 구현 (HTTP/CLI/IPC/SDK)
3. core.logic
4. view.* (해당 시)
5. integrations (해당 시)

**태스크 단위**: 1 PR = 1 태스크. 너무 크면 분리, 너무 작으면 병합.

**테스트 태스크 동반** (필수 — `/ha-review` 의 분포 체크가 BLOCK/WARN 발동):
- **구현 태스크 1개 = 대응 테스트 태스크 최소 1개** (또는 같은 태스크 안에 테스트 포함)
- **I/O 경계 컴포넌트 (LLM 호출, 외부 API, DB, 파일 시스템) 는 테스트 최소 2개 이상** — 성공 경로 + 실패/재시도 경로
- `core.logic` 순수 함수는 unit test 우선, `io/` 는 integration test
- 프론트엔드도 동일: `view.*` 는 render + interaction 테스트, `state.flow` 는 store action 테스트
- 테스트 태스크 ID 는 구현 태스크와 짝 (예: `T-003 모델 구현` ↔ `T-004 모델 테스트`), 또는 "implement + tests" 같은 이름으로 통합

**의존성** (`depends_on`):
- DB → API → 프론트엔드 (순서 필수)
- core.logic 은 다른 컴포넌트와 병렬 가능
- 테스트 태스크는 구현 태스크에 `depends_on`

**출력 포맷** (orchestrator/CLAUDE.md 와 동일 — 두 부분 모두 필수):

**1) Phase 테이블** (파서 고정, 정확히 5 컬럼):
```markdown
### Phase 1 — MVP
| ID | 에이전트 | 의존성 | 설명 | 상태 |
|----|---------|--------|------|------|
| T-001 | backend_coder | - | <component_id>: <설명> | 대기 |
| T-002 | backend_coder | T-001 | ... | 대기 |
```

**2) 태스크별 구현 스펙 블록** (모든 태스크마다 필수 — Coder 자율 결정 방지):

```markdown
### T-001 — DB 모델 (users)

- **담당**: backend_coder
- **생성/수정 파일** (skeleton 에서 복사):
  - NEW `backend/src/app/models/user.py`
  - NEW `backend/tests/models/test_user.py`
- **skeleton 참조**: `persistence.users`
- **구현 세부** (Architect 가 skeleton 에 확정한 것 그대로):
  - `users`: id (PK), email (unique/index/not null), password_hash (not null), ...
  - FK: 없음
  - 인덱스: email (unique)
- **참조 파일** (기존 패턴 복제 대상): `guidelines/backend/structure.md`
- **완료 기준**: LESSON-021 toolchain (test + lint + type) 통과 + skeleton 과 컬럼/타입/제약 100% 일치
```

- 스펙 블록은 모든 Phase 테이블 **아래에 연속 배치**
- skeleton 에 필요한 정보가 없으면 태스크 분해 중단 → Architect/Designer 에게 에스컬레이션 (skeleton 보완 후 재개)
- 스펙 블록 없는 태스크는 미완성 산출물로 간주

### 4. tasks.md 작성 + skeleton 의 tasks 섹션 갱신
```bash
python ~/.claude/skills/ha-plan/run.py commit \
  --tasks-content "$(cat <<'EOF'
<태스크 분해 마크다운 본문>
EOF
)"
```
run.py 가:
- `docs/tasks.md` 작성
- `docs/skeleton.md` 의 `## N. 태스크 분해` 섹션을 같은 내용으로 동기화
- `current_step` "designed" → "planned"

### 5. 다음 단계 안내
```
✅ /ha-plan 완료
태스크 N개 / Phase M개
의존성 없는 즉시 시작 가능: T-XXX, T-YYY

다음:
  /ha-build T-XXX  — 단일 태스크 구현
  /ha-build --parallel T-XXX,T-YYY  — 병렬 (의존성 없을 때)
```

### 출력의 guideline_paths 도 읽으세요

`prepare` 출력 JSON 의 `profiles[].guideline_paths` 에 프로파일별 컨벤션 문서 경로가 포함됩니다.
**작업 시작 전 모두 Read 로 읽으세요.** 프로파일별 파일 목록 → `<HARNESS_AI_HOME>/skills/_ha_shared/GUIDELINES_NOTE.md` 참조.

**모바일 사용자**: 안 읽으면 LESSON-STYLE-001 / 보안 위반 / 컨벤션 drift 가능성. 시스템 프롬프트만으로는 부족합니다.

## 가드레일
- 태스크에 reviewer/qa 직접 배정 금지 (Phase 리뷰는 자동 처리)
- skeleton 에 정의된 모든 컴포넌트가 태스크로 커버되는지 확인
- 의존성 순환 금지
- skeleton 의 다른 섹션은 절대 수정 X (tasks 만)
- agent ↔ active context 매칭은 `commit` 시점 자동 검증. task description 의미 일치는 orchestrator 책임 (Step 2 한계).

## Agent 매핑 룰 (Step 2 추가)

각 task 의 agent 컬럼은 다음을 따라야 한다 — `ha-plan commit` 의 검증이 자동 실행:

1. **활성 컨텍스트** = `plan.profiles` 의 `provides_capabilities` union + 6축에서 derived capability 셋 (`active has_keys`).
2. **agent별 매칭 조건** (agents.yaml 의 `requires_capabilities`, `requires_profile_ids`):
   - `backend_coder`: active has_keys 에 `http_server` / `cli_entrypoint` / `sdk_surface` 중 하나
   - `frontend_coder`: active has_keys 에 `ui` 있고 mobile profile 없음 (웹 한정)
   - `mobile_coder_rn`/`flutter`/`android`/`ios`: 각 profile + `ui` + `navigation` capability
   - capability-agnostic (architect, designer, orchestrator, reviewer, qa): 컨텍스트 무관
3. **agent ↔ 활성 컨텍스트 1차 가드**: `ha-plan commit` 이 검증. 위반 시 차단.
4. **task description ↔ agent 의미 매핑은 별도** — 1차 가드를 통과해도 task 의 실제 작업 내용 (예: "auth API") 과 agent 책임 영역이 일치하는지는 orchestrator 가 직접 판단 (LLM 의미 추론). 본 자동 검증은 컨텍스트 정합만 보장.

검증 우회: 의도적 mismatch (예: paired profile 추가 예정) → `commit --allow-agent-mismatch`.

## tasks.md 표준 schema (Step 4-1)

`ha-plan commit` 이 자동 검증. 위반 시 차단 — `--allow-format-drift` 로 우회 가능.

### Task ID
- 형식: `T-NNN` (3자리 정수, 예: T-001, T-024, T-100)
- fractional (T-024.5), letter (T-A01), 다른 길이 (T-1, T-1000) 거부

### 표 컬럼 순서 (강제)
```
| ID | 에이전트 | 의존성 | 설명 | 상태 |
```
- 컬럼명은 한국어/영어 혼용 허용 (`agent`/`에이전트`, `depends`/`의존성`, `status`/`상태` 등)
- 컬럼 수 = 5, 순서 변경 시 거부

### 상태 값 (allow-list)
`대기` / `pending` / `진행중` / `in-progress` / `완료` / `done` / `completed` / `차단` / `blocked` / `needs_rebuild`

### 의존성
- 없음: `-`, `—`, `없음`, `(없음)`, `none`, 빈 셀
- 있음: 콤마 구분 task ID (예: `T-001` 또는 `T-001, T-002`)
- 자유 텍스트 (`T-001 완료 후`) 거부

### Phase 헤더 (선택)
- 형식: `### Phase N[+] — <name>` (예: `### Phase 1 — MVP`, `### Phase 2+ — 확장`)
- `—` (em dash) 없이 공백으로 이은 형식 거부 (예: `### Phase 2+ 태스크 스펙` → 거부)
- Phase 헤더가 없으면 단일 Phase 로 간주 (위반 아님)

## 트러블슈팅

- **Agent mismatch FAIL**: tasks.md 의 task 가 활성 컨텍스트와 정합하지 않은 agent 에 배정. 해결 — agent 변경 or `plan.profiles` 추가 (paired 모드) or `--allow-agent-mismatch` 로 우회.
- **Schema violation FAIL**: tasks.md 의 ID/컬럼/상태/의존성/Phase 헤더 형식 위반. 해결 — 위반 항목 수정 or `--allow-format-drift` 로 우회 (경고로 기록 후 진행).

## 모바일 프로젝트 사용 예시 (Flutter)

**3단계 — `/ha-plan` 에서 태스크 분해**:

- `/ha-design` 완료 후 채워진 `skeleton.md` 기반으로 태스크 분해
- Flutter 프로젝트 전형적 태스크 구조:
  - `T-001 mobile_coder_flutter`: 프로젝트 초기화 + pubspec.yaml 의존성
  - `T-002 mobile_coder_flutter`: go_router 네비게이션 설정 (depends_on: T-001)
  - `T-003 mobile_coder_flutter`: Riverpod 상태 관리 레이어 (depends_on: T-001)
  - `T-004 mobile_coder_flutter`: 주요 화면 구현 (depends_on: T-002, T-003)
  - `T-005 mobile_coder_flutter`: drift DB + flutter_secure_storage (depends_on: T-001)

**react-native-expo 의 경우**:
- 에이전트: `mobile_coder_rn`
- android + iOS 동시 지원 태스크는 단일 T-NNN 으로 처리 (Expo 가 추상화)

**android-kotlin / ios-swift 의 경우**:
- 에이전트: `mobile_coder_android` / `mobile_coder_ios`
- 플랫폼별 빌드 설정 태스크 별도 분리 권장
