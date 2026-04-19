# Changelog

HarnessAI 의 모든 주요 변경 사항. 형식은 [Keep a Changelog](https://keepachangelog.com/) 기준, 버전은 [SemVer](https://semver.org/) 준수 (pre-1.0 단계).

---

## [Unreleased]

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

### Changed
- (항목 추가되는대로)

### Fixed
- (항목 추가되는대로)

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
