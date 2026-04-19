---
name: ha-build
model: sonnet
description: |
  HarnessAI v2 — 단일 태스크 구현 (Backend/Frontend Coder 역할).
  태스크 의존성 그래프 기반 병렬 실행 지원 (--parallel).
  코드 작성 속도/비용 최적화 위해 Sonnet 사용.
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

### 2. 단일 모드 — 직접 구현
- 태스크의 `agent` 에 따라 `<HARNESS_AI_HOME>/backend/agents/<agent>/CLAUDE.md` 읽음
- 활성 프로파일 본문 읽음 (실제 컨벤션)
- 관련 skeleton 섹션 (component 와 매핑) 읽음
- 기존 코드 (해당 컴포넌트의 파일들) Glob/Read 로 확인
- **테스트 먼저 작성** → 실패 확인 → 구현 → 테스트 통과 → 린트
- 새 파일/수정 파일 모두 사용자 화이트리스트 외 의존성 추가하지 않을 것

### 3. 병렬 모드 (Agent 분기)
지정된 태스크들에 대해 각각 Agent tool 호출 (general-purpose subagent):
```
Agent({
  description: "Build T-001",
  subagent_type: "general-purpose",
  prompt: "<단일 모드와 동일한 prompt — 단, 자기 태스크만 처리>"
})
```
모든 sub-agent 완료 후 결과 종합.

### 4. 검증 (자체)
- 작성한 테스트가 통과하는지 (`uv run pytest`, `pnpm test` 등 — 프로파일 toolchain.test)
- 실패 시 최대 3회 재시도
- 그래도 실패면 태스크 상태 "blocked" 로 마킹

### 5. tasks.md 업데이트
```bash
python ~/.claude/skills/ha-build/run.py complete --task T-001 --status done
```
또는 `--status blocked --reason "<이유>"`.

**LESSON-021 게이트 (done 전용)**:
- `--status done` 시 프로파일의 **`toolchain.test + toolchain.lint + toolchain.type`
  전부** 강제 실행. 하나라도 실패하면 done 거부 (태스크는 마킹 안 됨).
- 문서/설계처럼 toolchain 무관한 태스크엔 `--skip-toolchain` 명시.
- 배경: ui-assistant 2차 E2E 에서 단위 테스트만 통과 → done 흐름으로 pyright 15 errors 누적 발견.

run.py 가:
- `--status done` → LESSON-021 게이트 통과 → tasks.md 해당 행 상태 업데이트
- 모든 태스크 done 이면 "building" → "built" 자동 전이
- 일부만 done 이면 "planned" → "building" (첫 done 시)

### 6. 다음 단계 안내
```
✅ T-001 완료
남은 태스크: T-002 (depends_on: T-001 → 이제 시작 가능), T-003

다음:
  /ha-build T-002
  또는 모든 태스크 완료 시: /ha-verify
```

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

## 트러블슈팅

**depends_on 미만족**: run.py prepare 가 차단함. 의존하는 태스크 먼저 완료.
**병렬 모드에서 race condition**: 같은 파일 수정하는 태스크는 병렬 X. depends_on 으로 직렬화.
**3회 재시도 실패**: blocked 처리 후 사용자 개입 필요.
