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
- `profiles` (활성 프로파일 정보 + body 경로)
- `agent_prompts` (architect/designer CLAUDE.md 절대 경로)
- `skeleton_path`, `plan_path`

### 2. 에이전트 프롬프트 + skeleton 본문 로드

Read 로:
- `<HARNESS_AI_HOME>/backend/docs/shared-lessons.md` — **반드시 가장 먼저 읽는다.** 과거 실수 패턴 (LESSON-NNN) 숙지 후 설계. 특히 auth 섹션 작성 전 LESSON-022~027 필수.
- `<agent_prompts.architect>` (Architect 역할 프롬프트)
- `<agent_prompts.designer>` (Designer 역할 프롬프트)
- 활성 프로파일 본문들 (각 프로파일 .md 의 frontmatter 이외 부분 — components 가이드, 금지사항 등)
- `<skeleton_path>` (현재 skeleton.md)
- `<plan_path>` (사용자 설명, 판단 근거)
- `docs/conventions.md` — **존재하면 반드시 읽는다.** 사용자 정의 스타일이 skeleton 의 모든 기술 결정에 우선함. 없으면 skip.

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
- [ ] 표의 모든 행이 실제 값으로 채워짐 (DB 컬럼은 타입·제약 명시, API는 method+path+schema 모두)
- [ ] 에러 코드 섹션: 코드 ID + HTTP status + 설명 3종 세트 완비
- 분량보다 **구체성** 기준 — "Users 테이블" 이 아니라 "id(PK)/email(unique,not null)/token_version(int,default=0)"

**`auth` 섹션 보안 체크리스트 (작성 완료 전 전부 확인)**:
- [ ] JWT payload 에 `type` ("access"/"refresh") + `ver` (token_version) 두 claim 포함 (LESSON-022)
- [ ] User 모델에 `token_version: int` 필드 존재 (LESSON-023)
- [ ] logout 이 서버에서 `token_version` 증가 — no-op 절대 금지 (LESSON-023)
- [ ] refresh endpoint 가 httponly 쿠키 전용 — body.refresh_token 수락 금지 (LESSON-024)
- [ ] accessToken 저장 방법이 **메모리 변수** (인메모리 상태관리) — localStorage/sessionStorage/AsyncStorage/SharedPreferences/UserDefaults 금지 (LESSON-027)

**`view.*` 섹션 보안 체크리스트**:
- [ ] 토큰 저장 위치가 localStorage/sessionStorage 로 명시된 부분 없는지 확인
- [ ] 모바일의 경우 SecureStore(RN) / flutter_secure_storage / Android Keystore / iOS Keychain 사용 명시

**중간에 사용자 질문** (선택적, AskUserQuestion):
- 정보 부족한 부분만 (예: "비밀번호 정책은? 8자 이상 / 12자 이상 / 사용자 자유")
- 질문 5개 이하

### 4. 충돌 검토 (Designer ↔ Architect)

Designer 섹션 (view.*) 작성 후, 그 화면이 요구하는 데이터/액션이 Architect 가 작성한 `interface.http` / `auth` / `state.flow` 에서 모두 제공되는지 확인.

미충족 발견 시:
- `interface.http` 섹션에 새 엔드포인트 추가 (Architect 역할 재진입)
- 또는 `state.flow` 에 새 전이 규칙 추가
- (정말 안 되면 Designer 가 view 수정)

최대 3 라운드. 3라운드 후 미충족 항목이 남으면:
- 미충족 항목을 skeleton `notes` 섹션에 `TODO:` 로 기록
- commit 진행 + 다음 단계 안내에서 사용자에게 명시 ("미결 N개: …")
- **에스컬레이션하지 않고** best-effort 로 진행 — 완성도보다 전진 우선

### 5. 저장 + 상태 전이

```bash
python ~/.claude/skills/ha-design/run.py commit \
  --skeleton-path "<path>"
```

run.py 가:
- 채워진 skeleton.md 의 placeholder 잔재 검사 (`<...>` 패턴 카운트, 0 이 아니면 경고)
- harness validate 로 plan 무결성 재확인
- `current_step` "init" → "designed" 전이
- `completed_steps += ["ha-design"]`
- last_activity 갱신
- harness-plan.md 저장

### 6. 다음 단계 안내

```
✅ /ha-design 완료

채워진 섹션 (N): <목록>
미해결 placeholder: <0 또는 개수+위치>

다음 단계:
  /ha-plan — 태스크 분해
  (선택) /plan-eng-review — 설계 검토 (gstack)
```

### 출력의 guideline_paths 읽기 (필수)

출력 JSON 의 `profiles[].guideline_paths` 에 포함된 경로를 **작업 시작 전 모두 Read 로 읽으세요.**
프로파일별 파일 목록 → `<HARNESS_AI_HOME>/skills/_ha_shared/GUIDELINES_NOTE.md` 참조.

## 가드레일

- 사용자 설명에 없는 기능을 **추가하지 말 것** (over-engineering 방지)
- 프로파일 화이트리스트 외 라이브러리 명시 금지
- 작성 가이드 (`> 작성 가이드:`) 블록은 결과에서 **반드시 제거** (사용자 가이드는 임시 도움말)
- skeleton 의 `## N. <title>` 헤딩과 섹션 번호는 변경 금지 (다른 도구가 파싱)
- `tasks` / `notes` 섹션은 절대 채우지 말 것 (각각 /ha-plan, /ha-build 영역)

## 트러블슈팅

**"current_step != init"**: `/ha-init` 부터 다시. 또는 이미 designed 라면 `--reset` (run.py 미지원 시 수동 backup 후 init 으로 되돌리기).

**미해결 placeholder 가 많음**: 사용자 설명이 부족했을 가능성. `/ha-init` 로 돌아가서 더 구체적으로 작성.

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
