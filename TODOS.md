# TODOS — HarnessAI

향후 개선 항목. 현재 스코프 밖이지만 기록해둠.

---

## 아키텍처

- [ ] **Architect ↔ Designer 중재 루프** (최대 3회)
  - `design()` 현재 1회 순차 실행 (Architect → Designer)
  - Designer가 "이 API 구조로는 이 UI를 못 만든다"고 판단해도 Architect에 피드백 불가
  - `agents/architect/CLAUDE.md`에 3회 중재 규칙 있지만 코드에 없음
  - **비용 주의**: 구현 시 LLM 호출 최대 6회 (현재 2회)

- [ ] **의존성 기반 병렬 실행** (DAG 스케줄러)
  - `TaskItem.depends_on`이 이미 파싱되어 있음
  - `AgentRunner.run_many()`가 이미 구현되어 있음
  - `run_phases()` 에서 위상 정렬(topological sort) 후 독립 태스크 병렬 실행
  - 예: `[T-001(backend), T-002(backend), T-003(frontend)]`에서 T-002, T-003이 T-001에만 의존 → T-001 완료 후 T-002+T-003 동시 실행

## 에이전트

- [x] **self-review 구조 개선** ✅ 완료
  - GATE 1 엔지니어링 리뷰를 architect(self-review) → reviewer 에이전트로 교체
  - 파일: `backend/src/orchestrator/pipeline_runner.py`

- [x] **QA 에이전트 파이프라인 연결** ✅ 완료
  - Reviewer APPROVE 이후 `qa_phase()` 자동 실행
  - API 계약·상태흐름·타입 대조, health score 0-10 산출
  - health score < 7이면 Phase 재시도
  - 파일: `backend/src/orchestrator/orchestrate.py`, `output_parser.py`

- [ ] **TaskItem.ref_files 필드**
  - 태스크별 참조 파일 목록을 프롬프트에 주입하는 기능
  - 파일: `backend/src/orchestrator/orchestrate.py`

## 동시성

- [ ] **`plan.*` WS 핸들러와 `_impl_lock` 미연동**
  - `implement_with_retry()`는 `_impl_lock`으로 직렬화됨
  - 그러나 `server.py`의 `plan.approve/commit/start` 핸들러는 `pm.transition()`을 lock 없이 직접 호출
  - implement 진행 중에 `plan.commit` WS 메시지 도착 → Phase 상태 충돌 가능
  - 파일: `backend/src/dashboard/server.py:254-280`
  - **해결책**: Orchestra에 별도 `phase_transition_lock`을 두거나, plan.* 핸들러가 `_impl_lock` 보유 여부를 확인 후 거부

## 성능

- [ ] **LLM 응답 캐시**
  - 동일 프롬프트 재시도 시 이전 결과 재사용
  - `implement_with_retry()` 재시도 비용 절감
  - **주의**: 캐시 무효화 전략 필요 (프롬프트 해시 기반)

- [x] **max_concurrent 설정화** ✅ 완료
  - `agents.yaml`의 `max_concurrent` 필드로 이동
  - 기본값 2, 환경에 따라 조정 가능

## 기능 확장

- [ ] **대시보드 ↔ 오케스트레이터 실시간 연결** (EventMapper 주입)
- [ ] **GitHub 연동** (branch/commit/PR 자동 생성)
- [ ] **Pipeline 재개** (state.json 기반 resume)
- [ ] **--dry-run 모드** (DryRunProvider — LLM 호출 없이 파이프라인 구조 검증)
- [ ] **Claude API (HTTP) provider** — CLI subprocess 없이 직접 REST API 호출, 토큰 비용 추적
