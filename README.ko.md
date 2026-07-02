# HarnessAI

🌐 [English](README.md) · **한국어**

> *AI 에이전트가 짜되, 당신 규칙대로 짜게 하는 오케스트레이터.*

AI가 코드를 잘 짜는 건 알지만 **내 스타일대로 짜지는 않는다**. 기획 범위를 넘고, 허용 안 한 라이브러리를 쓰고, 에러 처리가 내 기준과 다르다. 직접 고치다 보면 결국 내가 다 짜는 거랑 같다.

HarnessAI 는 그 문제를 닫힌 루프로 푼다:

1. **계약서** (`skeleton.md` — 36개 표준 섹션, **사용자 6축 답변에 따라 자동 활성화**) 에 무엇을 만들지 먼저 선언
2. **11개 에이전트** (Architect · Designer · Orchestrator · Backend Coder · Frontend Coder · 4× mobile_coder (RN/Flutter/Android/iOS) · Reviewer · QA) 가 선언대로 구현 — Orchestrator 가 스택 프로파일에 따라 적합한 coder 에게 라우팅
3. **10개 품질 게이트** 가 계약 위반을 자동 차단 — 보안 훅 7 + ai-slop + 테스트 분포 + skeleton 정합성

AI 를 대체하는 게 아니라 **통제하는** 도구다.

---

## 🎯 실제로 무엇을 잡아내는가

일반 Claude 가 짜는 코드 — 테스트 통과, 린트 통과, 정상 동작:

```python
_BACKOFF_SECONDS = (1.0, 2.0, 4.0, 8.0)   # 4개 백오프 단계 선언
max_retries = 2
for i in range(max_retries):              # 그런데 2개만 사용
    time.sleep(_BACKOFF_SECONDS[i])
```

상수는 4개를 선언했는데 루프는 2개만 읽는다. 어떤 테스트도 못 잡는 dead code — 프로그램이 정상 동작하기 때문. 실제 사례 — dogfooding 로그의 [LESSON-018](docs/benchmarks/dogfooding-catches.md).

`/ha-review` 의 `ai-slop` 훅(보안훅 7 + ai-slop = 8번째 게이트) 이 잡아낸다:

```json
{
  "hook": "ai-slop",
  "severity": "WARN",
  "message": "dead 상수 의심 (LESSON-018) — 상수 정의 범위 vs 실제 사용 범위 확인",
  "snippet": "_BACKOFF_SECONDS = (1.0, 2.0, 4.0, 8.0)\n+max_retries = 2"
}
```

LLM 이 자주 만드는데 사람 리뷰에서 놓치는 종류의 실수. **35개 fixture** 에서 벤치마크 측정 7개 게이트가 **precision 100% / recall 100%** — [gate-coverage.md](docs/benchmarks/gate-coverage.md).

---

## 🎯 실제로 어떻게 맞춤되는가

![데모 — 5초 재현](docs/demo-adapt.gif)

같은 `python-cli` 프로파일, 두 가지 인터뷰 답변 → 다른 skeleton.

**기본선 — `data_sensitivity=none / lifecycle=poc / availability=casual` → 14 섹션**

```
overview · stack · errors · interface.cli · core.logic ·
configuration · environments · persistence · data_model · external_deps ·
integrations · requirements · tasks · notes
```

**상향 — `data_sensitivity=pii / lifecycle=mvp / availability=standard` → 18 섹션** (기본선 14 **+** 아래 4):

| + 섹션           | `required_when` 룰                                                  | 이 답변이 활성화한 이유                          |
|------------------|---------------------------------------------------------------------|--------------------------------------------------|
| `audit_log`      | `data_sensitivity in [pii, payment]`                                 | 민감 데이터 → compliance 로그                    |
| `threat_model`   | `data_sensitivity in [pii, payment] or availability == high`         | 민감 데이터 → STRIDE/OWASP                       |
| `ci_cd`          | `lifecycle in [mvp, ga]`                                             | mvp 이상 → 파이프라인 / 롤백                     |
| `test_strategy`  | `lifecycle in [mvp, ga]`                                             | mvp 이상 → 테스트 피라미드 / 컨트랙트 테스트     |

6축 (`user_scale` / `data_sensitivity` / `team_size` / `availability` / `monetization` / `lifecycle`) 은 `/ha-init` 가 받음. 각 fragment 의 표현식은 [`scale_expression.py`](backend/src/orchestrator/scale_expression.py) 가 파싱 → 6축에 평가 → `ProfileLoader.compute_active_sections` 가 활성 섹션 목록 반환. 룰은 `harness/templates/skeleton/*.md` frontmatter 에 — 완전 투명, 바꾸면 로더가 즉시 반영.

