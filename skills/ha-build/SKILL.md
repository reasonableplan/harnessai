---
name: ha-build
description: |
  HarnessAI v2 — 단일 태스크 구현 (Backend/Frontend Coder 역할).
  태스크 의존성 그래프 기반 병렬 실행 지원 (--task 에 CSV: T-001,T-002).
  코드 작성은 Agent tool (model="sonnet") 위임 — 부모 세션 모델/extra-usage 무관.
  Use when: /ha-plan 완료 후 태스크별 구현, "T-001 만들어줘", "/ha-build T-001"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - Agent
  - AskUserQuestion
---

> 🛑 **STOP — 부모 세션은 코드 작업을 직접 하지 않습니다.**
>
> `prepare` 실행 직후 즉시 **Agent tool 을 호출하여 Sonnet 서브에이전트에 위임**하세요.
> 부모가 직접 Read / Grep / Glob / Edit / Write 로 소스 파일을 만지면 룰 위반입니다.
>
> 부모가 하는 일은 정확히 4단계: **(1) prepare 실행 → (2) Agent 호출 → (3) 결과 종합 → (4) complete 실행**.
> 그 사이에 spec 분석, 코드 검색, 패턴 매칭, 파일 수정 — 전부 Agent prompt 안에서 일어나야 합니다.
>
> 이유: SKILL.md frontmatter 의 `model:` 의존성을 제거한 대신, 코드 작성 자체를
> Agent(model="sonnet") 로 명시 위임하는 것이 Sonnet 강제의 유일한 보장입니다.
> 부모가 grep/read 부터 시작하면 곧장 직접 작업 모드로 빠져 룰이 무너집니다.

## 사전 조건 (v0.10.0 HITL gate)

`/ha-build` 진입 전 `frozen_status="frozen"` 필수. drafting 이면 차단.

먼저 다음 흐름 완료:
1. `/ha-design` 인터뷰 — LOCKED 섹션 (requirements/user_journey/view.screens) 후보 N 개 → 사용자 선택
2. `/ha-design commit --locked-sections requirements user_journey view.screens` — `plan.freeze()` 호출
3. `harness-plan.md` frontmatter 에 `frozen_status: frozen` + `frozen_at: <ISO>` 박힘

확인:
```bash
grep "frozen_status" docs/harness-plan.md
```

마이그레이션 케이스 (기존 v0.9.x 프로젝트) 는 `--skip-frozen-gate` 옵트인.

## 사전 조건 2 — skeleton drift 게이트

`prepare` 가 skeleton.md 의 hash 를 plan 의 `skeleton_hash` 와 비교한다.
freeze 이후 외부 수정 (수동 편집 등) 이 감지되면 **BLOCK**. 진행하려면:
- `/ha-redesign` 으로 변경을 audit trail 에 반영 (권장), 또는
- `prepare --task T-XXX --accept-skeleton-drift` (의도적 수동 편집 인정 — audit 누락 감수)

legacy plan (hash 미기록) 또는 skeleton.md 부재 시 비교 없이 통과.

## 역할

`tasks.md` 의 단일 (또는 병렬 다중) 태스크를 구현.

**입력**: 태스크 ID (예: T-001)
**출력**: 태스크의 코드/테스트 파일 + tasks.md 상태 업데이트
**다음**: 모든 태스크 done 후 `/ha-verify`

## 실행 순서

### 1. 사전 조건 + 태스크 정보
```bash
python ~/.claude/skills/ha-build/run.py prepare --task T-001
```
JSON 출력: 태스크 정보 (agent, depends_on, description, path), 활성 프로파일, 에이전트 프롬프트 경로, depends_on 만족 여부.

**병렬 모드**: `--task T-001,T-002,T-003` (콤마 구분 CSV) — depends_on 없는 태스크만 허용. run.py 가 검증. (`--parallel` 플래그는 없음.)

