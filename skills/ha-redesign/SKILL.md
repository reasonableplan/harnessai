---
name: ha-redesign
description: |
  HarnessAI v2 — mutation propagation. 결정 변경 (CEO pivot / eng review 수정 / 요구사항 변경)
  을 받아 영향받는 skeleton 섹션과 tasks 를 식별하고 re-derivation 을 propagate.
  v2 파이프라인의 forward-only 흐름이 잡지 못하는 backward-propagation 결함을 메우는 cross-cutting 스킬.
  영향 분석 + 재설계 모두 Agent (model="sonnet") 위임 — 부모 모델 무관.
  Use when: skeleton 채워진 이후 결정이 바뀔 때, "CEO pivot 반영", "/ha-redesign"
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

> 🛑 **STOP — 부모 세션은 분석/재설계 작업을 직접 하지 않습니다.**
>
> 영향 분석 (Impact Analysis) 과 재설계 (Re-derivation) 둘 다 **Agent tool 로 Sonnet
> 서브에이전트에 위임**합니다. 부모는 Bash 명령 실행 + AskUserQuestion + Agent 호출
> + 결과 종합만 합니다. 직접 skeleton.md/tasks.md 를 분석하거나 수정하지 마세요.
>
> 이유: 본 작업은 (a) 분석 토큰이 무겁고 (skeleton 26 섹션 전체 + decision 매핑) (b) 재설계
> 토큰은 더 무거우며 (영향 섹션 본문 재생성) (c) 부모 모델/extra-usage 무관하게 Sonnet 으로
> 일관 처리해야 합니다.

## 역할

기존 v2 파이프라인 (`/ha-init → /ha-design → /ha-plan → /ha-build → /ha-verify → /ha-review`)
은 forward-only 단방향 생성. 결정이 중간에 바뀌면 (CEO pivot, eng review 결과) 본문 §1~15
는 update 안 되고 §16 태스크만 추가되어 §1~15 와 §16 사이 contract 가 깨집니다.

`/ha-redesign` 은 그 contract 깨짐을 해결하는 명시적 단계.

**입력**: 변경된 결정 + 근거 (rationale)
**출력**: skeleton.md / tasks.md 갱신 + `redesign_history` 에 audit trail
**상태 영향**: 현재 `pipeline.current_step` 유지 (transition 안 함). cross-cutting 스킬.

## 실행 순서

### 1. prepare — 컨텍스트 수집 + proposed 기록

```bash
python ~/.claude/skills/ha-redesign/run.py prepare \
  --decision "CEO pivot: PTT only, auto-mode dormant" \
  --rationale "/plan-ceo-review — D7 retention 우선, monetization 보류"
```

JSON 출력:
- `skeleton_sections`: 모든 §N enumeration (id + title)
- `tasks`: 모든 task ID + agent + status
- `agent_prompts.architect / .designer`: 재설계 시 사용할 시스템 프롬프트 경로
- `redesign_history_count`: 누적 redesign 개수
- `current_step`: 현재 파이프라인 단계

이 시점에 `redesign_history` 에 status="proposed" entry 1개 자동 추가됨 — 이후 단계에서
어떤 결정을 다루는지 audit trail 시작점.

### 2. Impact Analysis — Agent 위임 (model="sonnet")

prepare JSON 을 받았으면 곧바로 Impact Analysis Agent 호출. 부모는 직접 분석하지 않음.

```
Agent({
  description: "Redesign impact analysis",
  subagent_type: "general-purpose",
  model: "sonnet",
  prompt: "<아래 'Impact Analysis prompt 템플릿' 그대로 — prepare JSON 첨부>"
})
```

#### Impact Analysis prompt 템플릿

