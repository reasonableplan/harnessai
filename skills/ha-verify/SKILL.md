---
name: ha-verify
model: sonnet
description: |
  HarnessAI v2 — 프로파일의 toolchain (test/lint/type) 실행 + 결과 기록.
  기계적 명령 실행 + 결과 파싱이 주 업무라 Sonnet 사용 (속도/비용 최적화).
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
```
✅ /ha-verify PASS — 327 tests, lint clean
다음: /ha-review

또는

❌ /ha-verify FAIL — pytest 5 failed
실패 케이스: <목록>
다음: 실패 원인 수정 후 /ha-verify 재실행
       또는 /ha-build <T-ID>로 해당 태스크 재구현
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

- 명령 실행 전 `cwd` 확인 (모노레포에서 잘못된 디렉토리 실행 방지)
- 테스트 결과 임의 조작 X — 실패는 실패로 기록
- timeout 60~600초 사이 (큰 테스트 스위트는 백그라운드 실행 권장)

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