**resume 모드** (`--task` 생략): `prepare --resume` — 다음 ready 태스크(status 대기/in-progress + depends_on 전부 done)를 자동 선택. in-progress 우선(부분복구), 그다음 대기, T-ID 오름차순. 빌드할 게 없으면(전부 done) exit 0. "다음 뭘 빌드?" 를 tasks.md 수동 독해 없이 해결 (#7 부분복구·iteration 후 유용). 선택된 단일 태스크로 이후 단계 진행.

**착수 마킹 + 부분 완료 복구 (issue #7)**: prepare 는 대기 태스크를 `in-progress` 로 마킹하고
시작한다 (서브에이전트가 도중에 죽어도 status 로 흔적이 남도록). 출력 task 의:
- `reentry: true` — 이미 in-progress 였음 = 이전 착수가 끝나지 않음 (중단 후 재진입). 이 경우
  **새로 처음부터 만들기 전에** `existing_files` (선언 산출 중 이미 존재하는 파일) 를 점검해
  "이어서" 할지 "처음부터" 할지 결정하라. Agent prompt 에 부분 산출물 상태를 명시할 것.
- `declared_files` / `existing_files` — spec 의 "생성/수정 파일" 중 실재하는 것. 부분 완료 판단 근거.

### 2. 구현 — Agent 위임 (단일/병렬 공통)

**prepare JSON 을 받았으면 다음 단계는 곧바로 Agent 호출입니다.** 부모는 prepare 출력을
훑어 보거나 spec 블록을 미리 grep 하지 않습니다 — 그건 Agent 의 일입니다. 부모가
"먼저 좀 봐두자" 모드로 빠지면 그대로 직접 작업 모드로 미끄러져 룰이 무너집니다.

각 태스크마다 Agent tool 을 호출해 Sonnet 서브에이전트에 위임합니다.
이렇게 하면 부모 세션 모델(Fable/Opus 등) 이나 extra-usage 토글 상태와 무관하게
코드 작성은 항상 Sonnet 에서 실행됩니다.

```
Agent({
  description: "Build T-001",
  subagent_type: "general-purpose",
  model: "sonnet",                      // ← 부모 모델 무관, 항상 Sonnet 강제
  prompt: "<아래 'Agent prompt 템플릿' 그대로 — 자기 태스크만 처리>"
})
```

- **단일 모드** (`--task T-001`): Agent 호출 1회.
- **병렬 모드** (`--task T-001,T-002,T-003`): 한 메시지에 Agent 호출 N개 (병렬 실행).
  단, run.py prepare 가 같은 그룹 내 의존성 차단을 사전 검증.

부모 세션은 모든 서브에이전트 완료 후 결과 종합 → run.py complete 호출만.

#### Agent prompt 템플릿

각 Agent 호출의 prompt 에 다음을 그대로 포함하세요 (자기 태스크 ID 만 치환):

```
당신은 HarnessAI 의 <agent> 역할로 태스크 <T-XXX> 를 구현합니다.

읽기 순서 (엄수):
1. docs/tasks.md 의 해당 T-XXX 스펙 블록 — 가장 먼저 Read
   · "생성/수정 파일", "skeleton 참조", "구현 세부 (컬럼/props 타입/action 시그니처)" 를 그대로 사용.
   · 파일 경로/파일명/필드 자율 변경 금지 — 스펙이 곧 Architect/Designer 의 결정.
   · 스펙 블록이 없거나 불완전 (생성 파일 미명시, 필드 미명시 등) 하면:
     - 구현 중단.
     - python ~/.claude/skills/ha-build/run.py complete --task T-XXX --status blocked --reason "tasks.md 스펙 블록 <구체 항목> 누락" 실행.
     - 사용자가 Architect/Designer 에 에스컬레이션 후 skeleton/tasks.md 보완 → 재실행.
   · (하위 호환) 구버전 tasks.md: skeleton + agent CLAUDE.md 로 구현 가능하되,
     파일 경로/필드를 직접 결정하기 전에 skeleton 의 persistence/interface.http/view.*
     섹션에 명시돼 있는지 확인. 명시 없으면 위 에스컬레이션.
2. <HARNESS_AI_HOME>/backend/agents/<agent>/CLAUDE.md — 역할 프롬프트 (권위 순서 + 자율 결정 금지 테이블)
3. docs/conventions.md + docs/guidelines/ — 사용자 스타일 최상위 권위
4. 스펙 블록이 참조하는 skeleton 섹션 (예: persistence.users, interface.http.auth) — 세부 구현
5. 활성 프로파일 본문 — 허용 라이브러리 / toolchain
6. 기존 코드 — 스펙 블록의 "참조 파일" + 동일 레이어 기존 구현 (패턴 복제)

구현 흐름:
- 테스트 먼저 작성 → 실패 확인 → 구현 → 테스트 통과 → 린트
- 스펙 블록의 "구현 세부" 를 코드에 1:1 매핑 (컬럼 누락/타입 변경/필드 추가 금지)
- 새 파일/수정 파일 모두 프로파일 화이트리스트 + conventions 내에서만

출력 계약: 작업 완료 보고 끝에 핸드오프 노트 (한 일 / 우려 1가지 / 스펙 따랐지만 이견 /
다음 역할에게 — 역할 CLAUDE.md 의 '핸드오프 노트' 양식) 를 반드시 남기세요.

prepare 출력 (위에서 받은 JSON): <prepare 결과 그대로 첨부>
```

부모 세션의 일은 prepare → Agent 위임 → 결과 종합 → run.py complete 입니다.
**부모가 직접 Edit/Write 로 코드 파일을 만들면 위임 원칙 위반**입니다.

### 핸드오프 노트 전달 (서브에이전트 → 사용자)

서브에이전트는 출력 끝에 **핸드오프 노트**(한 일 / 우려 1가지 / 이견 / 다음 역할에게)를 남긴다.
부모는 결과 종합 시 이 노트를 **사용자 보고에 그대로 포함**한다 — 특히 "우려 1가지" 는 생략 금지.
병렬 모드면 태스크별로 모아 보여준다.

### 4. 검증 (자체)
- 작성한 테스트가 통과하는지 (`uv run pytest`, `pnpm test` 등 — 프로파일 toolchain.test)
- 실패 시 최대 3회 재시도
- 그래도 실패면 태스크 상태 "blocked" 로 마킹

### 5. tasks.md 업데이트
```bash
python ~/.claude/skills/ha-build/run.py complete --task T-001 --status done
```
또는 `--status blocked --reason "<이유>"`.
또는 `--status skipped` — Phase 2+ scope 등 **의도적으로 미루는** 태스크 (toolchain/security 게이트 건너뜀). 모든 태스크가 `done|skipped` 이면 `built` 자동 전이.

**LESSON-021 게이트 (done 전용)**:
- `--status done` 시 프로파일의 **`toolchain.test + toolchain.lint + toolchain.type`
  전부** 강제 실행. 하나라도 실패하면 done 거부 (태스크는 마킹 안 됨).
- 문서/설계처럼 toolchain 무관한 태스크엔 `--skip-toolchain` 명시.
- security_hooks 만 의도적으로 우회할 땐 `--skip-security` (toolchain 과 독립).
- 배경: ui-assistant 2차 E2E 에서 단위 테스트만 통과 → done 흐름으로 pyright 15 errors 누적 발견.

**v0.10.0**: `--status done` complete 후 worklog.md (docs/worklog.md) 에 변경 자동 append 됨.

**LESSON-021 강화 (B3 — no-tests 우회 감지)**:
- `toolchain.test` 가 exit 0 이어도 출력에 `no tests ran` / `passWithNoTests` /
  `0 tests` / `0 passed` 패턴 발견 시 `[WARN] LESSON-021 강화` 메시지 출력.
- BLOCK 아님 — WARN 만. 의도적 상황(초기 세팅 등)이면 무시 가능.
- profile 의 `toolchain.test` 명령에 `--passWithNoTests` 나 collection-only 플래그가
  있으면 실제 테스트 디렉토리/파일이 존재하는지 먼저 확인 후 실행 권장.

run.py 가:
- `--status done` → LESSON-021 게이트 통과 → tasks.md 해당 행 상태 업데이트
- 모든 태스크 done 이면 "building" → "built" 자동 전이
- 일부만 done 이면 "planned" → "building" (첫 done 시)

### 5-b. blocked 태스크 재시작

blocked 처리 후 원인이 해결됐으면:

1. **원인 확인**: skeleton/tasks.md 보완 완료 또는 의존 태스크 done 확인
2. **prepare 재실행** (의존성 재검증):
   ```bash
   python ~/.claude/skills/ha-build/run.py prepare --task T-XXX
   ```
3. **Agent 위임 → 구현** (단계 2 동일 절차)
4. **complete**:
   ```bash
   python ~/.claude/skills/ha-build/run.py complete --task T-XXX --status done
   ```
   blocked → done 직접 전환 가능 (in-progress 경유 불필요).

### 6. 다음 단계 안내
```
✅ T-001 완료
남은 태스크: T-002 (depends_on: T-001 → 이제 시작 가능), T-003

다음:
  /ha-build T-002
  또는 모든 태스크 완료 시: /ha-verify
```

### 출력의 guideline_paths 읽기 (필수)

출력 JSON 의 `tasks[].guideline_paths` 에 포함된 경로를 **작업 시작 전 모두 Read 로 읽으세요.**
프로파일별 파일 목록 → `<HARNESS_AI_HOME>/skills/_ha_shared/GUIDELINES_NOTE.md` 참조.

에이전트별 매핑: `mobile_coder_flutter` → flutter, `mobile_coder_rn` → react-native-expo,
`mobile_coder_android` → android-kotlin, `mobile_coder_ios` → ios-swift,
`backend_coder` → plan 의 backend 프로파일, `frontend_coder` → plan 의 frontend 프로파일.

## 작업 일지 자동 기록 (worklog)

run.py 가 complete 시 박는 메타 1줄 (`task=..., status=done`) 과 **별개로**, 이 스킬 작업
중 부모 세션이 판단해서 의미 있는 변경을 `ha-log` 로 worklog.md 에 박는다.

**구현 도중 — 그때그때**: 사용자가 다음을 주면 처리 완료 직후 1줄 요약을 박는다.
- 방향을 바꾼 수정 요청 ("이거 이렇게 바꿔줘")
- 버그 지적 + 수정
- 구현에 영향 준 결정

```bash
python ~/.claude/skills/ha-log/run.py append \
  --category change \
  --message "<무엇을 왜 바꿨는지 한 줄>" \
  --project "<프로젝트 루트 — docs/ 의 상위>"
```

카테고리: 수정/버그 → `change`, 결정/논의 → `discussion`, 다음 할 일 → `next`.

**제외 (노이즈 차단)**: 오타·포맷·표현 수정, 단순 질문/잡담, run.py 가 이미 박는 complete 메타.

**세션 마무리 — "오늘 끝 / 마무리 / 오늘 한 일 정리" 신호 시**: 이 세션에서 한 작업을
카테고리별로 모아 worklog 에 박는다 (항목마다 append 1회 호출). 구현/수정 → `change`,
정한 것 → `discussion`, 다음 할 것 → `next`. 박은 뒤 "오늘 N건 일지 기록" 1줄 보고.

## 가드레일

- 태스크 description 외 작업 추가 금지 (scope creep 방지)
- 프로파일 화이트리스트 외 의존성 설치 금지
- 테스트 없이 done 처리 금지
- depends_on 만족 안 된 태스크 시작 금지 (run.py 가 prepare 단계에서 차단)
- 같은 태스크 ID 중복 작업 금지

### TDD Iron Law (superpowers `test-driven-development` 이식, 2026-06-01)

> **실패하는 테스트 없이 프로덕션 코드 금지.**

- 실패하는 테스트를 먼저 작성 → **실패를 눈으로 확인** → 최소 구현 → 통과 → 린트. ("실패 확인" 단계를 건너뛰면 테스트가 옳은 걸 테스트하는지 알 수 없음.)
- 구현 코드를 테스트보다 먼저 짰다면 **삭제하고 테스트부터 다시.** "참고용으로 남겨두기" / "보면서 적응" 금지 — 삭제는 삭제.
- 예외(서브에이전트가 사용자에게 확인): throwaway 프로토타입 / 생성 코드 / 설정 파일. "이번 한 번만 TDD 건너뛰자"는 생각이 들면 그게 합리화 신호.

## AI Slop 방지 — 코드 작성 시 반드시 지킴

구현 중 다음 패턴은 **만들지 말 것** (과거 code-hijack E2E 에서 발견된 slop):

1. **사용 안 할 파라미터/컨텍스트 injection 금지**
   - ❌ `@click.pass_context` + `ctx: click.Context` 받지만 ctx 안 씀
   - ✅ 실제로 ctx 써야 할 때만 decorator 붙임

2. **호출자 없는 helper 금지**
   - ❌ `def build_layer_stats(): ...` 만들었지만 호출처 없음 ("미래에 쓸 수도")
   - ✅ 지금 호출할 곳이 있을 때만 작성. 미래용이면 skeleton `notes` 섹션에 기록

3. **의미 없는 try/except 금지**
   - ❌ `try: foo() except SomeError: raise` (re-raise 만)
   - ✅ 진짜 처리(복구/로깅/변환) 있을 때만

4. **장황한 docstring 금지**
   - ❌ 함수 코드보다 docstring 이 긴 경우 (200자+)
   - ✅ 한 줄 요약 + WHY 에 초점. WHAT 은 코드가 말함

5. **일관성 — UI 진행 표시**
   - ❌ `[3/4]` 있는데 `[2/4]` 없음
   - ✅ 시리즈면 모든 단계 표시 또는 전부 생략

6. **dead code 허용 금지**
   - ❌ import 했는데 안 씀 / 정의됐는데 호출 안 됨
   - ✅ 커밋 전 `ruff check` / `pyright` 에서 unused 경고 0개

7. **계층 분리 위반 금지**
   - ❌ 라우터 함수 안에 `await db.execute()` / `db.add()` / `await db.commit()` 직접 호출
   - ✅ 반드시 `services/` 계층 메서드를 경유 — 라우터는 호출만

8. **서비스 파일 간 헬퍼 중복 금지**
   - ❌ `scenes.py` 와 `chapters.py` 각각에 `_item_to_dict()` 복붙
   - ✅ 공통 로직은 `utils.py` 1곳 또는 Pydantic `model_dump()` 활용
   - 새 헬퍼 작성 전 반드시 grep: `grep -rn "def <함수명>" src/`

9. **Frontend 시각 AI티 금지** (frontend-design 이식, 2026-06-01 — 프론트 코드 작성 시)
   - ❌ 흔한 폰트 — Arial / Inter / Roboto / Space Grotesk / system 기본값
   - ❌ 클리셰 컬러 — 보라색 그래디언트, 뻔한 파스텔
   - ❌ 예측 가능한 레이아웃 / 어디서나 본 듯한 컴포넌트 패턴
   - ❌ 카드 아이콘 이모지 (🙂🛡️ 등), `❌` 텍스트 마커 → 컬러 dot·미니멀 마커·`✕` 로
   - ✅ 하나의 명확한 미학(brutal minimal / maximalist / retro 등)을 정해 **정밀하게** 실행 — 산만하게 섞지 말 것
   - ✅ 프로젝트마다 폰트·테마 변주 (디자인 시스템 있으면 conventions/DESIGN.md 우선)
   - 근거: "AI티 = 결함" — 단순 미감이 아니라 신뢰·차별화 신호 손상.

## 트러블슈팅

**depends_on 미만족**: run.py prepare 가 차단함. 의존하는 태스크 먼저 완료.
**병렬 모드에서 race condition**: 같은 파일 수정하는 태스크는 병렬 X. depends_on 으로 직렬화.
**3회 재시도 실패**: blocked 처리 후 사용자 개입 필요.

## 모바일 프로젝트 사용 예시 (Flutter)

에이전트 매핑: flutter→`mobile_coder_flutter` (go_router+Riverpod+drift),
react-native-expo→`mobile_coder_rn` (Expo SDK 우선, android/iOS 단일 T-NNN),
android-kotlin→`mobile_coder_android` (MVVM+Hilt+Compose),
ios-swift→`mobile_coder_ios` (SwiftUI — Windows 호스트는 `swift build` dry-run 만,
전체 빌드는 macOS CI). guideline_paths 4파일 읽은 후 구현 시작.
