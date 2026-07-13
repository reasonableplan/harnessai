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
  ],
  "nfr_conflicts": [
    {
      "decision_part": "<새 결정이 도입하는 의존성/외부호출/런타임 동작>",
      "violates": "<위반하는 skeleton 제약: §보안(시크릿)·§네트워크/오프라인·기타 NFR>",
      "severity": "blocker|warning"
    }
  ]
}

원칙:
- 영향 섹션은 최소화 — decision 과 직접 연결되는 §N 만. 보수적 추측은 ambiguity 로.
- 영향 태스크는 status 가 dormant/blocked 로 바뀌거나 spec 가 갱신될 것만.
- ambiguities 는 (4) Coder dry-run 의 흡수판 — 충돌이 보이는 즉시 기록.
- preservation_check 는 "이 결정과 무관한 다른 결정들이 그대로 유지됨" 을 명시 — 전면 재설계 방지.
- **nfr_conflicts (필수, #10)**: 새 결정이 도입하는 **의존성·외부호출·런타임 동작**이 skeleton 의
  보안(시크릿 금지)·네트워크/오프라인·기타 NFR 제약을 위반하는지 **명시 검사**. 예: 오프라인
  선언 프로젝트에 런타임 그래마/모델을 네트워크 다운로드하는 패키지 채택 = blocker. preservation_check
  에 제약을 넣고도 위반 검증을 빠뜨리는 게 #10 의 결함 — 절차 완결만으로 내용 위반을 통과시키지 말 것.
  blocker 가 있으면 사용자 승인 전 반드시 표면화(대안 패키지/제약 완화 결정).
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
- 표기 규칙: 코드 인자/예시 값은 백틱으로 감싸기 (예: `["sh","-c","script_body"]`). 본문에 `<...>` 형태의 placeholder 모양 토큰을 쓰지 마세요 — integrity 게이트가 미치환 placeholder 로 오인해 FAIL 처리합니다.
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

**v0.10.0**: `--status applied` commit 후 worklog.md (docs/worklog.md) 에 변경 자동 append 됨.

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

### 8. (선택) 전체 태스크 재분해 — `/ha-plan --replan`

위 6단계의 re-derivation 은 affected 태스크만 **surgical Edit** 한다. 결정 변경의 여파가
태스크 구조 전반(Phase 재배치, 의존성 그래프 재구성)에 미친다면, applied 후 태스크를
**통째로 다시 분해**하는 게 낫다:

```bash
python ~/.claude/skills/ha-plan/run.py prepare --replan
python ~/.claude/skills/ha-plan/run.py commit --replan --tasks-content "..."
```

`--replan` 은 ha-redesign 이 유지한 `planned` 상태에서 ha-plan 재실행을 허용한다 (issue #2).
**주의**: tasks.md 를 덮어쓰므로 보존할 done/needs_rebuild 상태를 tasks-content 에 반영할 것.
소규모 변경이면 6단계 surgical Edit 로 충분 — `--replan` 은 대규모 재구성용.

## 작업 일지 자동 기록 (worklog)

run.py 가 applied commit 시 박는 메타 1줄 (`decision=..., sections=...`) 과 **별개로**, 이
스킬 작업 중 부모 세션이 판단해서 의미 있는 변경을 `ha-log` 로 worklog.md 에 박는다.

**재설계 도중 — 그때그때**: 사용자가 다음을 주면 처리 완료 직후 1줄 요약을 박는다.
- 영향 범위 조정 ("§N 도 포함시켜", "T-XXX 는 빼")
- ambiguity 해소 결정 (어느 쪽을 ground truth 로)
- 추가 수정 요청

```bash
python ~/.claude/skills/ha-log/run.py append \
  --category change \
  --message "<무엇을 왜 바꿨는지 한 줄>" \
  --project "<프로젝트 루트 — docs/ 의 상위>"
```

카테고리: 수정/버그 → `change`, 결정/논의 → `discussion`, 다음 할 일 → `next`.

**제외 (노이즈 차단)**: 오타·포맷·표현 수정, 단순 질문/잡담, run.py 가 이미 박는 applied 메타.

**세션 마무리 — "오늘 끝 / 마무리 / 오늘 한 일 정리" 신호 시**: 이 세션에서 한 작업을
카테고리별로 모아 worklog 에 박는다 (항목마다 append 1회 호출). 구현/수정 → `change`,
정한 것 → `discussion`, 다음 할 것 → `next`. 박은 뒤 "오늘 N건 일지 기록" 1줄 보고.

## 가드레일

- **부모는 직접 분석/수정 금지**: Impact analysis + Re-derivation 둘 다 Agent 위임.
- **다른 결정 보존**: affected 에 들어간 섹션만 갱신. 나머지 §N 은 손대지 않음.
- **audit trail**: rejected 도 history 에 남김 — 검토했지만 적용 안 한 결정 추적.
- **forward 상태 유지**: redesign 은 `current_step` 안 바꿈.
- **post-build stale 자동 가드**: `applied` 시 `affected_tasks` 중 status=`done` 인
  태스크는 **run.py 가 자동으로 `needs_rebuild` 로 전이**한다. 이는 재설계로 spec 이 바뀐
  stale 코드가 재빌드 없이 `/ha-verify` 를 그대로 통과하는 것을 막는 안전 가드다 —
  `/ha-build --resume` 은 done 태스크를 재선택하지 않으므로, 상태를 내려야 재빌드 대상이 된다.
  전이된 태스크 목록은 stdout JSON 의 `rebuild_required_tasks` 필드로 보고된다.
  **추가 (F3)**: run.py 가 섹션별 hash 를 diff 해, agent 의 `affected_tasks` 에서 빠졌지만
  변경 섹션을 `skeleton 참조` 로 가리키는 task 를 **결정론적으로 파생**해 합산한다
  (`hash_derived_rebuild_candidates` 필드) — agent recall 누락에 대한 안전망.
- **HarnessAI 결정권 분리** (`user_harnessai_decision_authority.md`):
  - AI: 영향 분석 + 재설계 안 제안 + 실제 편집 (위임받은 영역)
  - 사용자: 승인/거부/수정 + 코드 스타일 영역
  - **모든 lifecycle 전이는 명시적 commit** — 자동 적용 금지.

## 트러블슈팅

**plan 자체가 stale (legacy compute)**: 먼저 `harness migrate-plan` 으로 plan 정정 후 ha-redesign 진행.
- `python ~/.claude/harness/bin/harness migrate-plan <project-dir>/docs/harness-plan.md` (dry-run)
- 확인 후 `--apply` 로 적용. 자동 백업 생성됨.
- skeleton.md 의 stale 섹션은 /ha-redesign 이 정리.
- `--mark-skeleton-stale` 옵션으로 removed 섹션에 자동 마커 삽입 가능:
  `python ~/.claude/harness/bin/harness migrate-plan <plan> --mark-skeleton-stale` (dry-run, `skeleton_will_mark` 미리보기)
  `python ~/.claude/harness/bin/harness migrate-plan <plan> --apply --mark-skeleton-stale` (실제 삽입 + 자동 백업)

**STALE 마커 발견 (`<!-- STALE: ... -->`)**: `migrate-plan --mark-skeleton-stale` 로 마킹된 섹션.
- 해당 섹션 본문 검토 후 제거 (활성 profile 에서 완전히 빠진 경우) — `/ha-redesign` 이 정리.
- 또는 `<!-- STALE ... -->` 주석 라인만 삭제 (paired profile 추가 예정이라 본문 유지 의도).
- 마커 형식: `<!-- STALE: 이 섹션은 더 이상 활성 아님 (migrate-plan YYYY-MM-DD). ... -->`

**"current step is init" 차단**: `/ha-init` + `/ha-design` 먼저. init 상태에선 redesign 할 게 없음.

**affected_sections 가 §1 형식이 아닐 때**: skeleton 의 헤딩 형식 (`## N. 제목`) 이 깨졌을 가능성. 헤딩 정규식 수동 검토.

**proposed entry 가 누적되기만 함**: prepare 만 호출하고 commit 안 하면 history 에 proposed 가 쌓임. 의도적 — 검토 중인 변경 여러 개일 수 있음. commit 시 같은 decision 라벨로 묶임.

**Agent 가 affected 에 §99 같은 가짜 섹션 반환**: run.py commit 의 검증이 차단. Agent prompt 의 "skeleton 에 실제 존재하는 §N 만" 룰 강조 필요.

**Re-derivation Agent 가 다른 섹션 건드림**: preservation 위반. git diff 로 확인 후 차단.
SKILL.md 의 "다른 결정 보존" 룰을 Agent prompt 에 강하게 박아둔 이유.

**`needs_rebuild` 된 task 처리**: `/ha-build complete --task T-XXX --status done` 으로
재구현 후 마킹. 또는 사용자가 stale 이 아님을 확인하고 직접 tasks.md 의 status 를
`done` 으로 되돌릴 수 있음 (명시적 결정). `/ha-build --resume` 은 `needs_rebuild` 를
**최우선으로 선택**하므로 (done 은 재선택하지 않는다) 반드시 재실행 대상이 된다.

## 메모리/룰 호환성

- `feedback_holistic_thinking.md`: 파이프라인/문서 수정 시 전체 설계 점검 — 본 스킬이 시스템 구현체.
- `user_harnessai_decision_authority.md`: AI 분석/제안, 사용자 승인 — Agent 위임 + AskUserQuestion 흐름이 이 분리 유지.
- `feedback_external_focus.md`: HarnessAI 코드 추가 금지 — 본 스킬은 mutation propagation 결함 해결을 위한 v0.7.0 시스템 fix 로 예외 적용 (2026-05-09 명시 결정).
- `feedback_sonnet_for_coding.md`: 코드 작성 Sonnet 위임 — Impact analysis + Re-derivation 모두 Agent(model="sonnet").
- `feedback_comment_language.md`: 코드 주석 영어, 사용자 메시지 한국어 — run.py / Agent prompt 둘 다 적용.
