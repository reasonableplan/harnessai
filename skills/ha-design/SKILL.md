---
name: ha-design
description: |
  HarnessAI v2 — skeleton 섹션 채우기 (Architect + Designer 역할).
  /ha-init 결과물(빈 skeleton.md)을 받아 사용자와 인터뷰 + 판단으로 채운다.
  Use when: /ha-init 완료 후, "skeleton 채우자", "/ha-design"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - AskUserQuestion
---

## 역할

`/ha-init` 이 만든 빈 skeleton 의 placeholder 들을 실제 프로젝트 맞춤 내용으로 채운다.
Claude 가 직접 Architect + Designer 두 역할을 순차로 수행 (subprocess agent X).

**입력**: `docs/skeleton.md` (빈 템플릿) + `docs/harness-plan.md` (의사결정 컨텍스트)
**출력**: `docs/skeleton.md` (채워진 상태)
**다음**: `/ha-plan`

## 실행 순서

### 1. 사전 조건 + 컨텍스트 로드

```bash
python ~/.claude/skills/ha-design/run.py prepare
```

run.py 가 다음 검증/출력 (JSON):
- `current_step` 이 "init" 인지 (아니면 에러)
- `included_sections` (채워야 할 섹션 ID 목록)
- `activation_trace` (`{section_id: required_when_expression}` — 각 활성 섹션이 어떤 표현식에 의해 활성됐는지. 빈 dict 면 legacy plan — cross-check 불가)
- `profiles` (활성 프로파일 정보 + body 경로)
- `agent_prompts` (architect/designer CLAUDE.md 절대 경로)
- `skeleton_path`, `plan_path`

### 2. 에이전트 프롬프트 + skeleton 본문 로드

Read 로 (순서 엄수):
- `<HARNESS_AI_HOME>/backend/docs/shared-lessons.md` — **반드시 가장 먼저 읽는다.** 과거 실수 패턴 (LESSON-NNN) 숙지 후 설계. 특히 auth 섹션 작성 전 LESSON-022~027 필수.
  - **v0.10.0 Pending Lessons 검토 (필수)**: 파일 끝에 `## Pending Lessons (자동 추출 — 사용자 promotion 대기)` 섹션이 있으면 *AskUserQuestion 으로 promotion 여부* 묻기. 가치 있으면 → main 섹션으로 이동 + `auto_extracted` 마커 제거 (promote) / 가치 없으면 → 블록 삭제 (reject). 검토 안 하면 매 /ha-design 마다 같은 안내 박힘.
- `<agent_prompts.architect>` (Architect 역할 프롬프트)
- `<agent_prompts.designer>` (Designer 역할 프롬프트)
- 활성 프로파일 본문들 (각 프로파일 .md 의 frontmatter 이외 부분 — components 가이드, 금지사항 등)
- `<skeleton_path>` (현재 skeleton.md)
- `<plan_path>` (사용자 설명, 판단 근거)
- `docs/conventions.md` — **존재하면 반드시 읽는다.** 사용자 정의 스타일이 skeleton 의 모든 기술 결정에 우선함. 없으면 skip.
- `<plan.activation_trace>` — 각 included 섹션이 어떤 trigger 로 활성됐는지. 모순 감지의 1차 컨텍스트.

### 2.5. Activation trace 검토 (cross-check)

prepare 출력의 `consistency_violations` 필드를 직접 읽어 사용자에게 보여준다.
이 필드는 run.py 가 `find_consistency_violations()` 로 deterministic 하게 계산한 결과다
(Claude 판단 아님 — 코드 레벨 검증).

**처리 흐름**:

- `consistency_violations` 가 빈 리스트 → §3 으로 바로 진행.
- `consistency_violations` 가 비어있지 않으면:
  - 사용자에게 위반 목록을 표시:
    ```
    ⚠️ 정합성 경고 N건:
      - <section_id>: <trigger_expression>
        필요: has.<missing_atom>, 제공 가능 프로파일: <expected_providers>
    ```
  - AskUserQuestion 으로 명시 승인:
    - `그대로 진행 (의도적)` — 외부 백엔드 별도 관리 등 의도적 모순. §3 으로 진행. §19 구현 노트 "결정 로그" 에 기록 권고.
    - `/ha-init 으로 돌아가서 프로파일 수정` — 스킬 종료, 사용자에게 ha-init 재실행 안내.
    - `취소` — 저장 없이 종료.

- trace 비어있음 (legacy plan):
  → 경고: "trace 없음 — cross-check 불가. ha-init 재실행 또는 수동 정합성 검토 권장."
  → consistency_violations 검사 skip — §3 으로 진행.

**중요**: consistency_violations 가 있으면 사용자에게 반드시 명시적으로 보여줄 것 — 자동으로 무시 금지.

(만약 사용자가 "그대로 진행" 선택 시 → §3 으로 넘어감)

---

### 2.7. HITL gate — LOCKED 섹션 후보 인터뷰 (v0.10.0)

`prepare` 출력의 `locked_section_ids` 가 비어있지 않으면 **반드시** 다음 흐름 수행. AI 추측으로 채우기 금지.

LOCKED 대상 섹션:
- `requirements` — 기능 요구사항 (페르소나/시나리오 기반)
- `user_journey` — 페르소나 + 핵심 시나리오
- `view.screens` — 화면 + 디자인 레퍼런스 URL

#### 흐름 (각 LOCKED 섹션마다 반복)

**Step A — AI 후보 5 개 생성**
- 입력: user_description + 활성 프로파일 + 이미 채워진 이전 LOCKED 섹션 (페르소나 → 시나리오 → 화면 순)
- 출력: 5 개 *구체적* 후보. 한 줄 요약 + 근거 (어느 페르소나 / 시나리오에서 왔는지)
- 후보 양식: fragment 의 `### AI 제안 후보` 표 그대로 채움

**Step B — AskUserQuestion 으로 사용자 선택**
```
질문: "<섹션 이름> 에서 어떤 후보를 확정할까요? (여러 개 가능)"
options:
  - 후보 1: <한 줄>
  - 후보 2: <한 줄>
  - 후보 3: <한 줄>
  - 후보 4: <한 줄>
  - 후보 5: <한 줄>
multiSelect: true (requirements / user_journey 페르소나)
multiSelect: false (디자인 레퍼런스 — 1 개 출처만)
```

**Step C — 응답 처리**
- 1+ 선택 → fragment 의 *확정* 섹션 (예: `### 확정 기능 (사용자 선택 결과)`) 에 박음. AI 후보 슬롯은 그대로 둠 (audit 용).
- "Other" 선택 (사용자 직접 입력) → 입력 내용 그대로 박음.
- 사용자가 명확히 "AI 가 알아서 채워" 라고 함 → §2.7-AI 분기 진입.

**§2.7-AI 분기 — `--ai-draft` 옵트인**

다음 흐름 강제:
1. AskUserQuestion 으로 *재확인*: "AI 가 추측으로 채우면 LESSON-014 재발 가능 (Designer 가 색상 직접 정의 → 밋밋). 정말 진행?"
   - "예 — 나중에 검토" → 진행. 해당 섹션 ID 를 `ai_drafted_sections` 누적 (commit 시 박음).
   - "아니오 — 다시 인터뷰" → Step B 재시도.

2. AI 가 5 개 후보 중 *best 1-3* 박음. fragment 의 *확정* 섹션에 박되 *맨 위에 ⚠️ AI-DRAFTED* 표시.

#### 특별 가드 — `view.screens` 의 디자인 레퍼런스