```
당신은 HarnessAI 의 Architect+Designer 합산 역할로 결정 변경의 영향을 분석합니다.
**코드 작성 또는 파일 수정 금지 — 분석 결과 JSON 만 반환하세요.**

읽기 순서 (엄수):
1. <HARNESS_AI_HOME>/backend/agents/architect/CLAUDE.md — Architect 역할 권위
2. <HARNESS_AI_HOME>/backend/agents/designer/CLAUDE.md — Designer 역할 권위
3. docs/skeleton.md — 분석 대상 (전체 본문)
4. docs/tasks.md — 영향 받을 수 있는 태스크 목록

받은 정보:
  decision: <prepare 의 --decision 값>
  rationale: <prepare 의 --rationale 값>
  prepare JSON: <위에서 받은 JSON 그대로 첨부>

분석 후 다음 형식의 JSON 만 출력:
{
  "affected_sections": ["§1", "§13", "§15"],
  "affected_section_reasons": {
    "§1": "<왜 영향 받는지 한 줄>",
    "§13": "<왜>",
    "§15": "<왜>"
  },
  "affected_tasks": ["T-200", "T-201"],
  "affected_task_reasons": {
    "T-200": "<왜>",
    "T-201": "<왜>"
  },
  "ambiguities": [
    {
      "issue": "<spec 블록과 본문 §X 간 충돌, 누락, 또는 모호점>",
      "sections_in_conflict": ["§13", "§16"],
      "needs_decision": "<무엇을 ground truth 로 할지>",
      "severity": "blocker|warning|info"
    }
  ],
  "preservation_check": [
    "<이 결정 변경으로 영향 안 받는 결정 목록 — '다른 결정 보존' 원칙 검증용>"
  ]
}

원칙:
- 영향 섹션은 최소화 — decision 과 직접 연결되는 §N 만. 보수적 추측은 ambiguity 로.
- 영향 태스크는 status 가 dormant/blocked 로 바뀌거나 spec 가 갱신될 것만.
- ambiguities 는 (4) Coder dry-run 의 흡수판 — 충돌이 보이는 즉시 기록.
- preservation_check 는 "이 결정과 무관한 다른 결정들이 그대로 유지됨" 을 명시 — 전면 재설계 방지.
```

부모 세션은 Agent 결과 (JSON) 를 받아 다음 단계로.

### 3. 사용자 승인 — AskUserQuestion

Agent 분석 결과를 사용자에게 보여주고 승인 받기. 직접 텍스트로 보여주는 게 아니라
`AskUserQuestion` 으로:

```
질문: "결정 '<decision>' 적용?"
선택지:
  [O 승인] 영향 §1, §13, §15 (3개) + 태스크 T-200, T-201 (2개) — 재설계 진행
  [X 거부] 결정 무효 — rejected 로 audit trail 만 남김
  [수정] 영향 범위 직접 조정 (텍스트 입력으로 §N 추가/제거)
```

ambiguities 가 1개 이상이면 별도 질문으로:
```
질문: "Ambiguity 처리:"
선택지:
  [모두 ground truth 로 해결 후 진행] 사용자가 텍스트로 결정 명시
  [Agent 가 보수적 해석 — affected 에 포함] 모호하면 영향 받는 것으로
  [Agent 가 진행 차단 — blocker]
```

### 4. 거부 시 — rejected lifecycle

```bash
python ~/.claude/skills/ha-redesign/run.py commit \
  --decision "<위 decision 그대로>" \
  --rationale "<위 rationale 그대로>" \
  --status rejected
```

종료. audit trail 에 "이 결정은 검토했지만 적용 안 함" 으로 보존.

### 5. 승인 시 — approved 기록

```bash
python ~/.claude/skills/ha-redesign/run.py commit \
  --decision "<...>" \
  --rationale "<...>" \
  --affected-sections "§1,§13,§15" \
  --affected-tasks "T-200,T-201" \
  --status approved
```

run.py 가 `affected_sections` 가 skeleton 에 실제 존재하는지 + `affected_tasks` 가
tasks.md 에 실제 존재하는지 검증. 잘못된 ID 면 차단. (audit 무결성 보호)

### 6. Re-derivation — Agent 위임 (model="sonnet")

승인 받은 affected 섹션/태스크 를 실제로 re-derive. 부모는 호출만.