**재현** (clean clone 에서, 에이전트 호출 없이):

```bash
cd backend && uv run python ../scripts/show_adapt_diff.py
# A  pii + mvp + standard  ->  18 sections
# B  none + poc + casual   ->  14 sections
# diff (A only)            ->  ['audit_log', 'ci_cd', 'test_strategy', 'threat_model']
```

---

## 🚀 30초 사용법

```bash
git clone https://github.com/reasonableplan/harnessai.git
cd harnessai
./install.sh                          # Windows: .\install.ps1
export HARNESS_AI_HOME="$(pwd)"       # (설치 스크립트가 안내)
```

새 Claude Code 세션에서:

```
/ha-init     # 스택 감지 + 인터뷰 → harness-plan.md + skeleton.md
/ha-design   # Architect+Designer 가 skeleton 섹션 채움
/ha-plan     # Orchestrator 가 tasks.md 로 분해
/ha-build T-001          # 태스크별 구현 [sonnet]
/ha-verify   # toolchain 실행 + skeleton 정합성 게이트 [sonnet]
/ha-review   # 보안훅 + LESSON + ai-slop + 테스트 분포 종합 리뷰
/ha-smoke    # 런타임 기동 검증 — 앱이 실제로 뜨는지 (advisory)
```

또는 드라이버에게 전체 파이프라인을 맡긴다:

```
/ha-run      # 원커맨드 드라이버 — 상태기계 기준 다음 스킬 자동 호출,
             # HITL 지점(인터뷰·smoke 실패 판단·배포 확인)에서만 정지
```

> 세부: [ARCHITECTURE.ko.md](docs/ARCHITECTURE.ko.md) · [SETUP.md](SETUP.md)

---

## 🏗 파이프라인

```
               ┌─ profile 감지 (~/.claude/harness/profiles/) ────┐
               │                                                 │
  /ha-init ───▶│ harness-plan.md  +  skeleton.md (빈 템플릿)      │
               └─────────────────────────┬───────────────────────┘
                                         ▼
  /ha-design ─────▶ Architect + Designer (협의 최대 3회) ─▶ skeleton 채움
                                         ▼
  /ha-plan   ─────▶ Orchestrator ─▶ tasks.md (의존성 그래프)
                                         ▼
  /ha-build  ─────▶ Backend/Frontend Coder ─▶ 구현 파일
    │                                 [--task T-001,T-002  ← parallel]
    ▼
  /ha-verify ─────▶ [1] harness integrity (skeleton ↔ 실재 FS)
                    [2] profile toolchain (pytest/ruff/pyright)
                                         ▼
  /ha-review ─────▶ 보안훅 7 + LESSON 31 + ai-slop 7 + 테스트 분포
                                         ▼
  /ha-smoke  ─────▶ 런타임 기동 probe (exit 0 / URL readiness) — advisory
                                         ▼
                               APPROVE / REJECT → /ship
```

각 단계 앞뒤에 gstack 스킬 연계 가능 (`/office-hours`, `/plan-eng-review`, `/review`, `/qa`, `/ship`, `/retro`).

---

## 🙋 Human-In-The-Loop Gate (v0.10.0+)

페르소나 / 사용자 여정 / 화면 시안 — AI 가 추측으로 채우면 밋밋한 결과가 나오는 3 영역. v0.10.0 은 이 섹션을 사용자 인터뷰로만 채우도록 강제한다.

- `skeleton.md` 에 `<!-- HUMAN-LOCKED:<section_id> -->` 마커 — PreToolUse hook (`~/.claude/harness/bin/check_locked.py`) 이 LOCKED 영역 Edit/Write 를 차단
- `/ha-design` 이 LOCKED 섹션마다 AI 후보 5 개 제시 → `AskUserQuestion` → 사용자 선택 → 섹션 채움
- `/ha-build` 진입 시 `harness-plan.md` frontmatter 의 `frozen_status="frozen"` 필수
- 설계 변경은 `/ha-redesign` 경유 (audit 기록 + mutation propagation)

```bash
# 기존 v0.9.x 프로젝트 마이그레이션
python ~/.claude/harness/bin/harness migrate-v10 docs/harness-plan.md

# /ha-design 으로 HITL 인터뷰 + freeze
/ha-design

# 정상 흐름
/ha-build T-001

# 개발/CI 용 escape hatch (사용자 책임)
/ha-build --skip-frozen-gate
```

---

## 🎯 핵심 개념

### 1. 프로파일 — 스택별 규칙 선언