URL 미입력 시 인터뷰 강제 1 회 추가:
- "디자인 레퍼런스 URL 없이 진행 = LESSON-014 재발 (밋밋). 다음 중 선택:"
  - "shadcn/ui 기본 사용 (가장 안전)" → fragment 에 `https://ui.shadcn.com` 박음
  - "Mobbin 검색 후 1 개 박음" → 사용자 입력 받음
  - "Dribbble 검색 후 1 개 박음" → 사용자 입력 받음

#### 누적 추적

LOCKED 섹션 채울 때마다:
- `locked_done: list[str]` 누적 (예: `["requirements", "user_journey"]`)
- `ai_drafted: list[str]` 누적 (사용자 옵트인 섹션만)

§5 commit 단계에서 두 리스트를 인자로 전달.

**세션 유실 시 복구**: Claude Code 세션이 중단되면 `run.py prepare` 재실행. 이미 채워진 LOCKED 섹션은 fragment 의 AI 후보 표 + 확정 섹션 텍스트로 식별 가능 — 빈 부분만 이어서 채움. `--ai-draft` 옵트인했던 섹션은 frontmatter `ai_drafted_sections` 에서 확인.

---

### 3. 섹션별 채우기 (1패스)

`included_sections` 의 각 섹션에 대해:

**섹션 owner 결정** (어느 역할이 책임지는가):
- `auth`, `persistence`, `interface.http`, `interface.cli`, `interface.ipc`, `interface.sdk`, `errors`, `state.flow`, `core.logic`, `configuration`, `integrations`, `observability`, `deployment` → **Architect**
- `view.screens`, `view.components` → **Designer**
- `overview`, `requirements`, `stack` → **둘 다 협의** (Architect 가 초안, Designer 검토)
- `tasks`, `notes` → 비워둔다 (각각 /ha-plan, /ha-build 가 채움)

**채우는 방법**:
- 해당 섹션의 placeholder 를 사용자 설명 + 프로파일 본문 가이드 + LESSON 들을 종합해서 실제 내용으로 교체
- 빈 표는 행 추가, `<예: ...>` 는 실제 값으로 대체
- 작성 가이드(`> ...` 블록)는 결과물에서 제거

**섹션 "충분히 채워짐" 기준** (다음 섹션으로 넘어가기 전 확인):
- [ ] `<...>` placeholder 0개
- [ ] 표의 모든 행이 실제 값으로 채워짐 (DB 컬럼은 타입·제약 명시, API 는 method+path+schema 모두)
- [ ] 에러 코드 섹션: 코드 ID + HTTP status + 설명 3종 세트 완비
- [ ] `persistence` 섹션: **Mermaid ER 다이어그램 포함** (테이블 정의 앞에 위치)
- 분량보다 **구체성** 기준 — "Users 테이블" 이 아니라 "id(PK)/email(unique,not null)/token_version(int,default=0)"

**`auth` 섹션 보안 체크리스트 (작성 완료 전 전부 확인)**:
- [ ] JWT payload 에 `type` ("access"/"refresh") + `ver` (token_version) 두 claim 포함 (LESSON-022)
- [ ] User 모델에 `token_version: int` 필드 존재 (LESSON-023)
- [ ] logout 이 서버에서 `token_version` 증가 — no-op 절대 금지 (LESSON-023)
- [ ] refresh endpoint 가 httponly 쿠키 전용 — body.refresh_token 수락 금지 (LESSON-024)
- [ ] accessToken 저장 방법이 **인메모리** — localStorage/sessionStorage/AsyncStorage/SharedPreferences/UserDefaults 금지 (LESSON-027)

**`view.*` 섹션 보안 체크리스트**:
- [ ] 토큰 저장 위치가 localStorage/sessionStorage 로 명시된 부분 없는지 확인
- [ ] 모바일의 경우 SecureStore(RN) / flutter_secure_storage / Android Keystore / iOS Keychain 사용 명시

**중간에 사용자 질문** (선택적, AskUserQuestion):
- 정보 부족한 부분만 (예: "비밀번호 정책은? 8자 이상 / 12자 이상 / 사용자 자유")
- 질문 5개 이하