```
Agent({
  description: "Redesign re-derivation",
  subagent_type: "general-purpose",
  model: "sonnet",
  prompt: "<아래 'Re-derivation prompt 템플릿' 그대로>"
})
```

#### Re-derivation prompt 템플릿

```
당신은 HarnessAI 의 Architect+Designer 합산 역할로 영향 섹션을 재설계합니다.

읽기 순서:
1. <HARNESS_AI_HOME>/backend/agents/architect/CLAUDE.md
2. <HARNESS_AI_HOME>/backend/agents/designer/CLAUDE.md
3. docs/skeleton.md — 전체 본문 (다른 결정 보존을 위한 컨텍스트)
4. docs/tasks.md — affected_tasks 의 현재 spec
5. <approved 단계의 affected_sections + affected_tasks + decision + rationale>

작업:
- 각 affected_sections 에 대해, decision/rationale 에 맞춰 **해당 섹션 본문만** 재작성.
  · 다른 섹션 (affected 에 안 들어간) 은 절대 손대지 마세요.
  · 같은 섹션 안에서도 decision 과 무관한 부분은 보존.
- 각 affected_tasks 에 대해 status / depends_on / spec 갱신.
  · 새 태스크 추가는 별도 결정 — 이번 작업 범위 X.
- skeleton.md 와 tasks.md 를 Edit tool 로 직접 수정.
  · 변경한 섹션마다 1-line 이력 코멘트 추가:
    "<!-- ha-redesign 2026-05-09: <decision> — affected via /ha-redesign -->"

원칙:
- 다른 결정 보존: 영향 안 받는 §N / 태스크는 0 변경.
- audit 가능성: 변경한 줄마다 이유 추적 가능해야 함.
- 의미적 일관성: §13 컴포넌트 → §14 상태 머신 → §15 의사 코드 cross-ref 깨지지 않도록.
- 출력은 Edit tool 로 직접 적용 — 부모에게 markdown 던지지 마세요.

작업 완료 후 다음 형식의 JSON 으로 부모에게 보고:
{
  "edited_files": ["docs/skeleton.md", "docs/tasks.md"],
  "sections_modified": ["§1", "§13", "§15"],
  "tasks_modified": ["T-200", "T-201"],
  "preservation_verified": true,
  "notes": "<특이사항 또는 fallback 결정>"
}
```

### 6-b. done 태스크 코드 재실행 여부 결정 (필수)

Re-derivation 완료 후, `affected_tasks` 중 `status=done` 인 태스크가 있으면 코드는 이미
작성됐지만 스펙이 바뀐 상태입니다. **이를 방치하면 silent spec drift** — 코드와 스펙이 조용히 불일치함.

done 태스크가 1개 이상이면 **반드시** AskUserQuestion:

```
질문: "재설계로 다음 완료 태스크의 스펙이 변경되었습니다. 코드 재작업이 필요합니까?"

  T-200 (<설명>): <변경된 내용 한 줄 요약>
  T-201 (<설명>): <변경된 내용 한 줄 요약>

선택지:
  [재작업 필요]       tasks.md 에서 status "대기" 로 재설정 → applied 후 /ha-build 재실행
  [무시 (의도적)]     reason 기록 후 진행 (코드-스펙 불일치 허용 선언)
  [태스크별 개별 결정] 각 done 태스크마다 위 두 옵션 중 선택
```

**[재작업 필요] 선택 시**:
- tasks.md 에서 해당 태스크 행 status 를 `"대기"` 로 Edit tool 로 직접 수정
- applied commit 이후 `/ha-build T-NNN` 으로 재구현

affected_tasks 중 done 이 없으면 이 단계 skip.

### 7. applied 기록 + consistency check

Agent 가 skeleton.md / tasks.md 를 수정한 후, 부모는 마지막 lifecycle 기록:

```bash
python ~/.claude/skills/ha-redesign/run.py commit \
  --decision "<...>" \
  --rationale "<...>" \
  --affected-sections "§1,§13,§15" \
  --affected-tasks "T-200,T-201" \
  --status applied
```

