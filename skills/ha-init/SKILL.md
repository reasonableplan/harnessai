---
name: ha-init
description: |
  HarnessAI v2 — 프로젝트 초기화 스킬.
  스택 자동 감지 + 사용자 설명 인터뷰 + 판단 → harness-plan.md + skeleton.md 생성.
  v2 인프라(profile_loader/skeleton_assembler/plan_manager) 의 첫 사용자 진입점.
  Use when: 새 프로젝트 시작, "프로젝트 시작하자", "/ha-init"
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

새 프로젝트 (또는 v2 시스템 처음 적용하는 기존 프로젝트) 의 초기화.

**입력**: 사용자가 무엇을 만들고 싶은지에 대한 자연어 설명
**출력**: `docs/harness-plan.md` + `docs/skeleton.md` (빈 템플릿)
**다음**: `/ha-design` 으로 skeleton 채우기

## 실행 순서

### 1. 프로젝트 루트 확인

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
echo "PROJECT_ROOT: $PROJECT_ROOT"
```

### 2. 프로파일 자동 감지

```bash
python ~/.claude/skills/ha-init/run.py detect "$PROJECT_ROOT"
```

**기존 코드베이스면 먼저 /ha-deepinit 제안**: 프로젝트에 소스가 이미 상당량 있으면 (src/ 등)
빈 skeleton 을 들이밀기 전에 `/ha-deepinit` 으로 AGENTS.md 를 먼저 생성하라고 제안 —
`/ha-design` 이 훨씬 풍부한 컨텍스트로 시작한다.

출력은 JSON. 다음 정보 추출:
- `matches[]` — 감지된 프로파일 목록 (id, name, path, required/optional sections, toolchain, whitelist, gstack_recommended)

**수동 프로파일 선택 — 트리 fallback (매칭 0건 또는 사용자 추가 선택 시)**:

AskUserQuestion 의 4-옵션 제약을 **트리 깊이로 우회**한다. 절대 confirmed 프로파일 중 일부만 임의로 추려서 보여주지 말 것.

1단계 — 도메인 (sticky 4 카테고리):
- `서버 / API` — 서버사이드 비즈니스 로직, HTTP/RPC 엔드포인트
- `UI (사용자 대면)` — 웹/모바일/데스크톱 등 사용자 인터페이스
- `인터랙티브 / 게임` — 게임 엔진, VR/AR
- `도구 / 라이브러리 / 기타` — CLI, lib, 스킬, 임베디드 등

2단계 — 각 도메인 안에서:
- `서버 / API`:
  - `fastapi` — Python FastAPI
  - `nestjs` — Node.js NestJS
- `UI`:
  - 웹 브라우저 → 3단계
  - 모바일 → 3단계
  - 데스크톱 → 3단계
- `인터랙티브 / 게임`:
  - (현재 confirmed 프로파일 없음 — Unity / Unreal / Godot 추가 예정)
- `도구 / 라이브러리 / 기타`:
  - `python-cli` — Python CLI 도구
  - `python-lib` — Python 라이브러리
  - `claude-skill` — Claude Code 스킬

3단계 — UI 플랫폼 분기:
- 웹 브라우저:
  - `nextjs` — Next.js App Router
  - `react-vite` — React + Vite SPA
- 모바일:
  - `react-native-expo` — Expo (React Native)
  - `flutter` — Flutter (Dart)
  - `android-kotlin` — 네이티브 Android
  - `ios-swift` — 네이티브 iOS
- 데스크톱:
  - `electron` — Electron

**진행 흐름**:
1. AskUserQuestion 으로 1단계 카테고리 1개 선택
2. 선택 카테고리에 프로파일이 1개면 바로 사용. 여러 개면 2단계 (필요 시 3단계) 로 좁힘
3. 풀스택 (백엔드 + UI 등 다계층) 케이스: 1차 선택 후 "다른 계층도 추가하시겠어요?" yes → 1단계부터 반복
4. 최종 선택된 프로파일 ID 들을 콤마 구분해서 `--profiles` 인자에 넘김

**확장 운영 규칙** — 신규 프로파일 추가 시:
1. 1단계 4 카테고리는 **도메인 레벨** 로 sticky — 플랫폼/언어/도구 기준으로 신설 금지
2. 한 단계 안에 옵션이 4개 차면 다음 단계로 깊이 늘리기 (예: 모바일이 5개 되면 4단계 분기)
3. `도구 / 라이브러리 / 기타` 안에서 같은 도메인 프로파일이 3개 이상 모이면 **1단계 카테고리로 승격 검토** (예: AI/ML 프로파일 3개 → "AI/ML" 1단계 신설)
4. 신규 프로파일 추가 PR 에 어느 카테고리/깊이에 들어가는지 명시 — 본 SKILL.md 도 동기 업데이트

### 3. 사용자 설명 수집

AskUserQuestion 으로:
- "뭘 만들고 싶으세요? 한두 문장으로 설명해 주세요."
- (free text 응답)

답변이 짧고 모호하면 (50자 미만) 추가 질문 1개:
- "주요 기능 또는 사용자가 누구인지 조금 더 알려주세요."

### 3-2. 6축 인터뷰 — project scaling

수집한 6축 답변은 `harness-plan.md` 의 `scale_axes` 에 구조화 저장된다. Phase 2 의 profile 매트릭스가 활성 섹션 결정에 사용 (현재 Phase 1 — 수집만).

**먼저 분기 질문** (AskUserQuestion):
- 질문: "프로젝트 규모를 빠르게 정할까요?"
- options:
  - `S 프리셋 — 개인 사이드 / 주말 프로젝트`
  - `M 프리셋 — 스타트업 MVP / 팀 프로젝트`
  - `L 프리셋 — 엔터프라이즈 / 운영 제품`
  - `6축 직접 답`

**프리셋 매핑**:

| 프리셋 | user_scale | data_sensitivity | team_size | availability | monetization | lifecycle |
|---|---|---|---|---|---|---|
| S | small | none | solo | standard | none | mvp |
| M | medium | (follow-up) | small | standard | (follow-up) | mvp |
| L | large | (follow-up) | multi | high | (follow-up) | ga |

`(follow-up)` 표시 축은 프리셋만으로 결정하지 말고 한 번 더 묻는다 (사람마다 다름):
- AskUserQuestion: "민감 데이터를 다루나요?" → `none` / `pii` (이메일·이름·전화) / `payment` (카드·계좌)
- AskUserQuestion: "수익 모델은?" → `none` / `ads` / `subscription` / `payment`

**6축 직접 답** (사용자가 "직접" 선택 시) — 각 축마다 AskUserQuestion 1회. 옵션 라벨에 짧은 설명을 같이 보여준다:
- user_scale: "예상 DAU? — tiny <10 / small <100 / medium <10k / large 10k+"
- data_sensitivity: "민감 데이터? — none / pii / payment"
- team_size: "팀 규모? — solo / small 2-5명 / multi 6명+"
- availability: "가용성 요구? — casual: down 수시간 ok / standard: 99% / high: 99.9%+"
- monetization: "수익 모델? — none / ads / subscription / payment"
- lifecycle: "라이프사이클 단계? — poc / mvp / ga"

### 4. Claude 판단 — 다음을 직접 결정한다

**4-1. 프로젝트 타입 한 줄 요약** (예: "LLM 기반 코드 분석 CLI 도구")

**4-2. legacy `scale` 매핑**

`scale` (기존 1축) 은 3-2 의 `user_scale` 값을 그대로 사용한다 (tiny|small|medium|large). 별도 판단 불필요. 6축 입력 자체로 충분.

**4-3. optional 섹션 포함 여부 결정**

각 optional 섹션마다 자체 판단:
- `requirements` — 명확한 기능 목록 있으면 포함 (보통 small 이상에서 포함)
- `configuration` — 환경변수/API 키 필요 시 포함
- `persistence` — 파일/DB 저장 있으면 포함
- `auth` — 다중 사용자 / 인증 필요 시 포함
- `integrations` — 3rd party API 연동 있으면 포함
- 기타 — 사용자 설명 + 프로파일 components 기반

**4-4. 파이프라인 단계 + gstack 게이트 제안**

기본:
```
ha-init → ha-design → ha-plan → ha-build (반복) → ha-verify → ha-review
```

프로파일의 `gstack_recommended` 에 정의된 게이트 끼워넣기:
- `before_design`, `after_design`, `after_build`, `before_ship`, `after_ship`

규모가 작으면 일부 gstack 게이트 생략 권장 (예: tiny CLI 는 `/qa` 생략).

### 5. 사용자에게 제안 출력 + 승인

다음 형식으로 출력:

```
=== /ha-init 제안 ===