---

### 3.5. 사용자 확인 gate (Human-in-the-Loop)

다음 섹션은 완료 즉시 **AskUserQuestion 으로 사용자 확인을 받는다.**
사용자가 "수정 요청" 선택 시 → 수정 후 재확인 (최대 2회). 2회 초과 시 해당 섹션 맨 아래에 `<!-- TODO: <미결 내용> -->` 주석으로 기록 후 진행. (`tasks`/`notes` 섹션에는 절대 쓰지 말 것)

#### 백엔드 gate

**`persistence` 완료 후** (included_sections 에 있을 때만 적용)
```
[확인 내용]
- Mermaid ER 다이어그램 (작성한 것 그대로)
- 테이블 수 / 주요 관계 요약

[질문]
"DB 스키마가 맞습니까? 컬럼이나 관계에서 수정할 부분이 있으면 알려주세요."

[선택지]
- 승인 — 다음 섹션으로 진행
- 수정 요청 (Other 로 수정 내용 입력)
```

**`auth` 완료 후** (included_sections 에 있을 때만 적용)
```
[확인 내용]
- 인증 방식 (JWT / 세션쿠키 / OAuth)
- Access token 수명 + 저장 위치

[프론트엔드/모바일 프로파일이 포함된 경우만 추가 확인]
- Silent refresh 전략 (방식 + 동시 요청 처리)
- 세션 만료 UX (만료 시 동작)
- 탭 간 동기화 여부 (웹 only)

[질문]
"인증 방식과 세션 관리 전략이 맞습니까?"
(백엔드 단독 프로젝트면 silent refresh / 탭 동기화 항목 생략)

[선택지]
- 승인
- 수정 요청 (Other 로 수정 내용 입력)
```

**`interface.http` 완료 후** (included_sections 에 있을 때만 적용)
```
[확인 내용]
- API 엔드포인트 표 (Method / Path / 인증 여부 / 간략 설명)
- rate_limiting 섹션이 있으면 주요 제한값 함께 표시

[질문]
"API 목록이 맞습니까? 빠진 엔드포인트나 수정할 것이 있으면 알려주세요."

[선택지]
- 승인
- 수정 요청 (Other 로 수정 내용 입력)
```

**`environments` 완료 후** (included_sections 에 있을 때만 적용)
```
[확인 내용]
- 환경 목록 (dev / staging / prod)
- 환경별 주요 설정 차이 표
- CORS 허용 origin

[질문]
"환경 분리 설정이 맞습니까? 수정할 부분이 있으면 알려주세요."

[선택지]
- 승인
- 수정 요청 (Other 로 수정 내용 입력)
```

#### 프론트엔드 gate

**`view.screens` 완료 후** (included_sections 에 있을 때만 적용)
```
[확인 내용]
- 화면 목록 + 라우트 구조
- 각 화면의 접근 권한 (public / 인증 필요)

[질문]
"화면 목록과 라우트 구조가 맞습니까? 빠진 화면이나 수정할 것이 있으면 알려주세요."

[선택지]
- 승인
- 수정 요청 (Other 로 수정 내용 입력)
```

**`error_ux` 완료 후** (included_sections 에 있을 때만 적용)
```
[확인 내용]
- 에러 유형별 표시 방식 표
- retry 전략
- 에러 바운더리 범위

[질문]
"에러 처리 UX 전략이 맞습니까? 특정 에러를 다르게 처리할 것이 있으면 알려주세요."

[선택지]
- 승인
- 수정 요청 (Other 로 수정 내용 입력)
```

#### 모바일 gate

**`mobile.navigation` 완료 후** (included_sections 에 있을 때만 적용)
```
[확인 내용]
- 화면 목록 + 탭/스택 구조
- 딥링크 처리 여부

[질문]
"앱 화면 구조가 맞습니까? 수정할 부분이 있으면 알려주세요."

[선택지]
- 승인
- 수정 요청 (Other 로 수정 내용 입력)
```