run.py 가 다시 한 번 검증:
1. `applied` 시점의 skeleton 에 §1/§13/§15 가 여전히 존재해야 함 (재설계 후 헤딩 보존).
2. **Cross-section consistency 자동 검증** — 재설계 결과의 drift 를 출력 JSON 의
   `consistency_findings` 로 보고:
   - `isolated-component` (info): §13 에 정의된 컴포넌트가 §14/§15 에 reference 없음.
     → 상태 머신 wiring 또는 의사 코드 누락 가능성.
   - `task-no-reference` (warn): 태스크 description 에 §N 또는 §13 컴포넌트 reference 없음.
     → 구현자가 anchor 없이 작업 → spec drift 위험.
   - finding 은 **블로킹 안 함** (advisory). 하지만 부모/사용자가 보고 처리할 책임.

## 가드레일

- **부모는 직접 분석/수정 금지**: Impact analysis + Re-derivation 둘 다 Agent 위임.
- **다른 결정 보존**: affected 에 들어간 섹션만 갱신. 나머지 §N 은 손대지 않음.
- **audit trail**: rejected 도 history 에 남김 — 검토했지만 적용 안 한 결정 추적.
- **forward 상태 유지**: redesign 은 `current_step` 안 바꿈.
- **post-build redesign 시 주의**: affected_tasks 가 done 인 경우 단계 6-b 에서 반드시
  사용자 확인. [재작업 필요] 선택 시 tasks.md status "대기" 재설정 → /ha-build 재실행.
  이 단계를 건너뛰면 코드-스펙 불일치(silent spec drift) 가 발생함.
- **HarnessAI 결정권 분리** (`user_harnessai_decision_authority.md`):
  - AI: 영향 분석 + 재설계 안 제안 + 실제 편집 (위임받은 영역)
  - 사용자: 승인/거부/수정 + 코드 스타일 영역
  - **모든 lifecycle 전이는 명시적 commit** — 자동 적용 금지.

## 트러블슈팅

**"current step is init" 차단**: `/ha-init` + `/ha-design` 먼저. init 상태에선 redesign 할 게 없음.

**affected_sections 가 §1 형식이 아닐 때**: skeleton 의 헤딩 형식 (`## N. 제목`) 이 깨졌을 가능성. 헤딩 정규식 수동 검토.

**proposed entry 가 누적되기만 함**: prepare 만 호출하고 commit 안 하면 history 에 proposed 가 쌓임. 의도적 — 검토 중인 변경 여러 개일 수 있음. commit 시 같은 decision 라벨로 묶임.

**Agent 가 affected 에 §99 같은 가짜 섹션 반환**: run.py commit 의 검증이 차단. Agent prompt 의 "skeleton 에 실제 존재하는 §N 만" 룰 강조 필요.

**Re-derivation Agent 가 다른 섹션 건드림**: preservation 위반. git diff 로 확인 후 차단.
SKILL.md 의 "다른 결정 보존" 룰을 Agent prompt 에 강하게 박아둔 이유.

## 메모리/룰 호환성

- `feedback_holistic_thinking.md`: 파이프라인/문서 수정 시 전체 설계 점검 — 본 스킬이 시스템 구현체.
- `user_harnessai_decision_authority.md`: AI 분석/제안, 사용자 승인 — Agent 위임 + AskUserQuestion 흐름이 이 분리 유지.
- `feedback_external_focus.md`: HarnessAI 코드 추가 금지 — 본 스킬은 mutation propagation 결함 해결을 위한 v0.7.0 시스템 fix 로 예외 적용 (2026-05-09 명시 결정).
- `feedback_sonnet_for_coding.md`: 코드 작성 Sonnet 위임 — Impact analysis + Re-derivation 모두 Agent(model="sonnet").
- `feedback_comment_language.md`: 코드 주석 영어, 사용자 메시지 한국어 — run.py / Agent prompt 둘 다 적용.