`~/.claude/harness/profiles/<stack>.md` 한 파일에 스택 하나의 모든 규칙을 담는다:
- **감지 규칙** (어떤 파일 있으면 이 스택인지)
- **컴포넌트** (필수/선택)
- **skeleton_sections** (어느 섹션 포함)
- **toolchain** (test/lint/type 명령)
- **whitelist** (허용 의존성)
- **lessons_applied** (강제 적용 LESSON)

기본 12개 스택 제공: `fastapi` · `nestjs` · `nextjs` · `react-vite` · `electron` · `python-cli` · `python-lib` · `claude-skill` · `react-native-expo` · `flutter` · `android-kotlin` · `ios-swift`. 새 스택은 파일 추가만으로 확장.

### 2. Skeleton — 프로젝트 계약서

36개 표준 섹션 ID 중 프로파일이 요구하는 것 + **사용자 6축 답변** 으로 활성 결정 (모바일 프로파일은 `has.*` atom 으로 `mobile.*` 섹션 자동 활성):

```
overview · requirements · stack · configuration · environments · errors · auth ·
persistence · integrations · interface.{http,cli,ipc,sdk} ·
view.{screens,components} · state.flow · core.logic ·
observability · deployment · error_ux · tasks · notes ·
data_model · threat_model · audit_log · slo · runbook ·
test_strategy · user_journey · authorization_matrix · ci_cd · external_deps ·
rate_limiting · mobile.{navigation,build_config,lifecycle}
```

