# Changelog

HarnessAI 의 모든 주요 변경 사항. 형식은 [Keep a Changelog](https://keepachangelog.com/) 기준, 버전은 [SemVer](https://semver.org/) 준수 (pre-1.0 단계).

---

## [0.11.0] — 2026-06-10 — "Design Integrity & Intent Capture"

전체 시스템 리뷰 (프롬프트 감사 + 코드/아키텍처 리뷰 에이전트 2종 병렬 + 최신 기법 리서치) 의 결함 수정 + 사용자 dogfood 피드백 ("작동은 하는데 의도와 다르게 작동") 대응. 설계 게이트 3→6개, 의도 손실 깔때기 5지점 봉합.

### Added

- **skeleton drift 게이트** (`/ha-build prepare`) — freeze 후 외부 수정 감지 시 BLOCK. `--accept-skeleton-drift` 로만 우회. 기존엔 skeleton 을 가장 많이 소비하는 build 단계에 hash 검사가 없었음
- **섹션별 hash 결정론 rebuild** — `plan.section_hashes` snapshot (ha-design commit / ha-redesign apply 기록). `/ha-redesign` 이 변경 섹션을 diff 해 `skeleton 참조` 하는 done task 를 **agent recall 과 무관하게** `needs_rebuild` 파생 (`hash_derived_rebuild_candidates`)
- **역방향 contract 검증** (`/ha-review prepare`) — `interface.http` 에 선언됐는데 소스에 정적 prefix 가 없는 엔드포인트 보고 (`missing_declared_endpoints`, SKILL §2.9). 기존 contract-validator (초과 구현) 와 합쳐 양방향 완성
- **설계-시점 cross-section 검증** (`/ha-design commit`, `design_findings`) — error_ux 코드↔errors 정의 / 화면 참조 API↔interface.http 선언 / Auth 칸 공백을 기계 대조 — §4 충돌 검토 (LLM 절차) 의 기계 보강
- **의도 포착 배치** (`/ha-design`) — Intent Echo (후보 생성 전 이해 재서술 + 모호점 질문) · 기능별 **Given/When/Then 수용 기준** HITL 확정 (Step D) · 게이트 **행동 워크스루** (구조 표 + 사용 장면 서사) · **모호어 스캔** §4.5 (알아서/적절히/자동으로 → 질문화) · **적대적 자가비판** §4.7 (깨지는 시나리오 3개 → 막는 섹션 확인)
- **루프 탈출 가드** (`/ha-verify record`) — 동일 T-ID 3회째 FAIL 은 차단 (`--force-continue` 우회). build↔verify 무한 왕복 방지
- **`/ha-ship`** — `reviewed → shipped` 라스트마일 마킹 (상태머신에 정의만 있고 운전자가 없던 고아 상태 해소)
- **6축 모순 경고** (`/ha-init`, `axis_warnings`) — `monetization=payment + data_sensitivity=none` / `availability=high + lifecycle=poc`
- **conventions.md 생성 경로** (`/ha-init` §6.5) — 모든 에이전트 권위 1순위 문서의 생성 단계 공석 해소 (/code-hijack 연결 / 스텁 생성)
- **시니어 핸드오프 노트** — 활성 에이전트 9종 프롬프트 (한 일 / 우려 1가지 / 이견 / 다음 역할에게) + ha-build/ha-plan/ha-design 의 사용자 노출 relay
- **3중 제목 동기 테스트** — fragment frontmatter name = 본문 헤딩 = SECTION_TITLES. 첫 실행에서 실제 drift 2건 적발
- 문서: `backend/docs/GATES.md` (게이트 전수 — BLOCK 15 + advisory 10+), `harness/templates/skeleton/_README.md` (fragment 작성 가이드), `backend/docs/prompt-evaluation-2026-06-10.md` (프롬프트 감사)

### Fixed

- **SECTION_TITLES drift** — `environments`("환경 분리") / `error_ux`("에러 처리 UX") 가 fragment 와 어긋나 제목 키잉 기능 전부에 invisible 이었음
- **consistency checker ID-키잉** — 하드코딩 §13/14/15 가 동적 섹션 번호 체계에서 엉뚱한 섹션을 검사하던 결함 (리뷰 에이전트 2종이 독립 수렴한 최대 발견)
- **fail-open 5곳** — ha-plan/ha-init 파일쓰기 가드 (실패 시 상태 전이 중단), ha-plan re.sub 람다화 (LLM 출력 `` 주입), 프로파일 로드 blind except 협소화 (agent-mismatch 게이트 공허 통과 차단), ha-review git diff timeout, profile_loader 부모 누락 stderr 경고
- **fragment de-rot** — tasks 의 가짜 6컬럼 스키마 → 실제 파서 5컬럼 + 실상태값, 존재하지 않는 `--reset` 안내 제거, AI 후보 표 5→3행 (런타임 ha-design 과 동기), view.components 의 HabitFlow 잔재 + 고정 다크 팔레트 시드 제거 (LESSON-014 모순), state.flow 중복 소절 삭제, 웹 전용 CVA 규칙 → 프로파일 위임
- **ha-deepinit Agent model 핀** — `model: "sonnet"` 누락으로 1M 컨텍스트 부모 상속 시 크레딧 에러 (실증 후 수정)
- `built` 전이 시 skipped 태스크 목록 공개 (`skipped_tasks` — 사일런트 게이트 우회 차단)

### Changed / Deprecated

- **v1 Orchestra 경로 deprecated** — `reviewer`/`qa` CLAUDE.md + `orchestrate.py` 에 표시. v2 에선 `/ha-review` (fp-check + LESSON + 7훅) / `/ha-verify` 가 대체. 코드/테스트는 유지
- guideline 블록 dedup — `_ha_shared/GUIDELINES_NOTE.md` 단일 원천으로 6개 스킬 통일
- 모바일 코더 4종 프롬프트 섹션 순서 통일 (권위 → 자율결정금지 → 골든원칙)
- repo↔`~/.claude` 미러 정리 — stale backport 해소 + byte-identical 동기 운영 (ha-design run.py 만 의도적 divergence)

**후반 추가 (같은 날)**: canonical 섹션 삽입 (`user_journey` 가 notes 뒤 dangling 하던 결함 — `CANONICAL_SECTION_ORDER`), ha-verify **가짜 FAIL 가드** (`test_dir_warning` — profile cwd 오매칭 시 실행 전 경고, python-cli paths 의 `backend/` 제거), `harness validate` 0 errors/0 warnings (stale ID 셋·`_`파일 스캔·slo 괄호식), 약모델 프롬프트 다이어트 (architect/designer 체크리스트→인변량 ≤7, backend_coder JWT 3중사본→포인터 264→219줄, ha-design 519→391줄 + 실행 진행표 + 게이트 8블록→표), assert 누락 테스트 3건 수정, LESSON 자동학습 루프 첫 완주 (**LESSON-029** promotion).

테스트 939 → **994** (+55). ruff check/format · pyright · validate · gate benchmark 전부 clean.

---

## [0.10.0] — 2026-05-15 — "HITL Gate"

ChatDev Experiential Co-Learning + aider confirm gate 영감으로 *사람-AI 결정권 분리* 강화. LESSON-014 / DESIGN-1 / ARCH-2 처럼 AI 추측 채우기로 발생하던 밋밋한 결과 패턴 차단.

### Added

- **HITL gate** — 페르소나 / 시나리오 / 화면 시안 = 사용자 인터뷰로만 채움. AI 추측 차단.
  - `<!-- HUMAN-LOCKED:<section_id> -->` 마커 + `~/.claude/harness/bin/check_locked.py` PreToolUse hook (Edit/Write 차단)
  - `HarnessPlan.frozen_status` (drafting/frozen), `frozen_at`, `locked_sections`, `ai_drafted_sections` 4 필드
  - `PlanManager.freeze()` — one-way gate (no unfreeze; rollback 은 `/ha-redesign` audit 통해)
- **`/ha-design` HITL 인터뷰** — LOCKED 섹션마다 AI 후보 5 개 → AskUserQuestion → 사용자 선택. `--ai-draft` 옵트인으로 AI 추측 채우기 (사용자 후속 promotion 필요)
- **`/ha-build` 진입 게이트** — `frozen_status="frozen"` 필수. `--skip-frozen-gate` 마이그레이션용 escape hatch
- **`/ha-review extract-lesson`** — 리뷰에서 패턴 발견 시 `shared-lessons.md` 의 Pending Lessons 섹션에 auto-append. 사용자 수동 promotion 으로만 main 진입 (가짜 LESSON 자동 적용 방지). ChatDev 영감
- **`/ha-log` 마이크로 스킬** — `worklog.md` 수동 append (discussion / change / next 카테고리). `/ha-design`, `/ha-build` (done), `/ha-redesign` (apply) 자동 append (subprocess)
- **`harness migrate-v10`** — v0.9.x → v0.10.0 마이그레이션. default drafting + `--auto-freeze` + `--dry-run` + `*.v9.bak` 백업
- Reviewer-driven hardening: `freeze(ai_drafted_sections=None vs [])` 분리, `_plan_to_dict` `frozen_status` validation, fragment placeholder 컨벤션 주석
- fragment 3 강화 — `requirements` / `user_journey` / `view.screens` 에 LOCKED 마커 + AI 제안 후보 슬롯 + HITL gate 가이드 + Mobbin/Dribbble 디자인 레퍼런스 URL 슬롯

### Fixed

- `test_context.py::test_all_36_standard_sections_present` — expected_ids 에 `environments` / `error_ux` / `rate_limiting` 3 개 추가 (실제 SECTION_TITLES 와 동기화)

### Migration

v0.9.x → v0.10.0 흐름:
1. `python ~/.claude/harness/bin/harness migrate-v10 <project>` — frontmatter 에 lock 필드 박음 (drafting default)
2. `/ha-design` 재실행 — HITL 인터뷰 통과 + freeze
3. `/ha-build` 정상 진행

또는 escape hatch (개발용): `--auto-freeze` (사용자 책임), `/ha-build --skip-frozen-gate`

backward-compat: legacy v0.9.x plan 은 `frozen_status` 미존재 시 default `"drafting"` 으로 자동 로드.

### Tests

- pytest **939/939 pass** (+39 신규 — T1~T9 + reviewer hardening 합산)
- ruff / pyright clean
- mirror sync: 모든 스킬 양쪽 (`~/.claude/skills/` ↔ `<repo>/skills/`) 바이트 동일

### 비교 분석

OSS 비교 (MetaGPT / ChatDev / OpenHands / aider / CrewAI) 결과 — HITL gate 는 ChatDev / aider / CrewAI 3 개에 있고 HarnessAI 만 없었음. v0.10.0 으로 따라잡음. 자동 LESSON 추출 (ChatDev) 도 함께 박음. 벡터 메모리 (CrewAI) + 실행 sandbox (OpenHands) 는 v1.0.0 백로그.

---

## [0.9.2] — 2026-05-12 — "audit cleanup"

Final verification: **pytest 893 pass / ruff clean / pyright 0 errors**.

핵심 가치: mirror sync (repo ↔ `~/.claude` 5파일 drift 회복), profile 보강 (LESSON-STYLE-001 정의 + whitelist/detect 항목 추가), 명세-코드 격차 3건 (G1 ha-deepinit augment-plan, G2 ha-verify integrity gate 자동 실행, G3 ha-build git WARN) 구현으로 설계 문서와 실제 코드가 일치하도록 정비.

### Added

- **`ha-deepinit augment-plan`** — G1: `ha-deepinit` 의 augment-plan 명령 구현. 기존 코드베이스 분석 결과를 harness-plan.md 에 반영 (신규 회귀 +23).
- **LESSON-STYLE-001** — profile 공통 원칙에 코딩 스타일 컨벤션 정의 항목 신규 추가.

### Changed

- **mirror sync** — `c760762`: repo 내 5개 파일 (`skeleton_hash.py`, `skeleton_stale.py`, `consistency.py`, `capabilities.py`, `agent_matching.py`) 과 `~/.claude` 사본 간 drift 회복. `skeleton_hash` frontmatter 미저장 버그 수정.
- **profile 보강** — `10a5432`: `python-lib` entry_points 추가, `drizzle-orm` / `python-multipart` / `@types/express` whitelist 추가, `android-kotlin` env_config 보강.
- **ha-verify integrity gate 자동 실행** — G2: `harness integrity` 를 `/ha-verify` 가 자동으로 실행하도록 명세 반영.
- **ha-build git WARN** — G3: ha-build 가 uncommitted 변경 감지 시 WARN 출력.

---

## [0.9.1] — 2026-05-12 — "graph CLI backfill"

Final verification: **pytest 870 pass / ruff clean / pyright 0 errors**.

핵심 가치: v0.8.0 CHANGELOG + 메모리에 `harness graph` CLI 가 추가됐다고 기록됐으나 실제 미구현이었던 사실을 dogfooding 중 발견 → 보충 구현. test_graph_cli.py 의 pre-existing failure 4건 해소.

### Added

- **`harness graph <tasks-path>`** — tasks.md → Mermaid 의존성 그래프 렌더링 CLI (142 lines). `--inject` 로 tasks.md 에 그래프 삽입, `--no-phases` 로 Phase 구분 없이 플랫 출력. 회귀 테스트 +4.

### Fixed

- **`test_graph_cli.py` pre-existing failure 4건** — v0.8.0 시점부터 존재하던 실패 해소.

---

## [0.9.0] — 2026-05-12 — "챙겼니 dogfood fixes"

Final verification: **pytest 866 pass / ruff clean / pyright 0 errors**.

핵심 가치: 챙겼니 (React Native/Expo) dogfooding 으로 노출된 결함 11건 (V1~V6, R1~R6, B1~B6) 전체 수정. 신규 CLI 2개 (`migrate-skeleton-hash`, `analyze-failure`), 회귀 테스트 +105.

### Added

- **`harness migrate-skeleton-hash`** — legacy plan 에 `skeleton_hash` 필드 없거나 잘못된 경우 마이그레이션 CLI. `--apply` 로 실제 갱신.
- **`harness analyze-failure`** — `/ha-build` 실패 시 원인 분류 + 권고 출력 CLI (B3/V5).
- **신규 회귀 테스트 +105** — v0.9.0 결함 fix 에 대한 regression coverage.

### Fixed

- **V3: RN profile bun test** — `react-native-expo` 프로파일 toolchain test 명령 `bun test` 로 정정.
- **R1: ha-review not-git silent fail** — git 저장소 아닌 디렉토리에서 `/ha-review` 가 조용히 실패하던 버그. fail-fast WARN 출력으로 변경.
- **B5/B1: ha-build state machine + atomic plan/tasks** — `building` 중복 진입 차단 + plan/tasks 파일 atomic 쓰기.
- **R2/R5/R6/V6: record gate** — `/ha-review` 와 `/ha-verify` 가 실행 기록(verify_history / review_history)을 저장하지 않던 버그. security hooks + violations/rework 결과 기록.
- **V1/R4 + B6: hash migration + file_structure drift** — legacy `skeleton_hash` 미저장 → 마이그레이션 + `file_structure` 섹션 drift audit 추가 (B6).
- **B3/V2/V5: no-tests WARN + integrity verbose + analyze-failure** — 테스트 파일 0개 시 WARN, `harness integrity` verbose 모드, `analyze-failure` CLI.

---

## [0.8.0] — 2026-05-11 — "design defect fixes"

Final verification: **pytest 761 pass / ruff clean / pyright 0 errors / harness validate 0 errors**.

핵심 가치: 챙겼니 dogfooding reverse-engineering 으로 5개 그룹 + 보강 결함 발견 → 인프라 모듈 7개 신설, frontmatter 필드 4개 추가, CLI 1개 (`migrate-plan`). 기존 설계 문서와 실제 코드 사이 구조적 격차를 대규모 수정.

### Added

- **신규 인프라 모듈 7개** (`backend/src/orchestrator/`):
  - `capabilities.py` — `KNOWN_CAPABILITY_ATOMS` (14개 atom single source of truth), `derive_axes_capabilities`, `validate_capability_set`
  - `consistency.py` — `find_consistency_violations`, `_HAS_KEY_PROVIDERS` (atom → provider profile 셋)
  - `lessons.py` — `extract_known_lessons`, `find_unknown_lesson_references`
  - `agent_matching.py` — `match_task_to_agent`, `find_best_agent_for_task`, `AgentMatchResult`
  - `tasks_schema.py` — `validate_tasks_md` (T-NNN 강제), `TaskNode/TaskGraph`, `extract_task_graph`, `render_mermaid`
  - `skeleton_hash.py` — `compute_skeleton_hash` (CRLF/LF 정규화), `check_skeleton_hash`
  - `skeleton_stale.py` — `preview_skeleton_stale`, `mark_skeleton_stale`

- **신규 frontmatter 필드 4개** (`HarnessPlan`):
  - `activation_trace` — 활성 섹션별 `required_when` 표현식 audit trail
  - `skeleton_hash` — skeleton.md SHA-256, 외부 수정 감지
  - `eng_review_history` — `/plan-eng-review` 등 외부 도구 audit trail
  - `external_capabilities` — BaaS/Firebase 등 외부 backend escape hatch

- **`harness migrate-plan <path>`** — stale plan 정정 + skeleton STALE 마킹 CLI (`--apply` / `--mark-skeleton-stale` / `--no-backup`).

- **신규 escape flags** — `--allow-agent-mismatch`, `--allow-format-drift`, `--allow-unknown-lessons`, `--external-capabilities`.

- **회귀 테스트 +220** (541 → 761).

### Fixed

- **mobile-only false-positive** — `interface.http` / `rate_limiting` / `slo` 섹션이 mobile-only 프로젝트에서 활성화되던 버그.
- **`auth` / `persistence` false-negative** — mobile-only 프로젝트에서 필수 섹션이 빠지던 버그.
- **`mobile_coder_rn` backend task 라우팅** — RN coder 에게 auth API 같은 backend task 가 잘못 배분되던 버그.
- **fractional task ID** — `T-024.5` 같은 소수 ID 생성 방지 (`tasks_schema.py` T-NNN 강제).
- **`/plan-eng-review` skeleton 직접 수정** — `skeleton_hash` 로 외부 수정 사후 감지.
- **`adapt_diff` TypeError** — `3ea95c1` review feedback.

### Migration

기존 v0.7.0 사용자:
- `./install.ps1 -Force` 또는 `./install.sh --force` 재실행 — 신규 모듈 7개 + harness bin 변경 동기화 필수.
- `harness migrate-plan <path> --apply` — 기존 `harness-plan.md` 에 신규 frontmatter 필드 추가 (선택, 하위 호환).

---

## [0.7.0] — 2026-05-11 — "web + desktop profiles"

Final verification snapshot at release time:
**pytest 569 pass / ruff clean / pyright 0 / harness validate 50 files 0 errors**.

핵심 사용자 가치: Next.js / NestJS / Electron 3개 프로파일 추가로 HarnessAI 커버리지를 풀스택 웹(App Router) · Node.js 백엔드 · 데스크톱까지 확장. 신규 skeleton fragment 3개 (environments / error_ux / rate_limiting) 로 HTTP/UI/CLI 프로젝트 계약서 품질 향상. 상태 머신 버그 2건 + 크로스 플랫폼 테스트 버그 수정.

### Added

- **3 web/desktop profiles** (`harness/profiles/`):
  - `nextjs.md` — Next.js App Router (Server Components 기본 · Server Actions 뮤테이션 · better-auth/NextAuth · Drizzle ORM · Zustand 클라이언트 UI 상태만)
  - `nestjs.md` — NestJS 백엔드 (TypeORM · class-validator · ValidationPipe · Passport JWT 2-strategy · GlobalExceptionFilter → `{ error, code, details }`)
  - `electron.md` — Electron 데스크톱 (Context Isolation 필수 · preload contextBridge IPC · 채널명 상수화 · electron-updater 자동 업데이트 · 코드 서명)

- **3 new skeleton fragments** (`harness/templates/skeleton/`):
  - `environments.md` — 환경별 config (dev/staging/prod) + 시크릿 관리 (`required_when: has.http_server or has.ui or has.navigation or has.cli_entrypoint`)
  - `error_ux.md` — 사용자 에러 경험 설계 (에러 메시지 계층 · fallback UI · 재시도 UX, `required_when: has.ui`)
  - `rate_limiting.md` — API rate limit 설계 (전략 · 임계값 · 응답 형식 · 클라이언트 가이드, `required_when: has.http_server`)

- **`_registry.yaml`** detection rules 3개 추가 (nextjs · nestjs · electron)

- **lessons_applied** per new profile:
  - nextjs: LESSON-006, 022, 023, 027, STYLE-001
  - nestjs: LESSON-002, 003, 004, 007, 018, 022, 023, 024, 027
  - electron: LESSON-006, 022, 023, 027, STYLE-001

### Changed

- **`slo.md`** `required_when`: `user_scale in [medium, large] or availability in [standard, high]` → `scale.medium_or_larger or availability == high`. Solo/S 프로젝트에서 `availability=standard` 만으로 SLO 섹션이 활성화되던 과잉 포함 방지.
- **`observability.md`** `required_when`: `has.production_concerns` → `has.production_concerns and scale.medium_or_larger`. S 규모 프로젝트에서 observability 섹션 과부하 방지.
- **`ha-design/SKILL.md`** auth gate: 프론트엔드/모바일 프로파일이 포함된 경우에만 silent refresh / 탭 동기화 항목 확인하도록 조건 추가.
- **테스트 +55** (496 → 551, 회귀 0): 신규 ha-redesign 스킬 + consistency_checker 테스트, toolchain gate 크로스 플랫폼 수정 포함.

### Fixed

- **ha-review state machine**: `assert_state(["verified", "building"])` → `assert_state(["verified"])` — `building` 상태에서 review 가 실행되던 버그.
- **ha-verify state machine**: `assert_state(["built", "building"])` → `assert_state(["built"])` — `building` 상태에서 verify 가 실행되던 버그.
- **`error_ux.md` required_when**: `has.frontend` → `has.ui` — `has.frontend` 가 `_SECTION_TO_HAS_KEY` 에 없어 항상 False 로 평가되던 버그.
- **toolchain gate 테스트**: `true`/`false` Unix 명령 → `subprocess.run` monkeypatch — Windows 에서 5개 테스트 전부 실패하던 크로스 플랫폼 버그.
- **paired-profile section ordering**: 2차 프로파일(mobile.*) 섹션이 tasks/notes 뒤에 추가되던 버그. 모든 프로파일 `order` 배열 병합 후 tasks/notes 마지막 배치로 수정.
- **`security_hooks` auth-guard 모바일 분리**: `is_mobile=True` 시 `_AUTH_MOBILE_PATTERNS` 독립 적용 — AsyncStorage / SharedPreferences / UserDefaults 토큰 저장 BLOCK, `.getString` 토큰 읽기 WARN. 기존엔 `is_frontend=True` 로 합산돼 백엔드 전용 룰(logout no-op 등)이 모바일 코드에도 적용되던 버그 수정.
- **`security_hooks` false positive 2건**: (1) `func.max()+1` 패턴 — 쓰기 연산(`session.add` / `bulk_save_objects` 등) 없는 순수 조회에서 WARN 미발생. (2) `author*` 식별자(`authorName`, `authorId`) — `auth` 앵커 정규식으로 오탐 제거.
- **`security_hooks` LESSON-024 severity**: `RefreshRequest` body schema → BLOCK → WARN (휴리스틱 패턴이라 확정 위반이 아님).
- **`ha-build/run.py` security gate 2건**: (1) git diff 추가 줄만 스캔 (`+` prefix) — 삭제된 코드가 BLOCK 트리거하던 버그. (2) `git log` returncode 비정상 시 조용히 건너뛰던 버그 수정 (명시적 `continue`).
- **`ha-build` `--skip-security` 플래그**: toolchain 과 독립적으로 security_hooks 게이트만 우회 가능. 기존 `--skip-toolchain` 이 security 까지 묶어서 우회하던 혼선 해소.

### Migration

기존 v0.6.0 사용자:
- `./install.ps1 -Force` 또는 `./install.sh --force` 재실행 — 신규 프로파일 3개 + fragment 3개 글로벌 install 동기화 필수
- 기존 프로젝트는 영향 없음 (새 프로파일은 감지 규칙에 매칭될 때만 활성)

---

## [0.6.0] — 2026-05-07 — "mobile expansion"

Final verification snapshot at release time:
**pytest 496 pass / ruff clean / pyright 0 / harness validate 44 files 0 errors / 글로벌 install 82 files**.

핵심 사용자 가치: HarnessAI 의 9 quality gates + 21 LESSONs + skeleton contract + profile system 가치를 모바일 (React Native + Expo / Flutter / Android Kotlin + Compose / iOS Swift + SwiftUI) 까지 확장. 외부 사용자가 자기 모바일 프로젝트에서 `HARNESS_AI_HOME` 설정 + `/ha-init` 만으로 production-grade 컨벤션 + 가이드라인 + 보안 룰을 즉시 받음.

### Added

- **4 mobile profiles** (`harness/profiles/`):
  - `react-native-expo.md` — Expo SDK + Bun + Zustand + NativeWind + Expo Router
  - `flutter.md` — Flutter SDK + Riverpod + go_router + drift + dio + Material3
  - `android-kotlin.md` — Jetpack Compose + StateFlow + Room + Retrofit + Hilt + Gradle Version Catalog
  - `ios-swift.md` — SwiftUI + `@Observable` + NavigationStack + CoreData/SwiftData + URLSession + Keychain (Win 호스트 제약 명시)

- **3 mobile fragments** (`harness/templates/skeleton/mobile.{navigation,build_config,lifecycle}.md`)

- **4 mobile_coder agents** + 공통 prefix `mobile_coder_shared.md` (10 원칙, 4 prompts 에 인라인됨)

- **16 framework guidelines** (`harness/templates/guidelines/<profile>/*.md` × 4 frameworks × 4 files)

- **`/ha-*` skill 모바일 awareness**:
  - 6 skill cmd_prepare 출력에 `guideline_paths` 필드 (Phase A) — `skills/_ha_shared/utils.py` 의 `resolve_guideline_paths(profile_id)` helper
  - `/ha-init detect` 의 `is_mobile: bool` 필드 + stderr `[INFO]` 안내 (Phase B1)
  - `/ha-review` 의 4 mobile 보안 룰 — AsyncStorage/UserDefaults/SharedPreferences/shared_preferences 시크릿 저장 BLOCK / 권한 일괄 요청 WARN / CocoaPods 신규 추가 WARN / RN CLI 직접 사용 WARN (Phase B2)
  - `/ha-verify` 의 `platform_warnings` (`shutil.which` 점검 + iOS-on-Windows 가드 + JAVA_HOME 가드, Phase B3)
  - 6 SKILL.md 모바일 워크플로우 예시 섹션 (Phase B4)

- **신규 atom + 매핑** (`profile_loader._SECTION_TO_HAS_KEY` + `harness/bin/harness REQUIRED_WHEN_ATOMS`):
  `has.navigation` / `has.build_config` / `has.lifecycle`

- **`files_any` registry 매처** — Android Gradle (`build.gradle.kts` OR `build.gradle` OR `settings.gradle.kts`) / iOS (`Package.swift` OR `Podfile`) 등 OR 매칭 케이스

- **Backend Orchestra path 보강** (대시보드 사용자):
  - `OrchestratorConfig` Pydantic 7→11 agent fields (4 mobile_coder)
  - `AGENT_SECTIONS_BY_ID` mobile_coder × 4 + Designer 의 mobile.navigation/lifecycle
  - `EXTRA_HARNESS_DOCS` + `build_context.harness_dir` 파라미터 — harness-global guidelines 직접 로드
  - `_resolve_prompt_path` HARNESS_AI_HOME fallback (외부 프로젝트에서 `agent_prompts` 경로 자동 해결)
  - `is_mobile` 플래그 플러밍 (verify / implement_with_retry / run_phases / SecurityHooks.run_all, frontend 와 상호배타)

- **테스트 +76** (420 → 496, 회귀 0):
  - 매처 확장 / 4 mobile profile 통합 / context 매핑 / harness-global doc 로딩 / HARNESS_AI_HOME fallback / mobile 보안 룰 / platform_warnings / SKILL.md 모바일 예시 / guideline_paths 출력 (12 파라미터 통합 테스트 포함)

### Changed

- **Architect / Designer 시스템 프롬프트** — "## 모바일 프로파일 — 추가 책임" 섹션 신설. Architect 는 mobile.build_config / mobile.lifecycle / persistence (mobile DB), Designer 는 mobile.navigation / mobile.lifecycle UX / view.screens (mobile 변형)
- **Frontend Coder 시스템 프롬프트** — "web only" 명시. 모바일 task 잘못 라우팅 시 즉시 에스컬레이션
- **Orchestrator 시스템 프롬프트** — Task→Agent 매핑 표 6-row 확장 (mobile_coder × 4) + 모노레포 dispatch 우선순위
- **`SECTION_TITLES` / `STANDARD_SECTION_IDS` / `_BATCH_MODE_DIRECTIVE`** — 20 → 33 정합 (v0.5.0 가 추가했지만 미동기였던 fragment 10개도 동시 회복)
- **`_FRONTEND_PROFILES`** — `("react-vite",)` 단일화 (`nextjs.md` 미구현 → 룰 제거, R1)

### Fixed

- **v0.5.0 partial drift 회복** — `data_model` / `threat_model` / `audit_log` / `slo` / `runbook` / `test_strategy` / `user_journey` / `authorization_matrix` / `ci_cd` / `external_deps` 10 fragment 가 SECTION_TITLES + STANDARD_SECTION_IDS + _BATCH_MODE_DIRECTIVE 에 누락되어 있던 silent drift 동시 회복
- **글로벌 install drift** — v0.5.0 release 이후 `./install.sh` 재실행 누락으로 사용자 컴퓨터 글로벌 install 이 27 files 에서 정지. v0.6.0 작업 중 발견 + `./install.ps1 -Force` 실행으로 27 → 37 → 82 동기화
- **사용자 흐름 결함 D1~D6 + 2차 점검 결함** — backend Orchestra path 와 /ha-* skill path 가 분리된 두 codepath 임을 발견 + 양쪽 모두 fix
- **R1: nextjs registry stub** — `_registry.yaml` 에 룰만 있고 `harness/profiles/nextjs.md` 미구현 → 잠재 사용자 silent fail. 룰 제거. Next.js 사용자는 react-vite 프로파일 + frontend_coder 시스템 프롬프트 수정 (SETUP.md 예시 2)

### Migration

기존 v0.5.0 사용자:
- `./install.ps1 -Force` 또는 `./install.sh --force` 재실행 — 글로벌 install 동기화 필수
- `HARNESS_AI_HOME` 환경변수 설정 권장 (외부 모바일 프로젝트에서 mobile_coder 사용 시)
- 기존 web/CLI 프로젝트는 영향 없음

알려진 제약 (Phase 7 후속):
- iOS native 의 `xcodebuild` 빌드 검증은 Windows 호스트에서 불가능 — macOS GitHub Actions runner CI 추가 예정
- examples/<framework>-todo/ 등 sample app E2E 는 별도 (LLM 비용 + 실 빌드 필요)
- 라이브 LLM dispatch 검증 (D7) 은 외부 사용자 첫 dogfood 시 자동 검증으로 대체

---

## [0.5.0] — 2026-05-02 — "auto-fit skeleton"

Final verification snapshot at release time:
**pytest 420 pass / ruff 0 / pyright 0 / harness validate 37 files 0 errors / install snapshot 12/12 PASSED / CI green**.

핵심: 사용자가 6축만 답하면 적합한 skeleton 섹션이 자동 활성화. PII+mvp →
audit_log/threat_model/test_strategy/ci_cd/slo 자동 포함, none+poc → 모두
정확히 제외 (POC 비계 가볍게 유지). 표준 섹션 20 → 30, backend tests
357 → 420 (+ 신규 63), skeleton fragment 신규 10개.

### Added
- **scale_axes 6축 + /ha-init 자동 맞춤 skeleton** (Phase 1+2, `c33197a` →
  `36a0451`) — 사용자가 6축 (user_scale / data_sensitivity / team_size /
  availability / monetization / lifecycle) 만 답하면 적합한 fragment 가
  자동 활성화 → "맞춤 skeleton" 이 실제로 동작.
  - **Phase 1 — scale_axes 데이터 모델** (`c33197a`, `47212fb`):
    `ScaleAxes` frozen dataclass + `HarnessPlan.scale_axes` 필드 + frontmatter
    `scale_axes:` 직렬화. 하위 호환 (legacy frontmatter 도 default 로 로드).
    `/ha-init` 인터뷰 단계 추가 — S/M/L 프리셋 분기 + 6축 직접 답. argparse
    6개 인자 + cmd_write 통합. `--scale` 은 `--user-scale` 로 강제 동기화.
    `_AXIS_NAMES_CLI` ↔ `ScaleAxes` drift 방지 sync 테스트.
  - **Phase 2-a — 신규 skeleton fragment 10개** (`34359e4`):
    `data_model` (ERD Mermaid + PII + cascade + 마이그레이션 정책),
    `threat_model` (STRIDE/OWASP), `audit_log` (compliance), `slo`
    (p50/p95/p99 + 가용성 + RPS), `runbook` (알람→대응),
    `test_strategy` (Test pyramid + contract test), `user_journey`
    (Mermaid sequence/state), `authorization_matrix` (역할×리소스×액션),
    `ci_cd` (파이프라인+환경+롤백), `external_deps` (3rd-party SLA+폴백+
    webhook idempotency). 표준 섹션 20 → 30.
  - **Phase 2-b-1 — scale_expression 파서/평가기** (`077dcdc`, `7ce07a6`):
    `backend/src/orchestrator/scale_expression.py` 신규 — AST + tokenizer +
    재귀 하강 parser + evaluator. `data_sensitivity in [pii, payment] or
    availability == high` 같은 표현식을 ScaleAxes 인스턴스에 평가. 6축 axis
    이름은 `dataclasses.fields(ScaleAxes)` 동적 추출 → 새 axis 자동 인식.
    24+5 unit tests (atom/comparison/membership/boolean/precedence/error/
    parse-AST).
  - **Phase 2-b-2 — harness validator vocabulary 확장** (`ff6d8d0`):
    CLI validator 가 6축 표현식 syntax 인정 (atom + or/and/+ 결합 + 정규식
    sanity). 9 fragment 의 `required_when` 을 description 의 의도 표현식
    그대로 교체 (`always` → `data_sensitivity in [pii, payment]` 등).
    괄호 표현식은 명시적 reject (validator 신뢰성 보존, 정식 평가는
    backend parser).
  - **Phase 2-b-3 — ProfileLoader 활성 섹션 결정** (`b4952a0`):
    `compute_active_sections` / `compute_has_keys` / `compute_scale_tokens` /
    `load_fragments_metadata` 4개 method. `_SECTION_TO_HAS_KEY` (19개
    매핑) + `_USER_SCALE_TO_TOKENS` (cumulative). 17 unit tests.
  - **Phase 2-b-4 — /ha-init cmd_write auto-determine** (`b2682e1`,
    `4e8da81`): `--included` optional. 빈 값/`auto` 면 `compute_active_sections`
    호출 → 활성 섹션 자동 결정. SkeletonAssembler 의 `harness_dir` 통일
    (dev mode + install mode 둘 다 안전). `view.components` 의 `+` → `and`
    (parser 일관). Smoke 검증: PII+mvp → 18 sections / none+poc →
    13 sections (audit_log/threat_model/test_strategy/ci_cd/slo 자동
    포함 vs 정확히 제외).
  - **README 노출** (`36a0451`): "What it actually adapts" 섹션 추가
    (PII vs none 비교표 + 실 smoke 결과). 30개 섹션 ID 목록 + 6축 anchor
    링크. test count 361 → 420 동기화 (.md 9개).
- **결정권 분리 원칙 전면 적용** (`36c026d`, `8dd11f7`) — Architect/Designer 는
  skeleton 에 DB/화면/레이아웃 세부까지 확정, Orchestrator 는 tasks.md 에 태스크별
  구현 스펙 블록 작성, Coder 는 자율 결정 금지 + 미정의 시 `--status blocked`
  에스컬레이션. 5 에이전트 CLAUDE.md + ha-plan/ha-build SKILL.md 일관 업데이트.
  - **Architect CLAUDE.md** — DB 세부 완비 체크리스트 (컬럼/타입/NULL/UNIQUE/
    기본값/인덱스/FK ondelete/`DateTime(timezone=True)`), 모호함 금지 원칙
    ("적절한 인덱스" 같은 표현 금지), 백엔드 레이아웃 결정 책임 (src/ vs flat,
    디렉토리 구조, 파일 경로 예시).
  - **Designer CLAUDE.md** — 화면당 8 필드 체크리스트 (경로/레이아웃/인증/초기
    로딩/API/store/에러/flow), 컴포넌트별 파일 경로 + props 타입 명시, store
    state/action 시그니처 완비, 프론트엔드 레이아웃·파일명 결정 책임, React
    Query 하드코딩 제거 (conventions 위임).
  - **Orchestrator CLAUDE.md** — tasks.md 에 Phase 5컬럼 테이블 + 태스크별
    스펙 블록 (생성/수정 파일, skeleton 참조, 구현 세부, 참조 파일, 완료 기준)
    포맷 추가. 파서 호환성 유지 (5컬럼 regex 불변).
  - **Backend/Frontend Coder CLAUDE.md** — 권위 순서 섹션 (conventions > 루트
    CLAUDE.md > agent CLAUDE.md > tasks.md 스펙 블록 > skeleton), 자율 결정
    금지 테이블 (레이아웃/DB 필드/API 경로/파일명), 에스컬레이션 절차.
  - **ha-plan SKILL.md** — 출력 포맷 예시에 "태스크별 구현 스펙 블록" 추가,
    스펙 없는 태스크는 미완성 산출물로 간주.
  - **ha-build SKILL.md** — 읽기 순서에 tasks.md 스펙 블록 1순위 배치, 스펙
    불완전 시 blocked 에스컬레이션 절차 명시, 하위 호환 폴백 안내.
- **실측 검증 완료** — `bench-personaljira-v3` Stage B smoke test 로 결정권
  분리 효과 정량 확인: skeleton `persistence` 0→11 테이블, FK ondelete 0→16,
  `CustomException` subclass 0→15 (conventions 위반→완비), Sonnet Backend
  Coder Phase 1 10 태스크 실행 pytest **194 / ruff 0 / pyright 0** clean.
  자율 결정 14건 모두 자발 보고, 스펙 위반 0건. (리포트는 bench 디렉토리
  내부, 레포 외부).
- **`docs/ARCHITECTURE.md` 영어 버전 신규** — 현재 한국어는 `ARCHITECTURE.ko.md`
  로 이전, 양쪽 상단에 언어 토글 배너. 영어 버전은 섹션 11로 나누어 condensed
  ~200 라인 (한국어 원본은 worklog-style 상세).
- **`backend/.env.example` 전면 재작성** — stale 엔트리 (DATABASE_URL /
  GITHUB_* / ANTHROPIC_API_KEY — 미사용) 제거, 실제 읽히는 env 변수만 남김
  (HARNESS_AI_HOME / GEMINI_API_KEY / DASHBOARD_* / PROJECT_DIR).
- **CONTRIBUTING.md** `HARNESS_AI_HOME` 설명 보강 — /ha-* 스킬 v2 모듈
  import 용. 미설정 시 스킬만 실패 (backend tests 는 영향 없음) 명시.

### Changed
- **`install.sh` + `install.ps1` 메시지 전면 영어화** — 국제 사용자 대상.
  도움말 · progress · 변경 요약 · y/N 프롬프트 · 완료 안내 전부 영어.
  한국어는 README.ko.md 에서 제공.

### Fixed
- (항목 추가되는대로)

---

## [0.4.0] — 2026-04-20 — "portfolio-ready"

Final verification snapshot at release time:
**pytest 357 pass / ruff 0 / pyright 0 / gate_benchmark 35/35 (100% precision/recall/accuracy) / harness validate 27 files 0 errors**.

First tagged release. Goal: the repository is ready for public GitHub
disclosure — bilingual README, community standards (LICENSE/CoC/SECURITY),
CI, GitHub templates, working examples/, English code comments, profile-based
v2 pipeline in both skill and Orchestra paths, 9 quality gates benchmarked.

### Added
- **`docs/decisions/` ADR 5개** (B4) — Architecture Decision Records.
  - ADR-001: 프로파일 기반 아키텍처로의 전환
  - ADR-002: Skeleton 섹션 번호 → ID 전환
  - ADR-003: 파이프라인 상태를 `harness-plan.md` 단일 파일로
  - ADR-004: ai-slop 감지를 Reviewer 7번째 훅으로 통합
  - ADR-005: /my-\* 완전 삭제, /ha-\* single cut-over (Phase 4a + 4b 실행 완료)
- **`scripts/benchmark.py` + `docs/benchmarks/`** (B5 — 측정 가능한 부분) —
  LLM 호출 없이 5가지 핵심 연산 latency 측정. 30 iter 기준:
  profile 감지 **4.7 ms**, skeleton 조립 **0.13 ms**,
  `harness validate` **149 ms**, `harness integrity` **104 ms**,
  `find_placeholders` 100KB **0.14 ms** (선형 스케일).
- README 에 ADR / CONTRIBUTING / CHANGELOG / benchmarks / e2e-reports 링크 추가.
- **`docs/e2e-reports/` 신규** (B7 부분 착수) — dogfooding 증거.
  - `code-hijack.md`: 1차 E2E Phase 1+2 완주 기록 (pytest 127 → 169, 4 갭 발견 → v2 반영)
  - `ui-assistant-initial.md`: 2차 E2E 진행 중 + 2 false positive 발견/수정 기록
  - `README.md`: 인덱스 + 형식 가이드 + 다음 계획
- **LESSON-021 신규** — ui-assistant 2차 E2E 중 발견. "태스크 `done` = toolchain 전체 통과
  (test + lint + **type**)". 단위 테스트만 통과시키면 `done` 으로 mark 되는 흐름 때문에
  pyright 15 errors + eslint config 누락이 Phase 1 끝까지 숨어 있었음. 실제 `/ha-verify`
  돌려서 발견 → 수정 → 최초 verify_history 갱신.
- **LESSON-021 구현** — `skills/ha-build/run.py::_run_toolchain_gate` 신규. `--status done`
  마킹 전 프로파일 toolchain (test + lint + type) 강제 실행. 실패 시 BLOCK + done 거부.
  `--skip-toolchain` 으로 문서/설계 태스크 opt-out. 회귀 테스트 5개 추가.
- **B3 design doc 재구조화** — `docs/harness-v2-design.md` 앞부분에 "이 문서 읽는 법"
  내비게이션 추가. 다른 문서 (README/ARCHITECTURE/ADR/E2E reports/benchmarks/lessons) 우선
  권장. D1-D6 결정 테이블을 ADR cross-reference 로 교체.

### Added — Phase 4b 후속
- **`Orchestra.materialize_skeleton_v2` + `run_pipeline_with_phases(profile_ids=...)`** —
  Orchestra backend 가 `/ha-*` 스킬 경로와 동일한 "profile → empty skeleton → section_id
  merge" 계약을 공유. legacy `materialize_skeleton` (raw concat) 은 `profile_ids`
  미지정 시 back-compat 경로로 유지.
- **`pyright` dev 의존성 + 자가검증 필수 항목**. `src/` 14개 pre-existing 타입 에러
  전부 정리 (0 errors 달성). `CLAUDE.md` 에 `uv run pyright src/` 추가.

### Added — 비교 실험
- **`scripts/gate_benchmark.py` + `docs/benchmarks/gate-coverage.md`** — 9개 품질
  게이트 중 정규식/AST 기반 **7개** × 35 fixtures 커버리지 벤치마크. positive/negative
  fixture 기반 TP/TN/FP/FN
  → **precision 100% / recall 100% / accuracy 100%**. 초기 2 fixture 실패가 게이트 정책
  경계 재확인 + LESSON-018 dead 상수 정규식이 walrus operator 미커버 발견 (미래 개선
  후보). CI 통합 가능 (`exit 1` on miss/false-alarm).
- **`docs/benchmarks/dogfooding-catches.md`** — 21개 LESSON ↔ 원천 프로젝트 (Personal
  Jira / HabitFlow / 금칙어게임 / code-hijack / ui-assistant) ↔ 현재 감지 게이트 매핑.
  LESSON-013/018/021 이 단순 기록에서 **자동 감지 게이트**로 올라간 흐름을 추적.
  plain Claude 와의 **구조적 차이** 정성 비교 포함.

### Added — 공개 준비
- **`README.md` 영어 버전** 신규 + 기존 한국어는 `README.ko.md` 로 이전. 양쪽 상단에
  언어 토글 배너. 영어 README 에 shields.io 배지 6종 (tests / pyright / ruff /
  gate-coverage / python / license) + Tech stack 의 latency summary 추가.
- **커뮤니티 표준 파일** — `LICENSE` (MIT, copyright 2026 reasonableplan),
  `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1 축약), `SECURITY.md` (취약점
  보고 프로세스 + 응답 SLA critical 7d / high 30d + scope).
- **GitHub 템플릿** — `.github/ISSUE_TEMPLATE/{bug,feature,profile_request}.md`
  3종 + `.github/pull_request_template.md` (CONTRIBUTING PR 체크리스트 재사용,
  pyright / gate_benchmark / harness validate 항목 포함).
- **`examples/python-cli-hello/`** — 최소 재현 가능한 예시 프로젝트 (pyproject.toml
  + docs/harness-plan.md + docs/skeleton.md + README). 신규 사용자가 `/ha-init`
  결과를 실행 전에 미리 볼 수 있음. Korean skeleton heading 관련 로컬라이제이션
  메모 포함.

### Changed — 공개 준비
- **`.github/workflows/ci.yml` 전면 재작성** — 기존은 postgres/alembic 참조하는
  stale template (이 프로젝트엔 DB 없음). 새 workflow: ruff lint + format check +
  pyright + pytest + harness validate + gate_benchmark + install-snapshot.
- **15 파일 주석/docstring 영어화** (orchestrator/* + scripts/*). `pipeline_runner`
  의 에이전트 프롬프트 · `print()` · `input()` 한국어 UX 메시지, `output_parser`
  의 한글 regex 파싱 패턴, `security_hooks` 의 Finding 메시지 문자열은 의도적 유지.
  변경된 테스트 5개에서 에러 메시지 matcher 동기화.

### Removed — **BREAKING** (Phase 4a + 4b)

**Phase 4a** (스킬/문서 정리):
- **`/my-*` 스킬 12종 전체 삭제** — `~/.claude/skills/my-db-design/`, `my-architect/`,
  `my-designer/`, `my-skeleton-check/`, `my-tasks/`, `my-db/`, `my-api/`, `my-ui/`,
  `my-logic/`, `my-type-check/`, `my-review/`, `my-lessons/`. v1 의 4-스택 하드코딩
  (fastapi/nextjs/react-native/electron) 파이프라인이 v2 프로파일 기반 (`/ha-*` 7종) 으로
  완전 대체됨. [ADR-005](docs/decisions/005-ha-skills-cut-over.md) 참조.
- **README `v1 (레거시)` 섹션 제거** — 신규 사용자의 혼란 제거.

**Phase 4b** (backend production 레거시 코드 제거):
- **`backend/src/orchestrator/context.py`** — `SECTION_MAP` (번호 기반 에이전트 매핑),
  `extract_section` (번호 기반 추출), `fill_skeleton_template` (구 템플릿 치환) 3개 삭제.
- **`build_context` 시그니처** — `use_section_ids: bool = False` 파라미터 제거.
  기본 동작이 섹션 ID 기반 (`AGENT_SECTIONS_BY_ID` + `extract_section_by_id`) 으로 고정.
- **`orchestrate.py::materialize_skeleton`** — `skeleton_template.md` 부재 전제
  (commit `595ef88` 에서 삭제됨) 로 template 치환 분기 제거. 추출된 섹션을 바로 concat.
- **`orchestrate.py::_extract_allowed_endpoints`** — 레거시 섹션 번호 7 폴백 제거.
  `interface.http` ID 기반 추출만 유지.
- **`runner.py`** — `build_context(..., use_section_ids=True)` 호출에서 kwarg 제거.
- **테스트 수 흐름**: 365 → 347 (v1 테스트 18개 삭제) → 357 (v2 테스트 10개 추가).
  최종 backend pytest **357**.

**마이그레이션 가이드**: 기존 HabitFlow / 금칙어게임 / Personal Jira 는 이미 완료 상태라
영향 없음. 새 프로젝트는 전부 `/ha-init → /ha-design → /ha-plan → /ha-build → /ha-verify
→ /ha-review` 흐름 사용. `/my-lessons` 회고 흐름은 `/ha-deepinit` + `/ha-review` 조합으로 대체.

### Fixed — 포트폴리오 공개 직전 종합 점검
- **`Orchestra.verify` 가 프로파일 whitelist 무시 버그** — `_get_security_hooks()` 신설.
  첫 감지된 프로파일로 `SecurityHooks.from_profile()` 을 지연 생성/캐싱. 이전에는 빈
  기본 whitelist 만 적용돼 프로파일 선언이 무의미했음.
- **`pipeline_runner.run(profile_ids=...)` v2 경로 추가** — 기존 인터랙티브 CLI 러너가
  legacy `materialize_skeleton` 만 호출해 v2 profile 기반 구조가 적용되지 않던 문제.
  `--profile <id>` CLI 옵션 복수 지정 가능.
- **`runner.py::run_many` 의 `CancelledError` 취소 전파 회복** — `isinstance(r, BaseException)`
  가 `CancelledError` 를 `RunResult(success=False)` 로 둔갑시켜 graceful shutdown 시
  취소 신호가 소실되던 문제. `Exception` 만 캐치 + `BaseException` 은 재발생으로 수정.

---

## [0.3.0] — 2026-04-18 — "포트폴리오 정점 업그레이드"

### Added — 신규 품질 게이트 2개

- **`harness integrity` 서브커맨드** — `~/.claude/harness/bin/harness` 에 신규. skeleton.md 의 ` ```filesystem ` 블록 선언 경로 ↔ 실재 FS 일치 + 미치환 placeholder (`<pkg>`, `<cmd_a>` 등) 감지. `/ha-verify` 가 toolchain 실행 전에 호출. (A5)
- **테스트 분포 체크** — `/ha-review` 가 프로파일별 src ↔ 테스트 파일 대응 집계. src 모듈 있는데 테스트 0개 → BLOCK, 편차 10x 이상 → WARN. Python (AST `def test_*`) + JS/TS (`describe/it/test` 정규식) 지원. 모노레포 대응. (A6)

### Added — 신규 LESSON 3개

- **LESSON-018** 상수 정의 범위 vs 실제 사용 범위 불일치 (dead 상수) — ai-slop 정규식 자동 감지 통합 (7번째 패턴)
- **LESSON-019** 외부 명령 stderr → 사용자 친화 메시지 번역
- **LESSON-020** 진행 표시 `[N/M]` 은 실제 작동해야 — 껍데기 금지

### Added — 설치 체계 신설

- **`install.sh` (Unix/WSL/Git Bash) + `install.ps1` (Windows PowerShell)** — 단일 명령으로 `harness/` + `skills/ha-*` + `skills/_ha_shared` 를 `~/.claude/` 로 복사. (B8)
- **SHA256 manifest** (`~/.claude/harness/.install-manifest.json`) — 재실행 시 diff 감지 (added/modified/unchanged/removed), 투명한 덮어쓰기 확인.
- **`--force` / `--dry-run`** 옵션 + `CLAUDE_HOME=/custom ./install.sh` env override.
- **`install.ps1` UTF-8 BOM** — Windows PS 5.1 의 cp949 기본값과 호환.
- **non-interactive 가드** (`install.ps1`) — CI / stdin redirect 환경에서 `Read-Host` hang 방지.
- **post-install env 안내** — `HARNESS_AI_HOME` 설정 명령 출력.

### Added — 레포 구조 (소스 이관)

- **`harness/` 루트 디렉토리 신설** — 이전엔 `~/.claude/harness/` 에만 존재. 29 파일 (profiles × 6, templates/skeleton × 20, bin × 2).
- **`skills/` 루트 디렉토리 신설** — ha-init / ha-design / ha-plan / ha-build / ha-verify / ha-review / ha-deepinit 7개 + `_ha_shared` 공용 유틸. 15 파일.
- 소스 이관으로 git 이력에 모든 스킬 변경이 추적됨.

### Added — 회귀 방지 테스트 (+41)

- `backend/tests/orchestrator/test_skeleton_assembler.py` +9 — find_placeholders 단위 테스트 (HTML 태그 제외 / 백틱 인라인 제외 / 라인 번호 보존 등).
- `backend/tests/skills/test_harness_integrity.py` +9 — A5 게이트 회귀 방지.
- `backend/tests/skills/test_ha_review_distribution.py` +13 — A6 분포 게이트 회귀 (python/JS 양쪽 + monorepo).
- `tests/install/test_install_snapshot.sh` — B8 install 시나리오 12 assertion (fresh / re-run / source-modified / dry-run).

### Added — 포트폴리오 수준 문서

- **`docs/ARCHITECTURE.md` 신규** (406 lines) — 전체 구조 ASCII 다이어그램, 프로파일 시스템 설계 의도, skeleton 20 섹션 ID 규약, state machine, 스킬 ↔ 에이전트 매핑, 품질 게이트 8개 상세, 설계 결정 D1-D6 요약, 확장 방법.
- **`CONTRIBUTING.md` 신규** — 프로파일/LESSON/게이트/스킬 추가 가이드, PR 체크리스트, 커밋 메시지 컨벤션.
- **`CHANGELOG.md` 신규** (이 파일).

### Changed — 프로파일 강화

- **`_base.md` §10 "설정 중앙화" 신설** — "하드코딩 상수 3개 이상이면 중앙화" 공통 원칙 + 비밀값 env 전용. 기존 §10 은 §11 (2대 절대 원칙) 로 이동.
- **`python-cli.md`** — `core/config.py` 또는 `[tool.<name>]` 구체화 섹션 추가. `lessons_applied` 에 LESSON-010/012 외 018/019/020 추가.
- **`fastapi.md`** — `pydantic-settings BaseSettings` 구체화 섹션 + LESSON-018 안전 예시 (`(1.0, 2.0)` + `for delay in ...:` 소비 루프). `lessons_applied` 확장.

### Changed — 스킬 강화

- **`/ha-verify/SKILL.md`** — "1.5. skeleton 정합성 게이트" 단계 삽입 (toolchain 실행 전).
- **`/ha-plan/SKILL.md`** — "테스트 태스크 동반" 원칙 강화 (구현 1 = 테스트 최소 1, I/O 경계 2+).
- **`/ha-review/run.py`** — ai-slop 정규식 7번째 패턴 (LESSON-018 dead 상수) + `_check_test_distribution()` 함수 + 프로파일별 분리 집계.

### Changed — README 전면 재작성 (709 → 293 lines)

- **30초 사용법 섹션** 추가 — Hook + Install + 파이프라인 순차 사용 한눈에
- **파이프라인 ASCII 다이어그램**
- **핵심 개념 3개** — 프로파일 / Skeleton / Shared Lessons
- **비교 테이블** — Cursor / Copilot / Claude Code / aider 대비
- **품질 게이트 8개** 정리 + **에이전트 7개** 매핑
- **한계 + Roadmap** 명시
- **v1 레거시** (`/my-*` 12종) 섹션 축소

### Fixed

- **하드코딩된 개인 로컬 경로 제거** (CRITICAL) — `skills/_ha_shared/utils.py` 의 `Path("C:/Users/juwon/OneDrive/Desktop/agent")` fallback 을 `__file__` 기반 자동 탐지 + env 필수 에러로 전환. 공개 포트폴리오 가능 상태 확보.
- **harness CLI `_check_placeholders` 라인 번호 왜곡** (HIGH) — 코드 블록을 빈 문자열로 치환해 placeholder 보고 라인이 최대 20줄 밀리는 문제. `"\n" * count` 로 개행 보존.
- **placeholder false positive 2건** (2차 E2E 발견) — HTML/SVG 태그 85개 (`<div>`, `<pre>` 등) + 백틱 인라인 템플릿 예시 (`` `<pkg>` ``) 제외.
- **` ```filesystem ` 블록 WARN → opt-in** — 블록 없으면 silent pass. 모든 프로젝트에서 발생하던 noise 제거.
- **`install.sh` `__pycache__/ + *.pyc` 제외** — 런타임 캐시 복사 방지.
- **ruff pre-existing 경고** — `harness/bin/harness` F541 + SIM102, `ha-review/run.py` F541 + I001 정리.
- **README pytest 카운트** — 327 → 356 (+12 install).
- **테스트 카운트 정확성** — SIM300 Yoda condition + F401 unused import 정리.

### Internal — 검증 지표

- **backend pytest**: 327 → **359** (+32)
- **install snapshot**: 0 → **12** (bash assertion)
- **harness validate**: 27 files, 0 errors, 0 warnings
- **ruff**: all clean
- **ui-assistant 2차 E2E** (backend fastapi + frontend react-vite): 초기 4 errors → **0 errors, 0 warnings**

### Meta

- 1차 E2E (code-hijack, Python CLI) 학습 → v2 로 직접 반영 완료
- 2차 E2E (ui-assistant, fastapi + react-vite 모노레포) 실전 검증에서 false positive 2건 발견 → 즉시 수정
- `/plan-eng-review` 를 이 업그레이드 계획에 적용 → HIGH 1 + MEDIUM 4 + LOW 3 발견 → 수정 후 진행

**커밋 10개**:
- `9531f4c` docs: README + CLAUDE + TODOS + SETUP + design doc 업데이트 (Phase 3 반영)
- `caaebf9` docs(lessons): LESSON-018/019/020 추가 — code-hijack 1차 E2E 학습 반영
- `715f585` feat(skeleton): find_placeholders 유틸 추가 — A5 정합성 게이트 지원
- `d06c037` feat(install): B8 단일 명령 설치 + ~/.claude 소스 레포 이관
- `19e6a86` test: C — A5/A6/B8 회귀 방지 테스트 29 + 12
- `03f3b51` fix: 리뷰 후속 — 하드코딩 경로 제거 + CI 안전 + pycache 필터
- `1dc7c7e` docs: B1 README 전면 재작성 + B2 ARCHITECTURE.md 신규
- `273fdb5` fix(integrity): placeholder 정규식 false positive 2건 차단 — 2차 E2E 발견
- `e9ab925` fix(integrity): ```filesystem 블록을 opt-in 으로 전환

---

## [0.2.x] — 2026-04-02 ~ 04-16 — HarnessAI v2 재설계

### Added — v2 프로파일 시스템

- `~/.claude/harness/profiles/` 에 프로파일 5개 (fastapi, react-vite, python-cli, python-lib, claude-skill) + `_base.md` 공통 원칙 + `_registry.yaml` 감지 규칙.
- 20개 표준 skeleton 섹션 ID 체계 (번호 기반 → ID 기반 전환).
- `profile_loader.py` (감지 + 상속), `skeleton_assembler.py` (조각 조립), `plan_manager.py` (상태 전이).
- `docs/harness-plan.md` 단일 파일 + YAML frontmatter 상태 관리 (init → designed → planned → building → built → verified → reviewed → shipped).

### Added — /ha-* 스킬 7종

- `/ha-init` 스택 자동감지 + 인터뷰 → harness-plan.md + 빈 skeleton.md
- `/ha-design` Architect+Designer 역할 (협의 최대 3회)
- `/ha-plan` Orchestrator 역할 → tasks.md 생성
- `/ha-build` Coder 역할 [sonnet] + `--parallel` ultrawork 패턴
- `/ha-verify` 프로파일 toolchain (test/lint/type) [sonnet]
- `/ha-review` 보안 훅 6 + LESSON + ai-slop (7번째 훅) 종합 리뷰
- `/ha-deepinit` 기존 코드베이스 → hierarchical AGENTS.md

### Added — LESSON 시스템

- `backend/docs/shared-lessons.md` 에 LESSON-001 ~ LESSON-017 (17개).
- 프로파일의 `lessons_applied` 필드로 강제 적용 대상 지정.

### Added — 품질 게이트 (v2 기반)

- `SecurityHooks.from_profile()` — 프로파일 whitelist 동적 주입.
- ai-slop 감지 6패턴 (장황한 docstring, 의미 없는 try/except, TODO/FIXME, unused 함수, 임시 pass).

### Changed

- agents/\*/CLAUDE.md 27개 섹션 번호 → ID 참조 전환.
- `runner.py::build_context(use_section_ids=True)` 활성화.
- backend pytest: 248 → 327 (+79).

---

## [0.1.x] — 2026-03-16 ~ 04-01 — 초기 구현

### Added

- Director/Worker 구조 (후에 재설계로 폐기).
- 7개 에이전트 (Architect/Designer/Orchestrator/Backend Coder/Frontend Coder/Reviewer/QA).
- `/my-*` 스킬 12종 (fastapi/nextjs/react-native/electron 하드코딩).
- FastAPI + WebSocket 대시보드 (포트 3002).
- `agents.yaml` 설정 (provider, model, timeout, on_timeout).
- Claude CLI subprocess provider (향후 Gemini/local 교체 가능 구조).

---

**참고**:
- [README.md](README.md) — 사용자 관점 소개
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 시스템 구조 상세
- [CONTRIBUTING.md](CONTRIBUTING.md) — 기여 가이드