프로젝트 타입: <한 줄>
규모(legacy scale): <tiny|small|medium|large>
6축 (scale_axes):
  - user_scale:        <tiny|small|medium|large>
  - data_sensitivity:  <none|pii|payment>
  - team_size:         <solo|small|multi>
  - availability:      <casual|standard|high>
  - monetization:      <none|ads|subscription|payment>
  - lifecycle:         <poc|mvp|ga>
활성 프로파일: <id @ path> [, ...]

skeleton 섹션 (총 N개, auto-determined by 6축 + profile):
  active (N):    <목록 — ProfileLoader.compute_active_sections 결과>
  (참고)
  required (M):  <profile 의 declared required>
  optional (K):  <profile 의 declared optional>

파이프라인:
  1. /ha-init     ✅ (방금)
  2. /ha-design   ⏳
  3. (gstack) /plan-eng-review (선택)
  ...

생략 제안:
  - /office-hours: <이유>
  - /qa: <이유>
```

**정합성 경고 표시** (`write` 출력의 `consistency_violations` 필드가 비어있지 않으면):

```
⚠️ 정합성 경고 N건:
  - <section_id>: <trigger>  (필요: has.<atom>, 제공 가능 프로파일: <providers>)
  ...
```

AskUserQuestion 으로 승인:
- `진행` — 그대로 작성
- `수정` — 어디를 어떻게 (사용자 텍스트 받아서 4-2~4-4 재조정 후 재제안. 최대 3회)
- `그대로 진행 — 외부 제공자가 있는 의도적 모순` — violation 을 인지하고 진행 (예: 외부 백엔드 별도 관리)
- `취소` — 저장 없이 종료

**가드레일**: consistency_violations 가 있으면 사용자에게 반드시 명시적으로 보여줄 것 — 자동으로 무시 금지.

### 6. 파일 작성

승인 받으면:

```bash
python ~/.claude/skills/ha-init/run.py write \
  --project "$PROJECT_ROOT" \
  --profiles "<comma-separated profile IDs>" \
  --description "<원본 사용자 설명>" \
  --project-type "<한 줄 요약>" \
  --user-scale "<tiny|small|medium|large>" \
  --data-sensitivity "<none|pii|payment>" \
  --team-size "<solo|small|multi>" \
  --availability "<casual|standard|high>" \
  --monetization "<none|ads|subscription|payment>" \
  --lifecycle "<poc|mvp|ga>" \
  --gstack-mode manual
