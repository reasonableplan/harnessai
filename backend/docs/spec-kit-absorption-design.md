# Spec Kit 흡수 설계서 — 설계품질 게이트 + 멀티 에이전트

> 상태: **초안 (설계 단계)** · 작성 2026-06-22 · 코드 변경 없음
> 근거: GitHub Spec Kit 레포 전수 정독([github/spec-kit](https://github.com/github/spec-kit)) + HarnessAI `docs/GATES.md` 병렬 비교.
> 관련 메모리: 설계 게이트 3 vs 구현 게이트 15 불균형, 런타임 깨짐 최우선.

---

## 1. 배경 / 동기

`GATES.md` 전수 비교 결과, HarnessAI의 게이트는 **구현 단계 15+개 vs 설계 단계 4개**로 비대칭이다.
그나마 설계 게이트도 **"채워졌나(완전성)"** 위주(placeholder 카운트, LESSON 인용, HITL 인터뷰)이고
**"채운 내용이 좋은가(품질·명료성·일관성)"**를 보는 게이트가 없다.

Spec Kit은 정확히 이 빈칸을 4개 명령으로 메운다:
- `/checklist` — "영어로 쓴 스펙의 단위 테스트" (요구사항 품질 검증)
- `/clarify` — 미명세 영역에 최대 5개 타겟 질문 → 스펙에 역기록
- `/analyze` — 구현 직전 spec↔plan↔tasks read-only 일관성 분석 (constitution 충돌=CRITICAL)
- `/converge` — 빌드된 코드 ↔ 스펙 대조 → 미구현분을 태스크로 append

추가로 Spec Kit의 **멀티 에이전트(40+) 구조**(agent-agnostic 명령 본문 + per-agent 어댑터)는
사용자 요구사항(Copilot/Claude Code/Gemini 호환)의 직접 청사진이다.

## 2. 목표 / 비목표

**목표**
- 설계 단계에 **품질 게이트**를 추가해 "프롬프트는 정교한데 산출물 깨짐"의 *설계측 절반*을 빌드 전 차단.
- HarnessAI를 **에이전트 중립**으로 확장 (Claude Code 외 Gemini/Copilot).

**비목표 (이번 범위 아님)**
- Spec Kit의 bash+ps 이중 스크립트 / workflows 엔진 / bundles·preset 생태계 이식 (1인 프로젝트엔 과함, HarnessAI 단일 `run.py`가 우월).
- 런타임 검증 사다리(계층3~5) — 별도 트랙(이미 진행 중).

## 3. 관통 원칙

> **아이디어는 Spec Kit, 집행은 HarnessAI식 코드 게이트로.**

Spec Kit의 4종은 전부 "LLM이 마크다운 지시를 따르는" 신뢰 기반이다. HarnessAI는 같은 의도를
`run.py`의 exit code로 **기계 강제**할 수 있다(우회는 명시 플래그만) → Spec Kit보다 강한 버전.
따라서 흡수 시 **결정론 검사를 우선 구현**하고, LLM 판단이 불가피한 부분만 HITL/프롬프트로 남긴다.

---

## 4. Track A — 설계품질 게이트

### A1. `skeleton_checklist.py` — 스켈레톤 품질 게이트 (흡수: `/checklist`, **최우선**)

> **상태: ✅ v1 구현 (2026-06-22)** — clarity(미정량 표현) + edge_case(I/O 경계 실패경로 누락)
> 2종, advisory(Q3=B). `ha-design commit` 배선(`checklist_findings` 출력 + WARN). 테스트 22.
> 잔여: consistency(용어 미정의)·acceptance(수용기준)·#11(boundary mock-only)은 v2.

**위치**: `backend/src/orchestrator/skeleton_checklist.py` (형제: `consistency_checker.py`)
**호출 지점**: `skills/ha-design/run.py::cmd_commit` (commit 직전, placeholder 검사 다음)
**데이터 모델** (consistency_checker 의 Finding 형태 재사용):
```python
@dataclass(frozen=True)
class ChecklistFinding:
    severity: str       # "block" | "warn"
    category: str       # "clarity" | "completeness" | "consistency" | "edge_case" | "acceptance"
    section_id: str     # 섹션 이름 (번호 아님 — 프로파일마다 번호 다름, #4 교훈)
    message: str

def check_skeleton_quality(
    skeleton_text: str,
    active_components: list[Component],   # 프로파일에서 — required/section 매핑
) -> list[ChecklistFinding]: ...
```

**검사 규칙 (결정론 우선)**:
1. **clarity — 미정량 표현**: `빠른|적절한|충분한|간단한|효율적|많은|fast|simple|scalable` 등이
   인접 숫자/단위 없이 등장 → WARN. (예: "API는 빠르게 응답" → "목표 latency(ms) 명시")
2. **edge_case — 실패경로 누락**: I/O 경계 섹션(`interface.*`, `integrations`, `persistence`)에
   실패/에러/타임아웃/빈값 관련 문장이 0개 → WARN.
3. **acceptance — 수용기준 부재**: 각 `required` component 섹션에 측정가능한 "완료 기준" 문장 부재 → WARN.
4. **consistency — 용어 미정의**: 한 섹션이 쓴 핵심 명사(예: "토큰", "세션")가 어느 섹션에도
   정의 안 됨 → WARN. (consistency_checker 의 cross-section 검사 확장)

**severity 정책**: v1 = 전부 advisory(WARN) + JSON 보고. 안정화 후 일부를 BLOCK 승격,
우회 `--allow-vague-spec` (HarnessAI 관용: agent-mismatch/format-drift 와 동일 패턴).

**LLM 보강 (옵션, v2)**: 결정론 검사가 못 잡는 의미적 모호성은 ha-design 의 부모 세션이
findings 를 받아 추가 판단. 단 1차 방어선은 코드.

**테스트**: `backend/tests/orchestrator/test_skeleton_checklist.py`
- 미정량 표현 탐지/통과, I/O 섹션 실패경로 유무, 수용기준 유무, 용어 정의 cross-ref, 빈 skeleton.

**SKILL.md 배선**: `ha-design` 출력에 `checklist_findings` 추가 → 사용자에게 표시(무시 금지 가드레일).

---

### A2. `/analyze` 독립 게이트 승격 + Constitution 권위 (흡수: `/analyze` + constitution)

> **상태: ✅ v1 구현 (2026-06-22)** — (a) 결정론: `consistency_checker.check_offline_network_violation`
> — 오프라인/네트워크/시크릿 제약 선언 시 비-루프백 URL·다운로드 동사를 **critical** 로 표면화
> (run_all_checks 배선 → ha-design/ha-plan/ha-redesign 자동 흐름). (b) 프롬프트: ha-redesign
> impact-analysis 에 `nfr_conflicts` 필수 단계(#10 정조준 — 신규 의존성/외부호출 ↔ NFR 위반).
> constitution 권위 = skeleton 제약 선언을 critical 권위로 취급(Q1=B). 테스트 +8.
> 잔여: 시크릿 외 §6 일반 제약 확장, "critical→BLOCK" 승격은 FP 관찰 후(Q3=B).

**현재**: `consistency_checker.run_all_checks` 가 `ha-plan`/`ha-redesign` **내부 advisory**로만 돈다.
**흡수**:
1. **독립 체크포인트화**: `ha-plan commit` 직후(또는 `ha-verify prepare` 직전) cross-artifact
   (skeleton ↔ tasks) 분석을 **명시 단계**로 노출. 출력에 `severity` 3단계(CRITICAL/HIGH/MEDIUM) 분류.
2. **Constitution 권위 도입**:
   - ✅ **확정(Q1=B)**: skeleton 의 "하네스 설계/골든 원칙" 섹션을 정본화 (새 파일 신설 X).
   - consistency_checker 가 **원칙 위반을 CRITICAL/BLOCK** 으로 격상 (현재 골든원칙은 문서일 뿐 게이트 미연결).
   - Spec Kit 의미 차용: 충돌 시 원칙을 깎지 말고 skeleton/tasks 를 고치도록 메시지 강제.

**테스트**: 원칙 위반 시 CRITICAL 분류, 정합 시 통과.

---

### A3. `/clarify`식 능동 미명세 발견 (흡수: `/clarify`)

**현재**: HITL LOCKED 인터뷰가 **고정 3섹션**(requirements/user_journey/view.screens)만 강제.
**흡수**: A1 의 `checklist_findings`(특히 clarity/completeness)를 입력으로,
`ha-design` 이 **AskUserQuestion** 으로 최대 N개(예: 5개) 타겟 질문 → skeleton 에 역기록.
→ 흐름: **vague 탐지(코드, A1) → 질문(HITL) → 채움**. 고정섹션 → **격차 주도(coverage-driven)** 로 확장.

**한계**: AskUserQuestion 은 Claude 전용 도구(Track B 의 Tier 2 의존성과 연결).

---

### A4. `ha-converge` — 코드↔스펙 미구현 회수 (흡수: `/converge`)

**현재**: `ha-review` 의 역방향 contract(선언-미구현 엔드포인트)가 **advisory 에 그침**.
**흡수**: 그 advisory 를 **actionable** 하게.
- skeleton 컴포넌트(필수) ↔ 실제 파일/엔드포인트 대조 → 미구현 컴포넌트를 `tasks.md` 에
  `needs_build` 신규 태스크로 append.
- 위치: ✅ **신규 `skills/ha-converge/` 스킬** (Q2 확정 — 검증과 회수 책임 분리).
- #7(부분복구)·역방향 contract 와 결이 같아 로직 일부 재사용.

---

## 4.5 dogfood 갭(#8~#13) → 흡수 매핑

code-mate dogfood 2차에서 추가 발견된 갭의 처리 귀속:

| 갭 | 상태 | 귀속 |
|---|---|---|
| #8 review 빈 diff vacuous pass | ✅ **수정 완료** (`_extract_diff` full-source 폴백) | 독립 |
| #9 reviewed 가 Phase 추가 빌드 가둠 | ✅ **수정 완료** (`_enter_build_state` building 회귀) | 독립 |
| #13 `--parallel` doc 불일치 | ✅ **수정 완료** | 독립 |
| **#10 신규 dep ↔ NFR 미검증** | 미구현 | **A2** |
| **#11 mock된 경계 → verify green** | 부분(#6) | **A1** |
| **#12 과대 태스크 분할 부재** | 미구현 | **A5 (신규, 아래)** |

**#10 → A2 구체화**: analyze 게이트가 **신규 의존성/외부호출이 skeleton §4(시크릿)/§5(네트워크·오프라인)/§6
제약과 충돌**하는지 검사 → 위반 시 CRITICAL/BLOCK. ha-redesign impact-analysis 프롬프트에도
"이 결정이 프로젝트 NFR(오프라인/key-free)을 위반하는가" 명시 검증 단계 추가. (tree-sitter-language-pack
런타임 다운로드가 §5 위반인데 절차만 통과한 사례.)

**#11 → A1 구체화**: skeleton_checklist 에 **"외부 경계(subprocess/네트워크/파일/인코딩)를 가진 컴포넌트가
mock 테스트만 있고 비-mock 스모크가 없으면"** WARN. + ha-plan 테스트 분배 규칙(이미 "I/O 경계 2개 이상")에
"**경계 기능은 mock 외 비-mock 스모크 1개 필수**" 명문화. (run_ruff-on-ts·cp949·language-pack 3연속
재발의 공통 뿌리 = 실패 지점 경계를 mock 해 verify 가 항상 green.)

### A5. done 보존 태스크 분할 (#12, 신규)

ha-plan/ha-redesign 에 **"기존 done 보존 + 특정 태스크를 하위로 분할(T-014 → T-014a/b/c)"** 연산 추가.
- 현재: re-derivation 은 "신규 태스크 추가 범위 밖", `ha-plan --replan`(#2)은 전체 덮어쓰기라 done 리셋
  → 과대 태스크를 안전하게 쪼갤 경로 없음.
- 설계: `tasks.md` 의 한 태스크 행을 N개 하위 행으로 치환하되 **done/needs_rebuild 상태와 무관 태스크는 보존**.
  #2(--replan)·#7(부분복구)와 같은 **iteration-보존 계열**.
- 우선순위: **P5+** (구조 변경, 런타임/설계 게이트보다 후순위).
- **재고(§4.6 패턴2)**: 별도 "분할 연산"보다 **`[X]`/status resume + 범위지정 빌드**가 #7·#12 를
  동시에 더 단순히 해결 → A5 를 그 방향으로 재설계 검토.

## 4.6 Spec Kit 버그-처리 패턴 (구조적 흡수 — dogfood 반복 클래스 대응)

HarnessAI dogfood 반복 버그를 **클래스**로 묶으면, Spec Kit 의 설계가 그 클래스를 구조적으로
회피/처리하는 패턴이 보인다. (기술 기능 흡수 A1~A5 와 별개의 **아키텍처 교훈**.)

### 패턴 1 — 상태머신 경직 (#2·#9·#12, 같은 뿌리 3회 반복) → 아티팩트-선행조건 모델

> **상태: ✅ 바운디드 v1 구현 (2026-06-22)** — 공유 유틸 `utils.reenter_or_assert(prerequisite_state,
> working_state)`: prerequisite 미만 차단 / working 이하 진행 / working 초과는 working 으로 regress
> (재진입). #2(`--replan`)·#9(`_enter_build_state`) 두 밴드에이드를 이 하나로 일원화 — 이제 어떤 phase
> 든 "자기 상태 이상에서 재실행 가능, 이후 상태는 회귀해 downstream 게이트 재통과". 테스트 +6.
> **풀 마이그레이션(글로벌 current_step 제거)은 보류** — 사용자 결정 = 바운디드. 잔여: ha-verify/
> ha-review 재진입 적용(미보고 갭, 선택), A5(태스크 분할)를 `[X]` resume 으로.
HarnessAI 는 forward-only 글로벌 state machine(init→…→shipped, 역행은 `regress()` 만). 이게
#2(redesign 후 re-plan 막힘)·#9(reviewed 후 추가 빌드 막힘)·#12(태스크 분할 불가)를 **반복
생산**한다. **Spec Kit 엔 글로벌 `current_step` 게이트가 아예 없다** — 각 명령은 "필요한 선행
아티팩트(spec/plan/tasks)가 존재하는가"만 확인. 반복(iteration)이 예외가 아니라 기본:
flow-forward(새 feature 디렉토리) / living-spec(spec 수정→하위 재생성) / flow-back(아무
아티팩트나 편집→reconcile) 중 사용자 선택.
→ **흡수**: HarnessAI 의 상태 강제를 "선행 아티팩트 존재 확인"으로 완화하거나, 최소한
re-plan/추가 빌드/분할을 **1급 동작**으로. 이번 #2(`--replan`)·#9(building 회귀)는 **땜질** —
근본은 state machine 완화. (가장 큰 구조적 교훈; 현재 HarnessAI 버그 1순위 양산처.)

### 패턴 2 — 부분완료·과대태스크 (#7·#12) → `[X]` 마커 + 런당 범위 스코핑
Spec Kit: 완료 태스크를 tasks.md 에 `[X]` 로 마킹 → 다음 `/implement` 가 거기서 이어감. 대형
기능은 `/implement only execute T001-T010, then stop` 으로 **런당 범위를 좁힘**(툴 변경 0).
context 소진(=서브에이전트 degrade)을 명시적으로 다루고, 서브에이전트 위임도 옵션 안내.
→ HarnessAI 의 #7(in-progress 마킹 머신)·A5(분할 연산)는 더 무거운 재발명. **`[X]`/status 기반
resume + ha-build 범위지정("T-001..T-005 만")** 하나로 #7·#12 동시 해결이 더 단순.

### 패턴 3 — silent divergence·vacuous (#1·#8) → clean tree + reflect-back 규율
Spec Kit 은 drift 를 코드 게이트가 아니라 "**clean working tree 에서 시작 → 모든 생성 변경이
리뷰 가능 + 결정을 spec 에 반영(reflect-back)**" 규율로 다룸(spec-persistence 의 'silent
divergence' 명시 경고). HarnessAI 의 hash 게이트는 더 강하지만 **도구 자기 변경을 외부수정으로
오판**(#1/#5)하는 자해. → 교훈: 게이트는 도구 산출(§태스크 sync)을 baseline 에 흡수해야 함
(이미 #1 수정). spec-as-source 방향(skeleton→spec, v1.0 백로그)은 reflect-back 을 자연스럽게 함.

### 종합
기술 기능(A1~A4)은 *추가*고, **패턴 1(상태머신 완화)이 가장 근본적인 흡수** — HarnessAI 의
강점(코드 강제 게이트)은 유지하되, **상태 전이를 forward-only 가 아니라 아티팩트-선행조건 +
명시 iteration**으로 바꾸면 #2/#9/#12 클래스가 통째로 사라진다. Spec Kit 의 "게이트 없음"을
그대로 베끼면 HarnessAI 의 검증 강점을 잃으므로, **선행조건 확인은 코드로 강제하되 글로벌
선형 상태는 완화**하는 절충이 정답.

## 5. Track B — 멀티 에이전트 호환 (흡수: Spec Kit `integrations/` 패턴)

> **상태: ✅ CLI 배선 완료 (2026-06-22)** — `backend/src/orchestrator/agent_scaffold.py`:
> `AGENT_SPECS`(claude/gemini/copilot 3종) + `parse_skill_md` + `render(skill, desc, body, agent)`
> + `render_context(agent)`(GEMINI.md / .github/copilot-instructions.md).
> SKILL.md(중립 소스) → 에이전트별 포맷 변환: args 토큰($ARGUMENTS↔{{args}}) + `~/.claude/` 경로
> (→ ${HARNESS_AI_HOME}/, claude 제외) 치환 — **skills/ + harness/bin 둘 다** 포함. gemini=TOML literal,
> copilot/claude=md+frontmatter.
> **CLI**: `harness scaffold --agent {claude|gemini|copilot|all} [--skill ha-X] [--out DIR] [--dry-run]`
> — 중립 SKILL.md 소스를 읽어 실제 파일 생성. agent_scaffold 를 standalone 로드(orchestrator 패키지
> __init__ 우회 → pydantic/yaml 불필요). HARNESS_AI_HOME 필수(미설정 시 exit 3).
> 테스트 37 (모듈 29 + CLI e2e 8, tomllib 파싱 검증 + 실제 미러 CLI subprocess).
> **잔여(다음 증분)**: Tier 2/3 스킬(AskUserQuestion/Agent 서브에이전트 의존)의 에이전트별 상호작용 대체
> — run.py 백엔드는 그대로 동작하나 질문/위임 UX 는 에이전트마다 다름.

**Spec Kit 패턴**: agent-agnostic 명령 본문 1벌 + per-agent 어댑터(경로/포맷/args 토큰 3속성).
Claude Code 통합 = `.claude/skills/<name>/SKILL.md` + `$ARGUMENTS` → **HarnessAI 현행과 동일**.

**HarnessAI 자산**: 로직이 이미 에이전트 중립 `run.py` 에 있음. SKILL.md 는 얇은 래퍼.

**설계**:
1. 각 스킬에 **에이전트 중립 명령 본문**(`skills/ha-*/COMMAND.md`) 분리 — 현 SKILL.md 본문이 거의 그대로 소스.
2. **스캐폴더**(`harness/bin/harness scaffold --agent <x>`):
   ```
   AGENTS = {
     "claude":  {dir: ".claude/skills/{n}", file: "SKILL.md",      fmt: md,   args: "$ARGUMENTS"},
     "gemini":  {dir: ".gemini/commands",   file: "{n}.toml",       fmt: toml, args: "{{args}}"},
     "copilot": {dir: ".github/prompts",    file: "{n}.prompt.md",  fmt: md,   args: "$ARGUMENTS"},
   }
   ```
   → 단순 에이전트(Gemini)는 딕셔너리 한 줄. **Copilot 은 특수처리 분기** 필요:
   명령당 `.github/prompts/<n>.prompt.md`(+선택 `.agent.md`), 컨텍스트 `.github/copilot-instructions.md`,
   선택적 `.vscode/settings.json` — Spec Kit `copilot` 통합과 동일. 스캐폴더에 small special-case.
3. `run.py` 는 중앙(`HARNESS_AI_HOME`) 고정, 래퍼는 `python <HOME>/skills/ha-X/run.py` 호출만.

**확정 타깃 (Q4)**: Claude(네이티브) + **Gemini + Copilot 둘 다**. 스캐폴더는 한 번 만들고
3종 산출. PoC 순서만 단순한 Gemini 먼저(파이프 증명) → 즉시 Copilot 추가.

**포팅 난이도 (정직)** — Claude 전용 도구 의존도별 3등급:

| 등급 | 스킬 | 의존 | 비용 |
|---|---|---|---|
| 1 (거의 공짜) | ha-verify, ha-smoke, ha-ship, ha-log | Bash(run.py)만 | 래퍼 포맷만 — **PoC 출발점** |
| 2 (상호작용 치환) | ha-init, ha-design, ha-plan | AskUserQuestion | 에이전트별 질문 방식 치환 |
| 3 (서브에이전트 치환) | ha-build, ha-redesign | Agent(model=sonnet) | 인라인 or 에이전트식 위임 대체 |

**PoC 범위**: Tier 1 스킬 1개(ha-verify) × Gemini 어댑터로 end-to-end 증명 → 같은 스킬에
Copilot 어댑터 추가로 "스캐폴더가 다포맷 산출" 확인.

---

## 6. Track C — 확장 훅 (흡수: extensions.yml hooks, **후순위**)

`harness-hooks.yml` 로 단계별 pre/post 훅(예: `before_ship` → gstack `/review`) 플러그인화.
Spec Kit 의 optional/mandatory 훅 모델 차용. 우선순위 낮음(1인 프로젝트).

## 7. 안 가져올 것
- bash+ps 이중 스크립트 (단일 run.py 우월)
- workflows 엔진, bundles/preset 생태계 (과함)

---

## 8. 로드맵 (단계)

| Phase | 내용 | 산출 | 의존 |
|---|---|---|---|
| **P1** ✅ | A1 `skeleton_checklist.py` + ha-design 배선 + 테스트 (v1: clarity+edge_case) | 설계품질 게이트 | 완료 2026-06-22 |
| **P2** ✅ | A2 analyze(offline/NFR critical 검사) + ha-redesign nfr_conflicts 프롬프트 | cross-artifact 게이트 | 완료 2026-06-22 |
| **P3** | A3 clarify 확장 (A1 findings → 질문) | coverage HITL | P1 |
| **P4** ✅ | Track B — agent_scaffold + `harness scaffold` CLI (render+context, claude/gemini/copilot) | 멀티에이전트 파일 생성 | 완료 2026-06-22 (CLI 배선 포함) |
| **P5** | A4 ha-converge | 코드↔스펙 회수 | §9-Q2 |
| **P6** | Track B 전 스킬 확장 + Track C 훅 | 완성 | P4 |

P1 과 P4 는 서로 독립 → 병렬 가능.

## 9. 결정사항 (2026-06-22 확정)

- **Q1 (Constitution 출처)**: ✅ **B — skeleton 골든원칙 섹션 정본화** (새 파일 신설 X). 중복/split-brain
  방지, skeleton 단일 계약 유지. analyze 게이트가 이 섹션을 CRITICAL 권위로 읽음. (사용자 결정권 영역)
- **Q2 (converge 위치)**: ✅ **A — 신규 `ha-converge` 스킬**. 검증(매 루프) vs 회수(가끔) 책임·주기 분리.
- **Q3 (checklist severity)**: ✅ **B — advisory 시작 → FP 관찰 후 BLOCK 승격**. 휴리스틱 FP 홍수 전례
  (LESSON-030, #5 `--accept-skeleton-drift` 상시화) 회피.
- **Q4 (멀티에이전트 타깃)**: ✅ **Gemini + Copilot 둘 다** (+ Claude 네이티브). 스캐폴더 1개로 3종 산출.
  PoC 순서만 Gemini 먼저. **실전 주력 에이전트는 사용자 확인 대기** (롤아웃 1순위 결정용).

## 10. 검증 전략
- 각 게이트는 **테스트 먼저**(TDD): 위반 케이스 RED → 구현 GREEN.
- 미러 2벌(`~/.claude` + repo `skills/`·`harness/`) cp 동기 필수.
- 전체 `pytest` + ruff + pyright clean 유지.
- Track B 는 실제 CLI e2e(임시 프로젝트에 스캐폴드 → 명령 호출)로 검증.

## 11. 성공 기준
- 설계 게이트 4 → 8+ 로 균형 회복 (구현 게이트 대비).
- "vague 표현/엣지케이스 누락 skeleton" 이 빌드 전 표면화됨 (회귀 테스트로 증명).
- Gemini/Copilot 에서 최소 1개 스킬이 run.py 백엔드로 동일 동작.