**`mobile.lifecycle` 완료 후** (included_sections 에 있을 때만 적용)
```
[확인 내용]
- 권한 매트릭스 (권한명 / 사용처 / 요청 시점)
- 앱 상태 전환 시 동작

[질문]
"앱 권한 요청과 상태 관리 전략이 맞습니까?"

[선택지]
- 승인
- 수정 요청 (Other 로 수정 내용 입력)
```

gate 가 없는 섹션 (`errors`, `view.components`, `state.flow`, `core.logic`, `configuration`, `observability`, `deployment`) 은 자율 설계 후 바로 다음 섹션으로 진행.

---

### 4. 충돌 검토 (Designer ↔ Architect)

Designer 섹션 (view.*) 작성 후, 그 화면이 요구하는 데이터/액션이 Architect 가 작성한 `interface.http` / `auth` / `state.flow` 에서 모두 제공되는지 확인.

미충족 발견 시:
- `interface.http` 섹션에 새 엔드포인트 추가 (Architect 역할 재진입)
- 또는 `state.flow` 에 새 전이 규칙 추가
- (정말 안 되면 Designer 가 view 수정)

최대 3 라운드. 3라운드 후 미충족 항목이 남으면:
- 미충족 항목을 해당 섹션 맨 아래에 `<!-- TODO: <항목> -->` 로 인라인 기록 (`notes` 섹션 금지)
- commit 진행 + 다음 단계 안내에서 사용자에게 명시 ("미결 N개: …")
- **에스컬레이션하지 않고** best-effort 로 진행 — 완성도보다 전진 우선

### 5. 저장 + 상태 전이

```bash
python ~/.claude/skills/ha-design/run.py commit \
  --skeleton-path "<path>" \
  --locked-sections requirements user_journey view.screens \
  --ai-drafted-sections "<섹션 ID 목록 — 옵트인된 것만, 없으면 인자 생략>" \
  --ai-draft  # ai-drafted-sections 가 있을 때만 박음
```

run.py 가:
- 채워진 skeleton.md 의 placeholder 잔재 검사 (`<...>` 패턴 카운트, 0 이 아니면 경고)
- **LESSON 인용 검증**: 본문에 인용된 `LESSON-NNN` 형식 ID 가 `shared-lessons.md` 에 실제 정의됐는지 검증. 미정의 ID 발견 시 **exit code 1 로 차단** (stderr 에 미정의 목록 출력). 의도적 인용이면 `--allow-unknown-lessons` flag 사용 (경고만 + 진행).
- harness validate 로 plan 무결성 재확인
- `current_step` "init" → "designed" 전이
- `completed_steps += ["ha-design"]`
- last_activity 갱신
- harness-plan.md 저장

commit 출력 JSON 에 `unknown_lesson_references` 필드가 항상 포함됨 (성공/실패 모두).
`shared-lessons.md` 파일 자체가 없으면 LESSON 검증 skip + stderr 경고 (외부 환경 호환).

**v0.10.0 HITL freeze**:
- `--locked-sections` 인자 — §2.7 에서 인터뷰 통과한 섹션 ID 목록. plan.freeze() 호출 → frozen_status="frozen".
- `--ai-drafted-sections` + `--ai-draft` — §2.7-AI 분기로 채운 섹션. 사용자 후속 promotion 필요.
- frozen_status="frozen" 이 박혀야 다음 단계 `/ha-build` 진입 가능.
- **v0.10.0**: commit 후 worklog.md (docs/worklog.md) 에 변경 자동 append 됨.

### 6. 다음 단계 안내

```
✅ /ha-design 완료

채워진 섹션 (N): <목록>
미해결 placeholder: <0 또는 개수+위치>

다음 단계:
  /ha-plan — 태스크 분해
  (선택) /plan-eng-review — 설계 검토 (gstack)
```