```

**Phase 2-b-4 부터 `--included` 는 optional**. 미지정 시 6축 + profile.skeleton_sections 로부터 `ProfileLoader.compute_active_sections` 가 활성 섹션을 자동 결정 (예: PII + mvp → audit_log/threat_model/test_strategy/ci_cd 등 자동 포함). 명시 시 (`--included "overview,stack,..."`) 그대로 사용 (override).

`--scale` 도 omit 가능 (`--user-scale` 값으로 자동 동기화). 6축 default: none/solo/standard/none/mvp. 명시적 6축 전달 권장 — 보수적 default 라 활성 섹션 부족 가능.

기존 `docs/harness-plan.md` 또는 `docs/skeleton.md` 가 있으면 자동 백업 (`.backup-*`).

**`axis_warnings` 확인**: write 출력 JSON 의 `axis_warnings` 가 비어있지 않으면
(예: monetization=payment 인데 data_sensitivity=none) 사용자에게 보여주고 해당 축을
재질문한다. 모순을 인지하고 그대로 두는 것도 허용 (의도적 선택 — 그 사실을 기록).

### 6.5. conventions.md 확인 (권위 1순위 문서)

모든 에이전트의 권위 순서 1위가 `docs/conventions.md` 인데, 파이프라인에 이 문서를
만들어 주는 단계가 없었다 — 여기서 확인한다:
- **이미 있으면**: 통과.
- **기존 코드베이스가 있으면**: `/code-hijack` 으로 시니어 스타일 추출을 제안.
- **신규 프로젝트면**: AskUserQuestion — "선호하는 코드 스타일이 있나요?" → 답을 바탕으로
  최소 스텁 생성 (네이밍 / 에러 패턴 / 상태관리 전략 3~5줄). "없음" 이면 skip
  (프로파일 guidelines 만으로 진행 — 권위 공석을 인지한 선택).

### 7. 다음 단계 안내

출력 예시:
```
✅ /ha-init 완료

생성된 파일:
  - <project>/docs/harness-plan.md
  - <project>/docs/skeleton.md (빈 템플릿)

다음 단계:
  1. /ha-design — Architect/Designer 가 skeleton 채움
  2. (선택) /plan-eng-review — 설계 검토 후 ha-design 결과 강화
  3. /ha-plan → /ha-build → /ha-verify → /ha-review

