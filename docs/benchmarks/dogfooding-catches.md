# Dogfooding Catches — LESSON 원천과 현재 게이트

> **왜 이 문서가 있는가**: HarnessAI 의 품질 게이트 28개 LESSON 은 **전부 실제 사용 중 발생한 실수** 에서 유도됐다. 어떤 프로젝트의 어떤 이슈가 어떤 LESSON 을 낳았고, 현재 어떤 게이트가 그걸 자동 감지하는지 trace 한다.

---

## Scope

- **HarnessAI 자체**: 이 레포 (v1 은 HabitFlow/Personal Jira/금칙어게임 dogfooding, v2 는 code-hijack/ui-assistant/챙겼니 dogfooding)
- **파생 프로젝트**: 실제 빌드한 사이드 프로젝트 6개
  - **Personal Jira** (v1) — 이슈 트래커 / fastapi + nextjs
  - **HabitFlow** (v1) — 습관 관리 / fastapi + nextjs
  - **금칙어게임** (v1) — 파티 게임 웹앱 / fastapi + react
  - **code-hijack** (v2 1차 E2E) — 코드베이스 분석 CLI / python-cli
  - **ui-assistant** (v2 2차 E2E) — LLM UI 디자인 어시스턴트 / fastapi + react-vite 모노레포
  - **챙겼니** (v2 3차 E2E) — 알림/루틴 관리 모바일 앱 / react-native-expo (mobile-only)

## LESSON ↔ 원천 프로젝트 ↔ 현재 게이트 매핑

| LESSON | 원천 | 실제 증상 | 현재 감지 게이트 |
|---|---|---|---|
| **001** camelCase query param | Personal Jira | FastAPI 에서 `?projectId=` 받다가 snake_case 로 변환 누락 | `ha-review` LESSON 텍스트 참조 (Reviewer 판단) |
| **002** limit 상한 | Personal Jira | 기본 `le=100` 으로 설정해 보드/백로그에서 이슈 잘림 | skeleton `interface.http` 계약 + Reviewer |
| **003** updated_at 자동 갱신 | Personal Jira | DB 모델에 `onupdate` 빠져 수동 갱신 누락 | `db-guard` + Reviewer |
| **004** timezone-naive TIMESTAMP | Personal Jira | 배포 환경 TZ 로 버그 | Reviewer 판단 |
| **005** URL params = source of truth | Personal Jira | 필터 상태가 URL 과 state 에 중복 | Reviewer 판단 |
| **006** type=number CJK | HabitFlow | 한글 입력 중 IME 충돌로 숫자 필드 깨짐 | Reviewer + UI 리뷰 |
| **007** ID 타입 명시 | Personal Jira | Integer auto-increment vs UUID 불일치로 타입 mismatch | skeleton `persistence` 섹션 + Reviewer |
| **008** 버튼/액션 누락 | Personal Jira | API 있는데 프론트에 UI 없음 | Reviewer (interface.http ↔ view.* 대조) |
| **009** 컴포넌트 직접 API 호출 | HabitFlow | 컴포넌트가 axios 직접 호출 → 상태 일관성 깨짐 | Reviewer |
| **010** 에러 처리 형식 통일 | Personal Jira | 3가지 에러 포맷 공존 → 프론트 파싱 복잡 | skeleton `errors` 섹션 강제 + Reviewer |
| **011** Tailwind v4 @layer | HabitFlow | 유틸리티가 커스텀 CSS 에 덮임 | Reviewer (CSS 패턴) |
| **012** 백엔드 실행 명령어 | HabitFlow | README 에 `uvicorn` 실행 명령 누락 | skeleton `notes` + Reviewer |
| **013** 프론트엔드 테스트 전략 | HabitFlow | task breakdown 에 프론트 테스트 0개 | **`test-distribution`** (v2 신규 게이트, A6) |
| **014** 디자인 시스템 소스 명시 | HabitFlow | Designer 가 색상을 직접 정의 → 품질 편차 | skeleton `view.screens` 가이드 + Reviewer |
| **015** RN 비동기 재진입 | 외부 RN 프로젝트 | concurrent restart → race | 텍스트 참조 (LESSON만) |
| **016** RN stale reference | 외부 RN 프로젝트 | await 이후 stale ref 사용 | 텍스트 참조 |
| **017** RN float 비교 | 외부 RN 프로젝트 | 부동소수점 === 비교 | 텍스트 참조 |
| **018** dead 상수 (backoff vs max_retries) | **code-hijack 1차 E2E** | `_BACKOFF=(1,2,4,8)` 인데 `range(2)` 로 2개만 씀 | **`ai-slop` 정규식** (자동 감지) |
| **019** stderr 번역 | **code-hijack 1차 E2E** | subprocess 실패 시 raw stderr 노출 → UX 열악 | Reviewer + shared-lessons 참조 |
| **020** `[N/M]` 진행표시 | **code-hijack 1차 E2E** | 진행 표시는 있지만 실제 업데이트 안 됨 (껍데기) | Reviewer + ai-slop 후속 패턴 여지 |
| **021** done = test+lint+**type** | **ui-assistant 2차 E2E** | `/ha-verify` 가 test-only, pyright 15 errors 가 done 뒤에 드러남 | **`toolchain-gate`** (v2 LESSON-021 구현, `ha-build` 내장) |

