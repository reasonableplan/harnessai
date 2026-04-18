# TODOS — HarnessAI

향후 개선 항목. 현재 스코프 밖이지만 기록해둠.

---

## 아키텍처

- [x] **Architect ↔ Designer 중재 루프** (최대 3회) ✅ 완료
  - `design()` 의 협의 루프 구현 (max_negotiation_rounds=3)
  - Designer → ACCEPT/CONFLICT 파싱 후 Architect 재호출
  - 파일: `backend/src/orchestrator/orchestrate.py::design`, `output_parser.py::parse_design_verdict`

- [x] **의존성 기반 병렬 실행** (DAG 스케줄러) ✅ 완료 (ha-build)
  - `/ha-build --parallel T-001,T-002` 지원 (ultrawork 패턴)
  - depends_on 검증 + 병렬 그룹 내 충돌 방지
  - 파일: `~/.claude/skills/ha-build/run.py`
  - **Orchestra 내부 사용은 미완** — run_phases() 에서 진짜 topological sort 는 후속

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

---

## v2 후속 (Phase 4+)

- [ ] **Orchestra production 흐름의 v2 wiring**
  - 현재: `run_pipeline_with_phases()` 가 레거시 `materialize_skeleton` 사용
  - 개선: `assemble_skeleton_for_profiles()` 직접 호출로 전환
  - 파일: `backend/src/orchestrator/orchestrate.py:787`

- [ ] **/my-* 스킬 삭제 (Phase 4)**
  - 12개 스킬: `~/.claude/skills/my-*/`
  - 사전 조건: /ha-* 로 실제 프로젝트 1개 완주 검증

- [ ] **레거시 코드 정리 (Phase 4)**
  - `SECTION_MAP`, `fill_skeleton_template`, `extract_section` (번호 기반)
  - `backend/src/orchestrator/context.py` + `orchestrate.py`

- [ ] **ccg 멀티 LLM consensus**
  - Reviewer 판단 고위험 결정만 Claude+Codex+Gemini 합의
  - 사전 조건: codex CLI 설치 + gemini API 키

- [ ] **Plugins 패키징**
  - HarnessAI 를 oh-my-claudecode plugin 으로 배포 가능하게
  - manifest + install 스크립트

- [ ] **비용 추적**
  - 각 에이전트 실행마다 token usage + 추정 비용 harness-plan 에 누적
  - 파일: `backend/src/orchestrator/runner.py`

- [ ] **스트리밍 에이전트 출력**
  - `claude --stream` → WebSocket 실시간 브로드캐스트
  - 긴 빌드 UX 개선

- [ ] **Live LESSONS 자동 학습**
  - `/ha-review` 가 N회 발견한 패턴 → shared-lessons.md 자동 LESSON 후보 등록

- [ ] **LESSON 번호 자동 할당 도구** (harness validate 확장)
  - 배경: 2026-04-17 포트폴리오 업그레이드 plan-eng-review 중 LESSON-015/016/017 번호 충돌 발견 (React Native 프로젝트에서 이미 사용)
  - 기능: `harness validate` 가 shared-lessons.md 의 LESSON 번호 중복 감지 + "다음 사용 가능한 번호 = LESSON-021" 제안
  - 현재 상태: 수동으로 grep 해야 함. 향후 LESSON 추가 시 같은 문제 반복 가능
  - 시작점: `~/.claude/harness/bin/harness` 의 validate 로직에 LESSON 번호 스캔 추가
  - 의존성: 없음 (단독 작업 가능, ~30분)
