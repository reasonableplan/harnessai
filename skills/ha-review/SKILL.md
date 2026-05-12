---
name: ha-review
description: |
  HarnessAI v2 — 보안 훅 + LESSON 패턴 + AI 슬롭 + convention 종합 리뷰 (Reviewer 역할).
  auth-guard 가 7번째 훅으로 통합됨 (LESSON-022~027: JWT/logout/refresh/token 저장).
  Use when: /ha-verify 통과 후, "리뷰해줘", "/ha-review"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
---

## 역할

`/ha-verify` 통과 후 코드 품질의 마지막 게이트. APPROVE 또는 REJECT (구체적 위반 사항 + 수정 방법).

**입력**: 변경된 코드 (verified 상태) + git diff
**출력**: 리뷰 결과 (APPROVE/REJECT) + verify_history 기록
**다음**: APPROVE 시 reviewed 상태 (배포 가능). REJECT 시 building 으로 회귀.

## 사전 조건

- **git 저장소 필수**: `/ha-review` 는 `git diff` 로 변경분을 추출해 보안/슬롭 훅에 입력한다.
  git 저장소가 아니면 모든 검사가 빈 입력으로 silent pass되는 위험이 있으므로 `prepare` 단계에서 exit 2 로 fail-fast 처리한다.
  프로젝트가 git 저장소가 아닌 경우: `git init && git add -A && git commit -m "initial"` 후 재실행.

## 실행 순서

### 1. 사전 조건 확인 + git diff
```bash
python ~/.claude/skills/ha-review/run.py prepare
```
git 저장소 아니면 exit 2 + actionable 에러 메시지 출력.
JSON 출력: 활성 프로파일들 (whitelist + lessons_applied), git diff 변경 파일 목록, 보안 훅 + ai-slop 패턴 목록.

### 2. 7개 보안 훅
backend 의 `security_hooks.SecurityHooks.from_profile(<primary_profile>).run_all(<diff_text>, is_frontend=...)` 호출.

다음 훅들이 자동 실행됨:
1. **secret-filter** — 하드코딩 시크릿 탐지
2. **command-guard** — 위험 명령 (rm -rf, eval, DROP TABLE)
3. **db-guard** — raw SQL, f-string SQL, WHERE 없는 DELETE
4. **dependency-check** — 화이트리스트 외 import/install
5. **code-quality** — TS any, 빈 except, console.log, print
6. **contract-validator** — skeleton 외 엔드포인트
7. **auth-guard** — JWT type+ver claim 누락, localStorage 토큰 저장, refresh body fallback, logout no-op, MAX()+1 race condition (LESSON-022~027)

### 2.5. AI Slop 수동 점검 (Bash + Grep 보조)

보안 훅과 별개로 다음 패턴을 Grep 으로 추가 확인:
- 과도한 추상화 (단일 호출자만 있는 helper)
- 의미 없는 try/except (re-raise 만)
- 장황한 docstring (>5줄에 정보 X)
- dead code (정의됐는데 안 쓰임)
- 임시 핵 흔적 (TODO/FIXME 신규 추가)

각 훅의 BLOCK/WARN finding 수집.

### 3. LESSON 패턴 점검
`<HARNESS_AI_HOME>/backend/docs/shared-lessons.md` 의 LESSON-XXX 패턴 중 활성 프로파일에 적용되는 것들 (`profile.lessons_applied`):
- 각 LESSON 의 패턴(보통 정규식이나 anti-pattern 설명)을 변경 파일에서 검색
- 발견 시 위반으로 기록 (LESSON-NNN 번호 포함)

### 4. 프로파일 convention 점검
프로파일 본문(.md) 의 "금지 사항" 섹션을 읽고 변경 파일에서 위반 검색.

### 5. APPROVE / REJECT 판정

| 조건 | 판정 |
|------|------|
| BLOCK 1건 이상 | REJECT |
| WARN 5건 이상 | REJECT 권고 (사용자 최종 판단 가능) |
| WARN 1~4건 + BLOCK 0건 | APPROVE (with notes 필수) |
| BLOCK 0 + WARN 0 | APPROVE (clean) |

