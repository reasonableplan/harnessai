---
name: ha-verify
description: |
  HarnessAI v2 — 프로파일의 toolchain (test/lint/type) 실행 + 결과 기록.
  기계적 명령 실행 + 짧은 결과 파싱이 전부라 부모 세션 모델 그대로 사용 (Opus 라도 비용 미미).
  Use when: /ha-build 완료 후, "검증해줘", "/ha-verify"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
---

## 역할

활성 프로파일들의 `toolchain.test/lint/type` 명령을 실행하고 결과를 `harness-plan.md` 의 `verify_history` 에 기록.

**입력**: 코드 (built 상태)
**출력**: 검증 결과 + verify_history 갱신
**다음**: 통과 시 `/ha-review`, 실패 시 `/ha-build`로 복귀

## 실행 순서

### 1. 사전 조건 + 명령 목록
```bash
python ~/.claude/skills/ha-verify/run.py prepare
```
JSON 출력: 활성 프로파일들의 toolchain (install/test/lint/type/format), 각 명령의 cwd.

### 1.5. skeleton 정합성 게이트 (toolchain 실행 전 필수)

```bash
python ~/.claude/harness/bin/harness integrity --project "$PROJECT_ROOT"
```

- `skeleton.md` 내 ` ```filesystem ` 블록에 선언한 경로 ↔ 실재 파일시스템 일치 확인
- 템플릿 placeholder (`<pkg>`, `<cmd_a>` 등) 미치환 잔존 감지
- **실패 (exit ≠ 0) 시 중단** — `/ha-design` 으로 복귀해 skeleton 보완 필요
- skeleton.md 가 없으면 WARN 만 하고 통과 (프로젝트 초기 상태)

### 1.7. 가짜 FAIL 가드 — `test_dir_warning`

`prepare` 출력의 각 profile 에 `test_dir_warning` 이 있으면 **toolchain 을 그대로 실행하지 말 것**:
toolchain.test 가 가리키는 테스트 디렉토리가 cwd 에 없다 (예: 루트에 `tests/` 를 둔 프로젝트가
profile path `backend/` 로 오매칭). 그대로 돌리면 'no tests ran' 가짜 FAIL 이 verify_history 에 남는다.
- 조치: `harness-plan.md` 의 `profiles[].path` 를 실제 코드 위치로 수정 후 prepare 재실행,
  또는 경고의 힌트 (상위 경로) 가 맞으면 그 cwd 에서 실행.
- 가짜 FAIL 이 이미 기록됐다면: 환경 문제이므로 후속 record 는 `--no-rework` 로.

### 1.8. 런타임 기동 스모크 게이트 (issue #6)

`prepare` 출력의 `smoke_failures` (list) 와 각 profile 의 `smoke_check` 를 확인:

- **`smoke_failures` 가 비어있지 않으면** — test/lint/type 이 통과해도 앱이 실제로 안 뜨거나
  출력 시 크래시한 것 (예: 한국어 Windows cp949 콘솔의 em-dash `UnicodeEncodeError`).
  CliRunner(utf-8 버퍼) 테스트는 이걸 못 잡으므로 **이 스모크 실패를 verify 실패로 간주**:
  `record --passed false --rework-tasks <entrypoint 태스크>` 로 기록하고 `/ha-build` 복귀.
  근본 수정은 LESSON-033 (기본 출력 ASCII-safe 또는 진입점 UTF-8 강제).
- **cli_entrypoint 인데 `smoke_check.ran=false` (toolchain.smoke 미설정) WARN** — 런타임 게이트가
  비어 있다. plan/profile 의 `toolchain.smoke` 에 실제 invoke (`python -m <pkg> --help` +
  대표 출력 경로) 를 설정하거나, 최소한 `/ha-smoke` 로 기동을 따로 검증.
- 서버/UI 프로파일(non-cli)은 여기서 안 돌린다 — `/ha-smoke` 의 url 모드가 담당.

### 2. 명령 실행 (Bash)
프로파일 순서대로:
```bash
cd <profile.cwd>
<profile.toolchain.install>  # (필요 시 1회)
<profile.toolchain.test>
<profile.toolchain.lint>
<profile.toolchain.type>     # (null 이면 skip)
```

각 명령 결과 (exit code + stdout/stderr 마지막 30~50 라인) 수집.

**install 실패 처리**: `toolchain.install` 이 실패하면 이후 명령 전부 skip.
install 실패는 T-ID 재작업 대상이 아님 — 환경 문제로 처리:
```
⚠️ /ha-verify BLOCKED — install 실패
  <install 명령>: exit 1
  원인: <오류 메시지>
  조치: 환경 점검 후 수동 재실행 (패키지 레지스트리, 네트워크, 권한 확인)
```
record 는 `--passed false --summary "install 실패: <사유>"` 로 기록 후 종료.

### 2.5. 실패 분석 — 재작업 태스크 특정

`passed=false` 인 경우, **어떤 T-ID를 `/ha-build` 로 재작업할지** 명시해야 합니다.
이 단계를 건너뛰면 사용자가 무엇을 고쳐야 할지 모릅니다.

**1. 실패 항목 추출** (명령 출력에서):
```
pytest : FAILED tests/api/test_auth.py::test_login_missing_fields
         FAILED tests/models/test_user.py::test_duplicate_email
pyright: src/services/auth.py:42 — Argument of type "str | None" ...
```

**2. 태스크 매핑** — `harness analyze-failure` 로 자동 매핑 (권장):
```bash
# 출력을 파일로 저장 후 분석
python ~/.claude/skills/ha-verify/run.py prepare > /tmp/verify-out.txt 2>&1
# (위 명령 후 실제 toolchain 출력을 파일로 캡처)
python ~/.claude/harness/bin/harness analyze-failure /tmp/toolchain-output.txt \
  --tasks docs/tasks.md