## 자동 감지 vs 텍스트 참조

- **자동 감지 (결정론적)**: LESSON-013 (test-distribution), LESSON-018 (ai-slop dead 상수 정규식), LESSON-021 (toolchain-gate) — 3개
- **구조적 강제**: LESSON-002/007/008/010/012/014 — skeleton 섹션 계약이 사전에 선언을 강제 → 누락 자체가 일어나지 않음
- **텍스트 참조**: 나머지 — Reviewer 에이전트가 shared-lessons.md 를 컨텍스트로 받아 사례 기반 판단

## 챙겼니 3차 E2E — v0.8.0/v0.9.0 결함 노출 (2026-05-11~12)

**프로젝트**: 챙겼니 — React Native + Expo (mobile-only, no backend). `/ha-init → /ha-design → /ha-plan` 진행 중 11개 결함 노출.

### 노출된 결함과 수정 (v0.8.0 / v0.9.0)

| 결함 ID | 증상 | 수정 |
|---|---|---|
| **mobile-only false-positive** | `interface.http` / `rate_limiting` / `slo` 섹션이 mobile-only 프로젝트에 활성화 | v0.8.0: `capabilities.py` atom 단일 진실 소스 + `consistency.py` 교차 검증 |
| **auth/persistence false-negative** | 모바일 앱에 `auth` / `persistence` 가 빠짐 | v0.8.0: `derive_axes_capabilities` 로 mobile atom 에서 users/storage 자동 유도 |
| **mobile_coder_rn 라우팅 오류** | RN coder 가 auth API (backend 작업) 받음 | v0.8.0: `agent_matching.py` task→agent 1차 가드 |
| **fractional task ID (T-024.5)** | Orchestrator 가 소수 task ID 생성 | v0.8.0: `tasks_schema.py` T-NNN 강제 검증 |
| **V3: RN bun test** | `react-native-expo` 프로파일 toolchain 이 npm test 사용 | v0.9.0: bun test 로 정정 |
| **R1: ha-review not-git** | git 저장소 아닌 디렉토리에서 조용히 실패 | v0.9.0: fail-fast WARN 출력 |
| **B1/B5: state machine** | `building` 중복 진입 + plan/tasks 비원자 쓰기 | v0.9.0: assert_state 가드 + atomic write |
| **R2/R5/R6/V6: record gate** | ha-review/ha-verify 기록 미저장 | v0.9.0: verify_history / review_history 저장 |
| **B6: file_structure drift** | skeleton 선언 경로 vs 실재 FS 미점검 | v0.9.0: file_structure drift audit 추가 |
| **V1/R4: skeleton_hash** | legacy plan 에 skeleton_hash 미저장 → 외부 수정 감지 불가 | v0.9.0: `harness migrate-skeleton-hash` CLI |
| **B3/V2/V5: UX 누락** | 테스트 0개 WARN 없음, integrity verbose 없음, 실패 분류 없음 | v0.9.0: no-tests WARN + integrity verbose + `harness analyze-failure` |

### 결과

- **v0.8.0**: 5개 그룹 + 보강 수정 → 신규 모듈 7개, 회귀 +220 (761 passed)
- **v0.9.0**: 11개 결함 전체 수정 → 회귀 +105 (866 passed)
- **게이트화**: mobile-only false-positive/negative 가 `capabilities.py` + `consistency.py` 의 결정론적 검증으로 → 재발 구조적 차단

