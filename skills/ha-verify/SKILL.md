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

### 2.5. 실패 분석 — 재작업 태스크 특정

`passed=false` 인 경우, **어떤 T-ID를 /ha-build 로 재작업할지** 명시해야 합니다.
이 단계를 건너뛰면 사용자가 무엇을 고쳐야 할지 모릅니다.

**1. 실패 항목 추출** (명령 출력에서):
```
pytest : FAILED tests/api/test_auth.py::test_login_missing_fields
         FAILED tests/models/test_user.py::test_duplicate_email
pyright: src/services/auth.py:42 — Argument of type "str | None" ...
```

**2. 태스크 매핑** — `tasks.md` 스펙 블록의 "생성/수정 파일" 에서 실패 파일 검색:
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
  --summary "<예: pytest 327, ruff clean, pyright 0 errors>"
```
run.py 가:
- `verify_history` 에 새 엔트리 추가 (step, at, passed, summary)
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

### 출력의 guideline_paths 읽기 (필수)

출력 JSON 의 `profiles[].guideline_paths` 에 포함된 경로를 **작업 시작 전 모두 Read 로 읽으세요.**
프로파일별 파일 목록 → `<HARNESS_AI_HOME>/skills/_ha_shared/GUIDELINES_NOTE.md` 참조.

## 가드레일

- 명령 실행 전 `cwd` 확인 (모노레포에서 잘못된 디렉토리 실행 방지)
- 테스트 결과 임의 조작 X — 실패는 실패로 기록
- timeout 60~600초 사이 (큰 테스트 스위트는 백그라운드 실행 권장)
- `passed=false` 시 **재작업 T-ID 없이 FAIL 보고 금지** — 단계 2.5 완료 후 record 호출
- verify_history 활용: 동일 T-ID 가 2회 이상 FAIL 하면 `/ha-redesign` 으로 설계 근본 수정 검토

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