```
JSON 출력:
```json
{
  "failures": ["tests/api/test_auth.py", "src/services/auth.py"],
  "matches": [
    {"task_id": "T-003", "files": ["src/services/auth.py", "tests/api/test_auth.py"]}
  ],
  "unmatched_failures": []
}
```
→ `matches[].task_id` 가 재작업 대상 T-ID.

**수동 fallback** (analyze-failure 사용 불가 시):
```bash
grep -n "test_auth\|auth\.py" docs/tasks.md
grep -n "test_user\|user\.py" docs/tasks.md
```
→ 해당 파일을 "생성/수정 파일" 로 가진 T-ID 가 재작업 대상.

**3. 부분 실패 처리** — 복수 프로파일 중 일부만 실패:
- 실패 프로파일의 태스크만 재작업 대상
- 통과 프로파일 태스크는 그대로 유지
- `--summary` 에 어느 프로파일이 통과/실패인지 명시

**4. depends_on 순서 우선** — 상위 의존 태스크를 먼저 수정.

`passed=true` 이면 이 단계 skip.

### 3. 결과 기록
```bash
python ~/.claude/skills/ha-verify/run.py record \
  --passed true|false \
  --summary "<예: pytest 327, ruff clean, pyright 0 errors>" \
  [--rework-tasks "T-001,T-002"]  # passed=false 시 필수 (재작업 T-ID CSV)
  [--no-rework]                   # task 재작업 아닌 환경 문제 등일 때 (--rework-tasks 대체)
```
run.py 자동 검증:
- `verify_history` 에 새 엔트리 추가 (step, at, passed, summary)
- **`passed=false` + `--rework-tasks` 없음 + `--no-rework` 없음** → exit 1 (가드레일: 재작업 T-ID 필수)
- `passed=false` + `--rework-tasks "T-001,T-002"` → summary 에 `[rework: T-001,T-002]` 자동 추가
- `passed=true` 면 "built" → "verified" 전이
- `passed=false` 면 "building" 으로 회귀 (재구현 필요)

### 4. 다음 안내

통과:
```
✅ /ha-verify PASS
  pytest N passed  |  ruff clean  |  pyright 0 errors
다음: /ha-review
```

실패 — **재작업 T-ID 를 반드시 명시** (단계 2.5 결과 기반):
```
❌ /ha-verify FAIL

실패 내역:
  pytest : 5 failed
    FAILED tests/api/test_auth.py::test_login_missing_fields
    FAILED tests/api/test_auth.py::test_refresh_invalid
    FAILED tests/models/test_user.py::test_duplicate_email
  pyright: 3 errors (src/services/auth.py:42, :67, :89)

재작업 태스크:
  → T-003 (auth 서비스): test_auth.py 2개 + pyright 3개
  → T-001 (users 모델): test_user.py 1개

다음:
  /ha-build T-003    ← depends_on 없음, 먼저 수정
  /ha-build T-001    ← T-003 완료 후
  모두 수정 후: /ha-verify 재실행
```

### 출력의 guideline_paths 도 읽으세요

`prepare` 출력 JSON 의 `profiles[].guideline_paths` 에 프로파일별 컨벤션 문서 경로가 포함됩니다.
**작업 시작 전 모두 Read 로 읽으세요.** 프로파일별 파일 목록 → `<HARNESS_AI_HOME>/skills/_ha_shared/GUIDELINES_NOTE.md` 참조.

**모바일 사용자**: 안 읽으면 LESSON-STYLE-001 / 보안 위반 / 컨벤션 drift 가능성. 시스템 프롬프트만으로는 부족합니다.

## 가드레일

- 명령 실행 전 `cwd` 확인 (모노레포에서 잘못된 디렉토리 실행 방지)
- 테스트 결과 임의 조작 X — 실패는 실패로 기록
- timeout 60~600초 사이 (큰 테스트 스위트는 백그라운드 실행 권장)
- `passed=false` 시 **재작업 T-ID 없이 FAIL 보고 금지** — **`record --passed false` 에 `--rework-tasks` 없으면 run.py 가 exit 1 로 차단**. 환경 문제로 task 재작업 아니면 `--no-rework` 명시
- 동일 T-ID **3회째 FAIL 은 run.py 가 record 를 차단** (`--force-continue` 로만 우회) — 2회째부터 `/ha-redesign` 설계 근본 수정 검토 권장

## 모바일 프로젝트 사용 예시 (Flutter)

**5단계 — `/ha-verify` 로 toolchain 실행**:

- `prepare` 출력의 `platform_warnings` 먼저 확인 — 도구 미설치 경고 처리
- Flutter toolchain 실행 순서:
  ```bash
  flutter pub get          # install
  flutter test             # test
  flutter analyze          # lint
  dart format --set-exit-if-changed .  # format
  ```
- `platform_warnings` 에 경고 있어도 toolchain 실행은 시도 (경고는 참고용)

**react-native-expo 의 경우**:
- `bun install` → `bun test` → `bun run lint` → `bunx tsc --noEmit`
- iOS 시뮬레이터 테스트는 macOS 에서만 가능

**android-kotlin 의 경우**:
- JAVA_HOME 미설정 시 `platform_warnings` 에 경고 — Gradle 실행 전 설정 필수
- `./gradlew test` 실패 시 로그에서 실패 테스트 확인

**ios-swift on Windows**:
- `platform_warnings`: "Windows host: swift build dry-run only"
- `swift build` 는 실행하되 `xcodebuild test` 는 macOS CI 에서만 실행
- SwiftLint 는 Docker 또는 CI 환경에서 실행 권장