**git diff 스코프**: `built` 상태 전환 이후 전체 변경분.
```bash
git log --oneline          # ha-build 시작 시점 커밋 확인
git diff <built-이전-hash>...HEAD
```
커밋 히스토리가 없거나 불명확하면 전체 소스 검토.

출력 형식 (Reviewer agent 출력 규격):
```
## Review Result: APPROVE | REJECT

### 위반 사항 (REJECT 시)
1. [훅명/LESSON-N번 위반] 파일:라인 — 설명 — 수정 방법
2. ...

### 권장 사항
1. 파일:라인 — 개선 제안 (선택)

### shared-lessons 확인
- 패턴 반복 여부: 없음 / 있음 (LESSON-XXX)

### AI Slop 점검
- 발견: 0 / N건
```

### 6. 결과 기록
```bash
python ~/.claude/skills/ha-review/run.py record \
  --verdict approve|reject \
  --summary "<요약>" \
  --violations "<\"위반1\",\"위반2\"...>" (REJECT 시)
```
run.py 가:
- `verify_history` 에 새 엔트리 (step="ha-review")
- APPROVE → "verified" → "reviewed" 전이
- REJECT → "building" 으로 회귀

### 7. 다음 안내

**APPROVE**:
```
✅ APPROVE — clean.
다음: (선택) /review (gstack pre-PR), /ship 또는 사용자 결정
```

**REJECT** — **재작업 T-ID 를 반드시 특정**:
```
❌ REJECT — N건 위반.

위반 사항:
  1. [auth-guard:BLOCK] src/services/auth.py:42 — JWT type claim 누락 → "type":"access" 추가
  2. [LESSON-023:BLOCK] src/services/auth.py:78 — logout no-op → token_version 증가 구현

재작업 태스크 (위반 파일 → tasks.md 스펙 블록에서 검색):
  → T-003 (auth 서비스): 위반 1, 2 모두 이 태스크 파일
  (확인: grep -n "auth.py" docs/tasks.md)

다음:
  /ha-build T-003
  수정 후: /ha-verify → /ha-review 재실행
```

REJECT 시 재작업 T-ID 특정 방법:
```bash
grep -n "<위반 파일명>" docs/tasks.md
```
→ "생성/수정 파일" 항목에 해당 파일이 있는 T-ID 가 재작업 대상.

### 출력의 guideline_paths 읽기 (필수)

출력 JSON 의 `profiles[].guideline_paths` 에 포함된 경로를 **작업 시작 전 모두 Read 로 읽으세요.**
프로파일별 파일 목록 → `<HARNESS_AI_HOME>/skills/_ha_shared/GUIDELINES_NOTE.md` 참조.

## 가드레일

- 코드 직접 수정 X (리뷰 코멘트만)
- BLOCK 무시하고 APPROVE 금지
- 모호한 reject 금지 — 반드시 파일:라인 + 수정 방법
- skeleton 계약 무시한 자기 기준 판단 금지

## 모바일 프로젝트 사용 예시 (Flutter)

**6단계 — `/ha-review` 로 보안 + 품질 리뷰**:

- `prepare` 출력의 `profiles[].guideline_paths` flutter 가이드라인 4개 읽기
- mobile 보안 룰 자동 검사 (flutter profile 활성 시):
  - `shared_preferences` 에 토큰 저장 → **BLOCK** (flutter_secure_storage 사용)
  - 3개 이상 권한 일괄 요청 → **WARN** (just-in-time 요청 권장)
- LESSON 패턴 + ai-slop 패턴 검사 동시 실행

**react-native-expo 의 경우**:
- `AsyncStorage.setItem('auth_token', ...)` → **BLOCK** (SecureStore 사용)
- `react-native run-android` 직접 사용 → **WARN** (`expo run:android` 사용)

**android-kotlin 의 경우**:
- `SharedPreferences` 에 Token 저장 → **BLOCK** (Android Keystore 사용)
- 권한 3개+ 일괄 요청 → **WARN**

**ios-swift 의 경우**:
- `UserDefaults` 에 Token 저장 → **BLOCK** (iOS Keychain 사용)
- Podfile 에 신규 `pod '...'` 추가 → **WARN** (SPM 우선 검토)