마지막 13개 (data_model … rate_limiting) 는 6축에 대해 평가되는 `required_when` 표현식으로 활성 — 아래 [실제로 어떻게 맞춤되는가](#-실제로-어떻게-맞춤되는가) 참조. 3개 `mobile.*` 섹션은 모바일 프로파일 선언 (`has.navigation` / `has.build_config` / `has.lifecycle` atom) 으로 활성.

섹션 내용이 **계약**. /ha-verify 가 `\`\`\`filesystem` 선언 ↔ 실재 FS 일치 검증, 플레이스홀더 (`<pkg>`, `<cmd_a>`) 미치환 잔존 차단.

### 3. Shared Lessons — 집단 기억

`backend/docs/shared-lessons.md` 에 과거 28개 실수 패턴. 한 번 발생한 버그는 시스템에 기록 → 모든 미래 `/ha-review` 가 참조 → 반복 방지.

예시:
- LESSON-001: FastAPI Query params 반드시 snake_case
- LESSON-013: 프론트엔드 테스트 전략 사전 정의 필수
- LESSON-018: 상수 정의 길이 ≤ 실제 소비 범위 (dead 상수)
- LESSON-020: 진행 표시 `[N/M]` 은 실제 작동해야
- LESSON-021: 태스크 `done` = toolchain 전체 통과 (test + lint + type)

---

## 🆚 비교

| | HarnessAI | Cursor / Copilot | Claude Code (plain) | aider |
|---|---|---|---|---|
| 범위 | 프로젝트 전체 | 파일/함수 단위 | 대화 기반 | diff 기반 |
| 규칙 강제 | **프로파일 + 게이트 (BLOCK 17 + advisory 14)** | .cursorrules (선언만) | CLAUDE.md (선언만) | 커밋 스타일만 |
| 실수 축적 | **LESSON 37** (자동 감지 + 리뷰어 참조) | ❌ | ❌ | ❌ |
| 스택 자동감지 | **12개 기본 + 확장 가능 (web · desktop · CLI · lib · 4 mobile)** | ❌ | ❌ | ❌ |
| 병렬 구현 | **/ha-build --task T-1,T-2** | ❌ | ❌ | ❌ |
| 설계-구현 계약 | **skeleton.md + integrity 게이트** | ❌ | ❌ | ❌ |

**HarnessAI 가 어울리는 곳**: 여러 개 중소 프로젝트를 같은 품질로 양산. 반복하는 실수를 시스템이 기억하기를 원할 때.

**안 어울리는 곳**: 1회성 스크립트, 탐색적 프로토타입, 이미 코드가 수만 줄인 레거시 (deepinit 필요).

---

## 📦 설치

```bash
# Unix / WSL / macOS / Git Bash
./install.sh

# Windows PowerShell
.\install.ps1
```

동작:
- `harness/` + `skills/ha-*` + `skills/_ha_shared` → `~/.claude/` 로 복사
- `~/.claude/harness/.install-manifest.json` 에 SHA256 기록 (재실행 시 diff 감지)
- `--force` / `--dry-run` 지원
- `CLAUDE_HOME=/custom/path ./install.sh` 로 커스텀 타겟

**환경 변수**: 설치 후 `HARNESS_AI_HOME` 을 이 레포 절대 경로로. 스크립트가 끝에 안내한다.

---

## 🧪 품질 게이트 (BLOCK 17 + advisory 14)

| 게이트 | 위치 | 역할 |
|---|---|---|
| secret-filter | `security_hooks.py` | 토큰/키/DB 연결 문자열 하드코딩 감지 |
| command-guard | ` " ` | `rm -rf`, `eval`, `DROP TABLE` 등 위험 명령 차단 |
| db-guard | ` " ` | raw SQL, f-string SQL, WHERE 없는 DELETE/UPDATE |
| dependency-check | ` " ` | 허용 외 의존성 차단 |
| code-quality | ` " ` | 빈 `except:`, `print` 디버깅, `# type: ignore` 남용 |
| contract-validator | ` " ` | skeleton `interface.http` 외 엔드포인트 차단 |
| **auth-guard** | ` " ` | JWT type+ver claim 누락, localStorage 토큰 저장, logout no-op, MAX()+1 race (LESSON-022~027) |
| **ai-slop** (8번째) | `ha-review/run.py` | 정규식 6패턴 — 장황한 docstring, 껍데기 try/except, dead 상수(LESSON-018), TODO/FIXME, unused 함수, 임시 pass |
| **테스트 분포** | ` " ` | src 모듈 대비 테스트 편중 감지 (BLOCK: 0개, WARN: 10x 편차) |
| **skeleton 정합성** | `harness integrity` | 선언 경로 ↔ 실재 + 플레이스홀더 검증 |
| **file_structure drift** | `ha-build` (advisory) | uncommitted FS 변경 vs skeleton 선언 경로 편차 감지 (WARN) |

---

## 🎭 에이전트

| 역할 | 담당 |
|---|---|
| Architect | skeleton 의 DB/API/인증/상태흐름 + 모바일 build_config/lifecycle 설계 |
| Designer | UI/UX/컴포넌트 트리/상태관리 + 모바일 navigation UX/view.screens 설계 |
| Orchestrator | 태스크 분해, 의존성 그래프, Phase 관리, 스택 프로파일별 coder 라우팅 |
| Backend Coder | Python/FastAPI/CLI 구현 |
| Frontend Coder | React/TS 웹 구현 (web only — 모바일은 mobile_coder_* 에 위임) |
| mobile_coder_rn | React Native + Expo (Expo Router · Zustand · NativeWind) |
| mobile_coder_flutter | Flutter + Dart (Riverpod · go_router · drift · Material3) |
| mobile_coder_android | Android Kotlin + Jetpack Compose (StateFlow · Room · Retrofit · Hilt) |
| mobile_coder_ios | iOS Swift + SwiftUI (`@Observable` · NavigationStack · CoreData/SwiftData · Keychain) |
| Reviewer | 보안 훅 + LESSON + convention 종합 리뷰 |
| QA | 통합 테스트 시나리오 검증 |

각 에이전트의 규칙은 `backend/agents/<role>/CLAUDE.md` 에서 수정 가능.

---

## ⚠️ 현재 한계

- **Windows 우선 테스트** — Linux/macOS 지원은 설계됐으나 CI 매트릭스 미정
- **LLM 자동 학습 X** — 새 LESSON 은 수동 추가 (자동 학습은 TODOS.md)
- **iOS native** — `xcodebuild` 빌드 검증은 Windows 호스트에서 불가능. macOS GitHub Actions CI 추가 예정 (Phase 7)
- **gstack 의존** — 일부 게이트는 gstack 스킬 연계 전제 (독립 실행 가능하나 full power 는 gstack 있을 때)

---

## 🗺 Roadmap

**Phase 1-4 (완료)**: 프로파일 시스템 · 7개 /ha-스킬 · 28 LESSONs · 10개 품질 게이트 · 단일 명령 설치 · /my-\* 스킬 12종 삭제 · v1 레거시 코드 (SECTION_MAP/extract_section/fill_skeleton_template) 제거 · Orchestra v2 wiring

**Phase 5 — v0.5.0 (완료, 2026-05-02)**: auto-fit skeleton — 6축 인터뷰 답변 (`user_scale` / `data_sensitivity` / `team_size` / `availability` / `monetization` / `lifecycle`) 으로 fragment 자동 활성. 30개 표준 섹션, 커스텀 AST + parser + evaluator.

**Phase 6 — v0.6.0 (완료, 2026-05-07)**: **모바일 확장**. 4개 신규 프로파일 (`react-native-expo` · `flutter` · `android-kotlin` · `ios-swift`) + 4개 mobile_coder 에이전트 (Pydantic + 시스템 프롬프트 + dispatch 라우팅) + 3개 mobile.* fragment (`navigation` / `build_config` / `lifecycle`) + harness-global guidelines 외부 사용자 자동 로딩 + `HARNESS_AI_HOME` fallback. iOS native 는 Windows 호스트 친화적 (SwiftLint + `swift build` dry-run; 전체 `xcodebuild` 는 macOS CI 에서).

**Phase 7 — v0.7.0 (완료, 2026-05-11)**: **웹 + 데스크톱 프로파일** — `nextjs` (App Router · Server Actions · better-auth · Drizzle) · `nestjs` (TypeORM · class-validator · Passport JWT · GlobalExceptionFilter) · `electron` (Context Isolation · preload IPC · electron-updater · 코드 서명). 신규 skeleton fragment 3개 (`environments` / `error_ux` / `rate_limiting`). 상태 머신 버그 수정 (`ha-review` / `ha-verify`). 크로스 플랫폼 toolchain 게이트 테스트.

**Phase 8 — v0.8.0 (완료, 2026-05-11)**: **설계 결함 대규모 수정**. 인프라 모듈 7개 신설 (`capabilities` / `consistency` / `lessons` / `agent_matching` / `tasks_schema` / `skeleton_hash` / `skeleton_stale`), `HarnessPlan` frontmatter 필드 4개 추가, `harness migrate-plan` CLI, 회귀 테스트 +220 (541 → 761). 챙겼니 (RN/Expo) dogfooding 으로 발견한 mobile-only false-positive/negative, fractional task ID, 에이전트 라우팅 오류 수정.

**Phase 9 — v0.9.x (완료, 2026-05-12)**: **dogfood 강화 + audit cleanup**.
- v0.9.0: 챙겼니 dogfood 결함 11건 수정 — `harness migrate-skeleton-hash` + `harness analyze-failure` CLI, RN bun test 수정, ha-review/ha-verify 기록 게이트, ha-build 상태 머신 + atomic 쓰기, file_structure drift audit 추가. 회귀 +105 (761 → 866).
- v0.9.1: `harness graph` CLI 보충 구현 — tasks.md → Mermaid 의존성 그래프 (v0.8.0 에 구현됐다고 기록됐으나 실제 미구현). 회귀 +4 (866 → 870).
- v0.9.2: mirror sync (repo ↔ `~/.claude` 5파일 drift 회복), profile 보강 (LESSON-STYLE-001, whitelist 항목 추가), 명세-코드 격차 해소 (G1 ha-deepinit augment-plan · G2 ha-verify integrity 자동 실행 · G3 ha-build git WARN). 회귀 +23 (870 → 893).

**Phase 10 — v0.10.0 (완료, 2026-05-15)**: **HITL Gate**. Human-locked 섹션 (`requirements` / `user_journey` / `view.screens`) PreToolUse hook 강제. `PlanManager.freeze()` one-way gate. `/ha-design` HITL 인터뷰 (AI 후보 5 개 → 사용자 선택). `/ha-build` frozen-status 진입 게이트. `/ha-review extract-lesson` Pending Lessons 자동 추가. `/ha-log` 마이크로 스킬 (worklog append + subprocess 자동). `harness migrate-v10` CLI. ChatDev / aider / CrewAI 격차 해소. 신규 테스트 +39 (893 → 939).

**Phase 11 — v0.11.0 (완료, 2026-06-10)**: **Design Integrity & Intent Capture**. 전체 시스템 리뷰 (프롬프트 감사 + 코드/아키텍처 리뷰 에이전트 병렬) → ID-키잉 consistency checker, fail-open 5곳 수정, skeleton drift 게이트, 섹션별 hash 결정론 rebuild, 역방향 contract 검증, 루프 탈출 가드, `/ha-ship` 라스트마일. dogfood 피드백 ("작동은 하는데 의도와 다르게") 대응 의도 포착 배치: Intent Echo · 기능별 Given/When/Then 수용 기준 · 행동 워크스루 게이트 · 모호어 스캔 · 적대적 자가비판. 에이전트 9종 시니어 핸드오프 노트. 3중 제목 동기 테스트 (첫 실행에서 실 drift 2건 적발). `GATES.md` 게이트 전수표. 후반 추가: canonical 섹션 삽입 (user_journey dangling 해소), 가짜 FAIL 가드 (profile cwd 오매칭), `harness validate` 0/0, 약모델 프롬프트 다이어트 (체크리스트→인변량 ≤7, ha-design 519→391줄+진행표), LESSON 자동학습 루프 첫 완주 (LESSON-029). 신규 테스트 +55 (939 → 994).

**Phase 12 — v0.12.0 (완료, 2026-06-12)**: **런타임 스모크 게이트 + 디폴트 guidelines**. `/ha-smoke` — 검증 사다리 최상단: test/lint/type 전부 통과해도 앱이 안 뜨는 산출물을 잡는다. exit 모드 (exit 0 = PASS) / URL readiness probe + 프로세스 트리 정리, `verify_history` step=`smoke` 기록 (advisory, 스키마 변경 0) + `toolchain.smoke` optional 프로파일 필드. untracked 파일 스캔 우회 봉합 — 방금 생성된 파일이 의사 diff 합성으로 `/ha-build` 보안 게이트 + `/ha-review` 스캔에 합류. cp949 디코딩 크래시 root fix (6지점). `electron` / `nextjs` / `nestjs` 디폴트 guidelines 11파일 (sosel dogfood 검증 kalpie 계열 규칙 역수출). ha-design `locked_section_status` 백포트 (미러 전수 해시 감사로 명세-코드 격차 적발). 신규 테스트 +23 (1015 → 1038).

**Phase 13 — v0.13.0 (완료, 2026-06-22)**: **Dogfood Harvest 2 — 런타임 L2 & 단계 정합성**. `/ha-smoke` 계층2: 기동 후 선언 `interface.http` GET 엔드포인트를 실제 타격해 "프로세스는 떠도 라우트 깨짐"(404 미등록 / 5xx 핸들러 크래시)을 잡는다. ha-plan→build→review→redesign 단계 정합성 수정: ha-plan 이 §태스크 sync 후 skeleton hash baseline refresh(거짓 drift WARN + 매 빌드 BLOCK 제거), `/ha-plan --replan`(redesign 후 재-plan), worklog 루트 우선(split-brain), `/ha-verify` cli_entrypoint 런타임 인코딩 스모크(CliRunner 가 못 잡는 cp949 `UnicodeEncodeError`), `/ha-build` in-progress 마킹 + 부분복구 + reviewed→building 회귀(Phase 2 iteration), `/ha-review` 빈 diff full-source 폴백(vacuous APPROVE 차단). LESSON-033~037 추출. Spec Kit 흡수 설계서(`docs/spec-kit-absorption-design.md` — 설계품질 게이트 + 멀티에이전트 Gemini/Copilot) 작성 후 구현: **A1** skeleton 품질 체크리스트(clarity / edge-case advisory, `/ha-design`), **A2** offline/NFR 위반 검사(cross-artifact critical) + `/ha-redesign` nfr_conflicts, **축A** `reenter_or_assert`(상태머신 재진입 일원화, #2/#9), **Track B** `harness scaffold` 멀티에이전트 파일 생성(claude / gemini / copilot 명령 + 컨텍스트 파일), **A4** `/ha-converge`(코드↔스펙 미구현 엔드포인트 회수 → tasks.md), **A5** `ha-build --resume`(다음 ready 태스크 자동 선택 — status 대기/in-progress + depends_on done). 신규 테스트 +174 (1038 → 1212).

**Phase 14 — v0.14.0 (완료, 2026-06-24)**: **Spec Kit 흡수 마감 — clarify 게이트 + 유실 작업 복구 + 상태 일관성**. **A3 `/ha-design clarify`**(Spec Kit `/clarify` 흡수) — A1 품질 findings(clarity/edge_case)를 사용자 질문 후보로 변환하는 read-only 서브커맨드 + SKILL.md §4.5 배선(AskUserQuestion ≤5 → skeleton 역기록): "vague 탐지(코드) → 질문(HITL) → 채움" 고리 완성. **`/ha-resync` 신규 스킬** — `applied` 이후 skeleton 손수정으로 stale 된 `skeleton_hash`/`section_hashes` 를 무조건 재계산·덮어쓰기(백업 + `--dry-run`); `/ha-build` BLOCK 을 추적(`/ha-redesign`)/재동기(`/ha-resync`)/일회우회(`--accept-skeleton-drift`) 3분기로 명확화. **#8 `/ha-review` vacuous-APPROVE 가드** — 빈 diff 로 approve 시 보안/슬롭 훅이 false-green 통과하던 갭 차단(`--allow-empty` 우회, 기존 #19 dependency-check 보존). **skipped 상태 일관성(사전 존재 결함)** — `/ha-build` 가 쓰는 `skipped` 가 schema `VALID_STATUSES` 에 없어 거부되고 내부 "resolved" 판정이 3집합으로 갈려 자기모순(skipped 의존성의 dependent 영구 블록) → `VALID_STATUSES += skipped` + 단일 `_RESOLVED_STATES` 통합 + 교차 일관성 테스트(record choices ⊆ VALID_STATUSES). Spec Kit 로드맵 P6(멀티에이전트 Tier2/3 + Track C 훅) 보류 — 주력 에이전트 미정 YAGNI. 미러 drift 정리. 신규 테스트 +24 (1212 → 1236).

**Phase 14.1 — v0.14.1 (완료, 2026-06-26)**: **스킬 감사 — ha-map 레포 편입 & 결함 일소**. `/ha-map`(skeleton→아키텍처 Mermaid 파생 뷰, 독립 보조)은 레포에 미러된 적도 테스트된 적도 없는 유일한 `ha-*` 스킬 → `skills/ha-map/` 로 편입 + 단위 테스트 9개. 14개 스킬 결함 일소(subprocess timeout/except, CRLF 정규식, broad except, `write_text` OSError, `json.load`) 결과 ha-map 이 *유일하게* 실결함 보유 — "테스트 스위트 = eval 하네스" 직접 실증. 수정: ha-map `subprocess.TimeoutExpired` 처리(mmdc 행이 렌더 루프 크래시 안 함), `` ```mermaid `` 펜스 정규식 CRLF 호환(Windows silent no-render), tmp 쓰기 `OSError` 가드; `_ha_shared/utils.py::project_root` git rev-parse 에 `timeout=10` + `TimeoutExpired` 처리. 신규 분석 문서 `backend/docs/eval-harness-positioning.md`(+`.en.md`) — 제안된 `/ha-eval` 보류 전 사이클 검토: 검증 사다리(pytest + GATES + `/ha-smoke`)가 이미 eval 하네스, 생태계 조사(Promptfoo/DeepEval/OpenAI skill-regression)상 "파이프라인 → 전체 레포" eval 단위는 어떤 도구도 미구현. 신규 테스트 +11 (1236 → 1247).

**Phase 14.2 — v0.14.2 (완료, 2026-07-02)**: **미러 재조정 — #15 strict placeholder 백포트**. 전체 점검(미러 2벌 정규화 해시 감사)에서 양방향 drift 18파일 발견: #15 작업 전체(strict placeholder 정규식 + 템플릿 백틱 규약)가 `~/.claude` 에만 존재 — `install -Force` 한 번이면 유실 — 반대로 모델 별칭 갱신은 실사용 미러 미전파(`python-cli.md` 가 `claude-sonnet-4-6` 잔존). strict 정규식 `<(?![A-Z])[^\W\d]\w*>` 을 `bin/harness` + `skeleton_assembler` 로 TDD 백포트(한글 `<본문>` 잔재 검출, TS 제네릭 `<T>`·공백 HITL 토큰 보호), 템플릿 13파일 백틱 통일, installer 재실행 → 정규화 drift 0. 신규 테스트 +5 (1252 → 1257).

**v1.0.0 백로그**:
- Live LESSONS 자동 학습 (ha-review 반복 패턴 → 후보 등록)
- multi-provider (Gemini/OpenAI backend)
- macOS GitHub Actions CI (iOS native `xcodebuild` test/build)
- 비용 추적 (에이전트별 토큰/달러 누적)
- Claude Code plugin manifest 로 배포
- 벡터 메모리 (CrewAI 방식) — 프로젝트별 LESSON embedding
- 실행 sandbox (OpenHands 방식) — 격리된 subprocess 환경
- `ha-smoke` 확장 — user_journey 브라우저 스모크 (GWT 수용 기준 체크리스트). 선언 엔드포인트 liveness 일괄 점검은 v0.13.0 출시; 기동 게이트 코어는 v0.12.0
- Spec Kit 흡수 — 설계품질 게이트 (skeleton 품질 checklist, analyze + constitution 권위, ha-converge) + 멀티에이전트 (Gemini/Copilot 어댑터). 설계: `docs/spec-kit-absorption-design.md`

---

## 🧱 Tech Stack

- **언어**: Python 3.12
- **서버**: FastAPI + WebSocket (포트 3002)
- **패키지**: uv
- **에이전트 실행**: Claude CLI subprocess (Gemini/로컬 LLM 교체 가능)
- **상태**: `docs/harness-plan.md` (YAML frontmatter) + `.orchestra/` JSON (DB 없음)
- **테스트**: pytest **1296개** backend + **12개** install 스냅샷 (회귀 0건)
- **타입 체크**: pyright **0 errors** (`src/` 전수)
- **게이트 커버리지 (자기 검증)**: 10개 게이트 중 정규식/AST 기반 7개를 35 fixtures (positive/negative) 로 측정 → **precision 100% / recall 100% / accuracy 100%**. 나머지 3개 — `auth-guard` 는 test_security_hooks 단위테스트, `test-distribution`·`skeleton-integrity` 는 filesystem fixture 로 별도 검증. 상세 한계/방법: [gate-coverage.md](docs/benchmarks/gate-coverage.md)
- **성능** (30 iter, LLM 제외): profile 감지 **~5 ms**, skeleton 조립 **<1 ms**, `harness validate` **~150 ms**, `harness integrity` **~104 ms**. [docs/benchmarks/](docs/benchmarks/)
- **v2 인프라**: `profile_loader`, `skeleton_assembler`, `plan_manager`, `harness` 검증 CLI

---

## 📂 디렉토리 구조

```
harness/              프로파일/템플릿/CLI 소스  ─┐
skills/               ha-* 스킬 + _ha_shared    ├─ install.sh → ~/.claude/
install.sh/ps1        설치 + manifest           ─┘

backend/
  agents/<role>/CLAUDE.md     11개 에이전트 시스템 프롬프트 (편집 가능)
  agents.yaml                 provider/model/timeout
  docs/shared-lessons.md      37 LESSONs
  src/orchestrator/           profile_loader / skeleton_assembler /
                              plan_manager / security_hooks / runner
  tests/                      1296 pytest + skills/ 회귀 방지

docs/
  ARCHITECTURE.md             시스템 구조 30분 이해
  harness-v2-design.md        상세 작업 로그
```

---

## 🛠 개발

```bash
cd backend
uv sync
uv run pytest tests/ --rootdir=.      # 1296 tests
uv run ruff check src/                 # 0 errors
uv run pyright src/                    # 0 errors (타입 체크)
uv run python -m src.main              # dashboard 서버 (포트 3002)
```

install 스크립트 회귀 테스트:
```bash
./tests/install/test_install_snapshot.sh   # 12 assertions
```

harness 스키마 검증:
```bash
python harness/bin/harness validate                 # 50 files, 0 errors
python harness/bin/harness integrity --project .    # skeleton ↔ FS 정합성
python harness/bin/harness graph docs/tasks.md      # tasks.md → Mermaid 의존성 그래프
python harness/bin/harness migrate-plan docs/harness-plan.md --apply  # legacy plan 마이그레이션
python harness/bin/harness migrate-skeleton-hash docs/harness-plan.md --apply  # skeleton 해시 마이그레이션
python harness/bin/harness analyze-failure          # 빌드 실패 원인 분류 + 권고
```

---

## 📚 문서

| 문서 | 내용 |
|---|---|
| [ARCHITECTURE.ko.md](docs/ARCHITECTURE.ko.md) | 시스템 구조 · 프로파일 · skeleton · 게이트 (**먼저 읽으세요**) |
| [docs/decisions/](docs/decisions/) | Architecture Decision Records (ADR 5개) |
| [docs/e2e-reports/](docs/e2e-reports/) | E2E 리포트 — dogfooding 증거 (code-hijack 완주, ui-assistant 진행 중) |
| [docs/benchmarks/](docs/benchmarks/) | 성능 측정 + **게이트 커버리지** (35 fixtures, 100%) + LESSON↔게이트 dogfooding 트레이싱 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 프로파일/LESSON/게이트/스킬 기여 가이드 |
| [CHANGELOG.md](CHANGELOG.md) | 버전별 변경 이력 |
| [SETUP.md](SETUP.md) | 처음부터 끝까지 설치/실행 가이드 |
| [TODOS.md](TODOS.md) | 향후 개선 항목 |
| [backend/docs/shared-lessons.md](backend/docs/shared-lessons.md) | 28개 과거 실수 패턴 |
| [CLAUDE.md](CLAUDE.md) | 구현 시 엄격 규칙 (현업 시니어 수준) |
| [SECURITY.md](SECURITY.md) | 취약점 보고 프로세스 |
| [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) | 커뮤니티 행동 규범 |
| [docs/harness-v2-design.md](docs/harness-v2-design.md) | v2 재설계 상세 작업 로그 |

---

## License

MIT

---

**포트폴리오 목표**: 현업 시니어 수준의 코드 품질 기준으로 포트폴리오의 정점을 찍기. Phase 1–10 완료 (v0.10.0 HITL gate), pytest 948 / ruff clean / pyright 0 / harness validate 50 files.
