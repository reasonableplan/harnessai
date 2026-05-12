---
name: ha-build
description: |
  HarnessAI v2 — 단일 태스크 구현 (Backend/Frontend Coder 역할).
  태스크 의존성 그래프 기반 병렬 실행 지원 (--parallel).
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

**병렬 모드**: `--parallel T-001,T-002,T-003` — depends_on 없는 태스크만 허용. run.py 가 검증.

### 2. 구현 — Agent 위임 (단일/병렬 공통)

**prepare JSON 을 받았으면 다음 단계는 곧바로 Agent 호출입니다.** 부모는 prepare 출력을
훑어 보거나 spec 블록을 미리 grep 하지 않습니다 — 그건 Agent 의 일입니다. 부모가
"먼저 좀 봐두자" 모드로 빠지면 그대로 직접 작업 모드로 미끄러져 룰이 무너집니다.

각 태스크마다 Agent tool 을 호출해 Sonnet 서브에이전트에 위임합니다.
이렇게 하면 부모 세션 모델(Opus/Sonnet) 이나 extra-usage 토글 상태와 무관하게
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

prepare 출력 (위에서 받은 JSON): <prepare 결과 그대로 첨부>
```

부모 세션의 일은 prepare → Agent 위임 → 결과 종합 → run.py complete 입니다.
**부모가 직접 Edit/Write 로 코드 파일을 만들면 위임 원칙 위반**입니다.

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

## 가드레일

- 태스크 description 외 작업 추가 금지 (scope creep 방지)
- 프로파일 화이트리스트 외 의존성 설치 금지
- 테스트 없이 done 처리 금지
- depends_on 만족 안 된 태스크 시작 금지 (run.py 가 prepare 단계에서 차단)
- 같은 태스크 ID 중복 작업 금지

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

## 트러블슈팅

**depends_on 미만족**: run.py prepare 가 차단함. 의존하는 태스크 먼저 완료.
**병렬 모드에서 race condition**: 같은 파일 수정하는 태스크는 병렬 X. depends_on 으로 직렬화.
**3회 재시도 실패**: blocked 처리 후 사용자 개입 필요.

## 모바일 프로젝트 사용 예시 (Flutter)

**4단계 — `/ha-build` 로 태스크 구현**:

- `/ha-plan` 완료 후 `tasks.md` 의 태스크를 순서대로 실행
- Flutter 태스크 실행 예시:
  ```bash
  python ~/.claude/skills/ha-build/run.py prepare --task T-001
  ```
- `guideline_paths` 의 flutter 가이드라인 4개 읽은 후 구현 시작
- 에이전트: `mobile_coder_flutter` — go_router + Riverpod + drift 컨벤션 준수

**react-native-expo 의 경우**:
- 에이전트: `mobile_coder_rn`
- Expo SDK API 우선 사용 (react-native 직접 API 최소화)
- `expo run:android` / `expo run:ios` 로 로컬 테스트

**android-kotlin 의 경우**:
- 에이전트: `mobile_coder_android`
- MVVM + Hilt DI + Compose UI 패턴 준수
- `./gradlew assembleDebug` 로 빌드 확인

**ios-swift 의 경우**:
- 에이전트: `mobile_coder_ios`
- SwiftUI + Combine / async-await 패턴
- Windows host 에서는 `swift build` dry-run 만 가능 (macOS CI 에서 전체 빌드)