참고:
  - skeleton.md 직접 편집 가능 (어색한 placeholder 보완)
  - harness-plan.md 의 pipeline.skipped_steps 에 생략하고 싶은 단계 추가 가능
```

### 출력의 guideline_paths 도 읽으세요

`detect` / `write` 출력 JSON 의 `matches[].guideline_paths` / `profiles[].guideline_paths` 에 프로파일별 컨벤션 문서 경로가 포함됩니다.
**작업 시작 전 모두 Read 로 읽으세요.** 프로파일별 파일 목록 → `<HARNESS_AI_HOME>/skills/_ha_shared/GUIDELINES_NOTE.md` 참조.

**모바일 사용자**: 안 읽으면 LESSON-STYLE-001 / 보안 위반 / 컨벤션 drift 가능성. 시스템 프롬프트만으로는 부족합니다.

## 가드레일 — 절대 하지 마라

- `--overwrite` 플래그 없이 기존 파일 덮어쓰기 (run.py 가 자동 백업하지만 직접 Write 도구로 우회 금지)
- 사용자 설명 없이 임의로 description/project-type 결정
- 프로파일 매칭 0건인데 멋대로 진행 — 반드시 수동 선택 옵션 제시
- 프로파일 선택 시 confirmed 프로파일 중 일부만 임의로 추려서 옵션 보여주기 — §2 의 **트리 fallback** 만 사용 (1단계 도메인 카테고리부터 시작, AskUserQuestion 4-옵션 제약은 깊이로 우회)
- skeleton.md 의 fragment 본문 직접 편집 (그건 `/ha-design` 의 일)

## 환경변수

- `HARNESS_AI_HOME` — HarnessAI 레포 경로 (기본: `C:/Users/juwon/OneDrive/Desktop/agent`)
  - run.py 가 v2 모듈 (profile_loader 등) 을 import 할 때 사용

## 트러블슈팅

**`[FAIL] HARNESS_AI_HOME 의 backend/ 가 없음`**:
- HARNESS_AI_HOME 환경변수가 잘못 설정됨. agent 레포의 절대 경로로 export.

**`프로파일 'X' 로드 실패`**:
- `~/.claude/harness/profiles/X.md` 가 없거나 frontmatter 깨짐. `harness validate profiles` 로 확인.

**`detect` 가 매칭 0건**:
- 프로젝트 루트에 `pyproject.toml` / `package.json` 등 마커 파일이 없거나, `_registry.yaml` 의 paths 에 해당 위치가 없음.
- `python ~/.claude/harness/bin/harness validate registry` 로 규칙 확인.

**기존 plan 이 새 로직과 어긋남 (legacy stale)**:
- compute_active_sections 버그 fix 전에 생성된 plan 은 `included` 가 현재 로직과 mismatch 될 수 있음.
- `python ~/.claude/harness/bin/harness migrate-plan <project-dir>/docs/harness-plan.md` (dry-run) 으로 diff 확인.
- `diff.removed_sections` 에 잘못 포함된 섹션, `trace_was_missing: true` 로 legacy 여부 확인.
- 검토 후 `--apply` 로 적용. 자동 백업 (`.backup-pre-migrate-<timestamp>.md`) 생성됨.
- skeleton.md 의 stale 섹션 본문은 별도 `/ha-redesign` 으로 정리 (migrate-plan 은 plan 만 정정).

## 모바일 프로젝트 사용 예시 (Flutter)

**1단계** — 빈 디렉토리에 `pubspec.yaml` 생성:
```yaml
name: my_flutter_app
flutter:
  sdk: flutter
```

**2단계** — `/ha-init` 호출:
- `detect` 출력 JSON 의 `is_mobile: true` 확인
- `guideline_paths` 4개 (navigation/state/storage/style) 모두 읽기
- stderr 에 "[INFO] 모바일 프로젝트 감지: flutter" 안내 확인
- 6축 답변 시 `data_sensitivity=pii` 면 audit_log/threat_model 자동 활성

**react-native-expo 의 경우**:
- `package.json` 에 `"expo"` 의존성 있으면 자동 감지
- `mobile_coder_rn` 에이전트 사용 안내 확인
- android / iOS 양쪽 빌드 고려해 `team_size` 답변 시 반영

**android-kotlin / ios-swift 의 경우**:
- `build.gradle.kts` / `Package.swift` 마커로 자동 감지
- JAVA_HOME (android) / Xcode (ios) 사전 설치 필요
- `platform_warnings` 출력으로 누락 도구 확인 가능 (`/ha-verify` 단계)