### 출력의 guideline_paths 도 읽으세요

`prepare` 출력 JSON 의 `profiles[].guideline_paths` 에
프로파일별 컨벤션 문서 경로가 포함됩니다. **반드시 작업 시작 전 모두 읽으세요**:

- `react-native-expo`: navigation/state/storage/style 4 파일 — Expo Router + Zustand + SecureStore 컨벤션
- `flutter`: navigation/state/storage/style 4 파일 — go_router + Riverpod + drift + ThemeData
- `android-kotlin`: architecture/compose/network/storage 4 파일 — MVVM + Compose + Retrofit + Room
- `ios-swift`: architecture/swiftui/network/storage 4 파일 — MV pattern + SwiftUI + URLSession + Keychain
- `fastapi`: api/services/structure 3 파일 — Clean Arch + DI + 패키지 구조

**모바일 사용자**: 위 가이드라인을 안 읽으면 LESSON-STYLE-001 / 보안 위반 / 컨벤션 drift 가능성. 시스템 프롬프트만으로는 부족합니다.

## 가드레일

- 사용자 설명에 없는 기능을 **추가하지 말 것** (over-engineering 방지)
- 프로파일 화이트리스트 외 라이브러리 명시 금지
- 작성 가이드 (`> 작성 가이드:`) 블록은 결과에서 **반드시 제거** (사용자 가이드는 임시 도움말)
- skeleton 의 `## N. <title>` 헤딩과 섹션 번호는 변경 금지 (다른 도구가 파싱)
- `tasks` / `notes` 섹션은 절대 채우지 말 것 (각각 /ha-plan, /ha-build 영역)

## 트러블슈팅

**"current_step != init"**: `/ha-init` 부터 다시. 또는 이미 designed 라면 `--reset` (run.py 미지원 시 수동 backup 후 init 으로 되돌리기).

**미해결 placeholder 가 많음**: 사용자 설명이 부족했을 가능성. `/ha-init` 로 돌아가서 더 구체적으로 작성.

**Unknown LESSON references**: `LESSON-22`, `LESSON-999` 등 미정의 LESSON ID — `shared-lessons.md` 에 정의 없음. 해결 방법:
1. skeleton.md 본문에서 인용 제거 (zero-padded 오타라면 수정: `LESSON-022`)
2. 실제 LESSON 을 `shared-lessons.md` 에 추가 후 재시도
3. 의도적 인용 (아직 미작성된 LESSON) 이면 `--allow-unknown-lessons` flag:
   ```bash
   python ~/.claude/skills/ha-design/run.py commit --allow-unknown-lessons
   ```

## 모바일 프로젝트 사용 예시 (Flutter)

**2단계 — `/ha-design` 에서 skeleton 채우기**:

- `/ha-init` 완료 후 `docs/skeleton.md` (빈 템플릿) 확인
- `guideline_paths` 의 flutter/navigation.md, state.md, storage.md, style.md 모두 읽기
- skeleton 의 `mobile.navigation` 섹션: go_router 기반 라우팅 구조 채움
- skeleton 의 `state.flow` 섹션: Riverpod Provider 계층 + 상태 흐름 채움
- skeleton 의 `persistence` 섹션 (data_sensitivity=pii 시 자동 포함): drift DB 스키마 + flutter_secure_storage 토큰 저장 방법 채움

**react-native-expo 의 경우**:
- `mobile.navigation`: Expo Router (파일 기반 라우팅) 구조
- `state.flow`: Zustand store 설계
- `persistence`: SecureStore (토큰) + AsyncStorage (비민감 캐시) 분리

**android-kotlin 의 경우**:
- `mobile.navigation`: Navigation Compose + NavGraph
- `state.flow`: ViewModel + StateFlow (MVVM)

**ios-swift 의 경우**:
- `mobile.navigation`: NavigationStack (SwiftUI)
- `state.flow`: @StateObject / @ObservableObject 패턴