---

## 관찰: v1 → v2 변화

v1 (Personal Jira/HabitFlow) 시절 LESSON 은 **사후 학습** 뿐 — "다음엔 조심하자" 텍스트. 반복률은 낮아졌지만 재발 제로 보장 X.

v2 (code-hijack/ui-assistant) 부터 **게이트화 3건**:

1. **LESSON-013 → test-distribution 게이트** (2026-04, commit `7dc7a3e` 근방)
2. **LESSON-018 → ai-slop 7번째 패턴** ([ADR-004](../decisions/004-ai-slop-as-7th-hook.md))
3. **LESSON-021 → toolchain-gate** ([commit `01ce1cb`](https://github.com/reasonableplan/harnessai/commit/01ce1cb))

챙겼니 (3차 E2E, v0.8.0/v0.9.0) 부터 **인프라 게이트화 2건 추가**:

4. **mobile-only false-positive/negative → `capabilities.py` + `consistency.py`** — atom 단일 소스 + 교차 검증으로 결정론적 차단 (v0.8.0)
5. **file_structure drift → ha-build advisory WARN** — skeleton 선언 ↔ 실재 FS 편차 빌드 시 감지 (v0.9.0)

— LESSON 이 단순 기록에서 **게이트 강제**로 올라가는 흐름. 이것이 v2 의 핵심 가치.

## Plain Claude 와 비교 (정성적)

이 레포가 아닌 일반 Claude Code 세션에서 같은 프로젝트를 돌릴 때 **회귀 가능성**:

| 케이스 | HarnessAI | plain Claude |
|---|---|---|
| 허용 안 한 패키지 import | 빌드 중단 (dependency-check BLOCK) | 성공, 리뷰어 운좋아야 발견 |
| 하드코딩 API 키 누락 커밋 | 커밋 전 BLOCK (secret-filter) | git-hooks 없으면 통과 |
| f-string SQL | BLOCK (db-guard) | 리뷰어 눈썰미 의존 |
| `_BACKOFF=(1,2,4,8)` + `range(2)` | WARN (ai-slop, LESSON-018) | 정상 동작하므로 발견 안 됨 |
| pytest 통과지만 pyright 실패 상태 `done` 마킹 | BLOCK (toolchain-gate, LESSON-021) | 수동 체크 안 돌리면 숨음 |
| skeleton 에 없는 `@router.post("/admin/wipe")` | BLOCK (contract-validator) | 스펙-코드 drift 감지 경로 없음 |

plain Claude 가 못한다는 것이 아니라, **HarnessAI 는 "이 클래스의 실수는 이제 구조적으로 막힌다" 라고 보증** 한다는 차이. 28개 LESSON 이 28번 발견된 버그의 역사이므로, 게이트화된 것은 **재발률이 0 에 근사**.

## 관련 문서

- [gate-coverage.md](gate-coverage.md) — 게이트 정량 벤치마크 (35/35 pass)
- [../e2e-reports/code-hijack.md](../e2e-reports/code-hijack.md) — 1차 E2E 기록 (LESSON-018/019/020 원천)
- [../e2e-reports/ui-assistant-initial.md](../e2e-reports/ui-assistant-initial.md) — 2차 E2E (LESSON-021 원천)
- [`backend/docs/shared-lessons.md`](../../backend/docs/shared-lessons.md) — 28개 LESSON 전문
- [`docs/decisions/`](../decisions/) — ADR 5개 (LESSON 을 게이트화한 설계 결정)

## 정직한 한계

- **실제 반복률 / 방지율 수치 없음**: LESSON 이 게이트화되기 전/후의 재발 횟수를 체계적으로 추적하지 않았음. 향후 `/ha-review` 가 LESSON 히트를 로깅하면 정량 가능 ([TODOS.md](../../TODOS.md) — Live LESSONS 자동 학습).
- **Plain Claude 직접 비교 없음**: 동일 요구사항을 plain Claude 에게도 돌려서 결과를 diff 하는 controlled experiment 는 비용/시간 한계로 미실시. 이 문서는 **구조적 차이** 의 정성적 기록.
