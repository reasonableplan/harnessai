# HarnessAI Capability Atom Spec

이 문서는 HarnessAI 의 `has.*` capability atom 시스템의 단일 source of truth.
신규 atom 추가 / 매핑 변경 / 결정 근거 검토 시 반드시 참조.

## 1. Source of truth

- 코드 상수: `backend/src/orchestrator/capabilities.py::KNOWN_CAPABILITY_ATOMS`
- 양방향 일관성: `backend/src/orchestrator/consistency.py::_HAS_KEY_PROVIDERS`
- 검증 강제: `backend/tests/orchestrator/test_capability_atoms_consistency.py`

`KNOWN_CAPABILITY_ATOMS` 외 atom 사용은 `validate_capability_set()` 가 차단.
`provides_capabilities`, `_HAS_KEY_PROVIDERS`, `derive_axes_capabilities`, fragment
`required_when` 모두 이 셋 안의 atom 만 참조 가능.

## 2. has.* 결정 흐름

```
has_keys =
    profile.provides_capabilities (selected profiles)
  ∪ derive_axes_capabilities(scale_axes)
  ∪ plan.external_capabilities (user-declared BaaS / external)
```

세 source 의 union. fragment 의 `required_when` 표현식이 이 셋을 평가.

## 3. Atom 목록 (14개)

### `ui` — 사용자 인터페이스 (화면 렌더링)

- **정의**: 사용자가 직접 보는 화면/뷰. React/Vue/SwiftUI/Jetpack Compose 컴포넌트 트리.
- **제공자 profiles**: `nextjs`, `react-vite`, `electron`, `react-native-expo`, `flutter`, `android-kotlin`, `ios-swift`
- **6축 derived**: 없음
- **사용 fragments**: `view.screens`, `view.components`, `error_ux`
- **근거**: UI 프로파일이라면 모두 제공. 백엔드/CLI/lib 는 제공 안 함.

### `http_server` — HTTP 요청 처리

- **정의**: HTTP/HTTPS 엔드포인트를 노출하는 서버 또는 풀스택. REST/GraphQL/RPC 핸들러.
- **제공자 profiles**: `fastapi`, `nestjs`, `nextjs`
- **6축 derived**: 없음
- **사용 fragments**: `interface.http`, `rate_limiting`
- **근거**: 백엔드 또는 RSC + Server Actions 를 가진 풀스택. Next.js 는 Route Handler 가 http_server 역할.

### `cli_entrypoint` — CLI 명령어

- **정의**: `console_scripts` 또는 `[project.scripts]` 의 entry point. argparse / click / typer.
- **제공자 profiles**: `python-cli`
- **6축 derived**: 없음
- **사용 fragments**: `interface.cli`
- **근거**: CLI 전용 프로파일만 진정한 cli_entrypoint. fastapi 안 함 (server 가 본질).

### `sdk_surface` — 라이브러리 공개 API

- **정의**: 외부 사용자가 import 하는 public API. 버전 호환성 약속.
- **제공자 profiles**: `python-lib`
- **6축 derived**: 없음
- **사용 fragments**: `interface.sdk`
- **근거**: 라이브러리 프로파일만. SemVer 호환성 + public 표면.

### `ipc` — 프로세스 간 통신

- **정의**: Electron main↔renderer, native bridge 같은 IPC. tRPC 도 일부 해당.
- **제공자 profiles**: `electron`
- **6축 derived**: 없음
- **사용 fragments**: `interface.ipc`
- **근거**: 데스크톱 프로파일에서 main process ↔ renderer 통신.

### `navigation` — 모바일 네비게이션

- **정의**: 화면 간 전환 + 딥링크 + 백 스택 관리. Expo Router / go_router / NavigationStack.
- **제공자 profiles**: `react-native-expo`, `flutter`, `android-kotlin`, `ios-swift`
- **6축 derived**: 없음
- **사용 fragments**: `mobile.navigation`
- **근거**: 모바일 4종만. 웹은 url 기반 라우팅이라 별도 (mobile.navigation 안 씀).

### `lifecycle` — 앱 라이프사이클

- **정의**: foreground/background 전환, 권한, 푸시 알림 처리.
- **제공자 profiles**: `react-native-expo`, `flutter`, `android-kotlin`, `ios-swift`
- **6축 derived**: 없음
- **사용 fragments**: `mobile.lifecycle`
- **근거**: 모바일 OS 의 lifecycle 이벤트. 웹은 가능하지만 SPA 본질 약함.

### `build_config` — 빌드 설정

- **정의**: 환경별 빌드 변형 (dev/staging/prod), 시그니처, 번들 ID.
- **제공자 profiles**: `react-native-expo`, `flutter`, `android-kotlin`, `ios-swift`
- **6축 derived**: 없음
- **사용 fragments**: `mobile.build_config`
- **근거**: 모바일은 빌드 단계가 복잡 (EAS / Gradle / xcconfig). 웹은 단순 (.env).

### `storage` — 영구 저장소

- **정의**: 디바이스 또는 서버 측 영구 저장. SQLite / AsyncStorage / SecureStore / DB.
- **제공자 profiles**: `react-native-expo`, `flutter`, `android-kotlin`, `ios-swift`
- **6축 derived**: 없음
- **사용 fragments**: `persistence`, `data_model`
- **근거**: 모바일 앱은 거의 항상 로컬 저장소. 백엔드는 별도 명시 안 함 (현재 fastapi/nestjs `provides_capabilities` 에 storage 없음 — 백엔드 DB 는 ORM 화이트리스트로 검증).

### `complex_state` — 클라이언트 복잡 상태

- **정의**: 단순 useState 를 넘어선 글로벌/공유 상태. Zustand / Redux / Riverpod / @StateObject.
- **제공자 profiles**: `react-vite`, `nextjs`, `electron`, `react-native-expo`, `android-kotlin`, `ios-swift`, `flutter`
- **6축 derived**: 없음
- **사용 fragments**: `state.flow`
- **근거**: UI + interactive 프로파일. CLI / lib 는 본질적으로 stateless.

### `env_config` — 환경변수

- **정의**: 빌드/실행 시점 환경별 설정. .env, app.config.ts, --dart-define.
- **제공자 profiles**: `fastapi`, `nestjs`, `nextjs`, `electron`, `react-vite`, `react-native-expo`, `python-cli`, `flutter`
- **6축 derived**: 없음
- **사용 fragments**: `configuration`
- **근거**: 대부분의 운영 프로파일. android-kotlin / ios-swift 는 BuildConfig / xcconfig 가 별도 (build_config 와 중복) — 명시 제외.

### `production_concerns` — 운영 관심사

- **정의**: 모니터링, 알람, 로깅, 배포, CI/CD. SLO / runbook 의 전제.
- **제공자 profiles**: `fastapi`, `nestjs`, `nextjs`
- **6축 derived**: 없음 (Group 1 보강에서 검토했으나 mobile-only 와의 충돌로 제외)
- **사용 fragments**: `observability`, `deployment`, `slo`, `runbook`
- **근거**: 백엔드/풀스택만 본질적 production_concerns. 모바일 앱의 운영 (Sentry/Crashlytics) 은 별도 영역 — 현재 atom 으로 분리 안 됨 (잠재 결함).

### `users` — 사용자 계정 / 식별

- **정의**: 다중 사용자 시스템. 인증, 권한, 사용자별 데이터 격리.
- **제공자 profiles**: 없음 (capability 가 직접 제공되는 게 아니라 의도에서 도출)
- **6축 derived**:
  - `data_sensitivity in [pii, payment]` → users
  - `monetization in [subscription, payment]` → users
- **사용 fragments**: `auth`, `authorization_matrix`, `user_journey`, `audit_log` (threat_model 트리거에도 영향)
- **근거**: 프로파일 자체가 user system 을 강제하지 않음. 사용자 의도 (PII 보유, 결제 monetization) 가 multi-user 시스템 필요성을 시사.

### `external_deps` — 외부 시스템 의존성

- **정의**: 3rd-party API, 외부 SaaS, decoupled service.
- **제공자 profiles**: 없음 (의도된 gap)
- **6축 derived**: 없음
- **사용 fragments**: `external_deps`, `integrations`
- **근거**: 모든 프로파일이 외부 의존성 가능. 자동 derive 매핑이 적절하지 않아 의도적으로 비어둠. 사용자가 직접 `external_capabilities: [external_deps]` 로 명시하거나 `--included` override 로 활성.

## 4. 신규 capability atom 추가 절차

1. `capabilities.py::KNOWN_CAPABILITY_ATOMS` 에 추가 (알파벳 순서 유지)
2. 다음 중 최소 하나 충족:
   - 적어도 하나의 프로파일에 `provides_capabilities` 추가
   - `derive_axes_capabilities` 에 매핑 추가
   - 사용자가 `--external-capabilities` 로 명시 가능하도록 문서
3. 백엔드 프로파일이 제공할 수 있다면 `consistency.py::_HAS_KEY_PROVIDERS` 에 매핑 추가
4. fragment 의 `required_when` 에서 참조
5. 본 문서의 atom 목록 (§3) 에 새 항목 추가:
   - 정의 / 제공자 / 사용 fragments / 근거
6. 테스트 통과 확인:
   - `test_capability_atoms_consistency.py` 의 invariant 8개 모두 PASS

## 5. 매핑 한계 (의식적 미해결)

- **`production_concerns` 의 axes-derived 매핑 부재**: `lifecycle == ga` 가 production_concerns 를 자동 활성하면 안전해 보이지만, mobile-only 프로젝트 (mvp 라이프사이클 + mobile profile) 에 SLO / runbook 같은 백엔드용 섹션이 활성되는 false-positive 위험. 사용자가 `--external-capabilities production_concerns` 명시로만 활성 — 의식적 보수.
- **`team_size` ↔ `users` 매핑 부재**: team_size 는 *개발팀* 규모 (`solo` / `small 2-5명` / `multi 6명+`) 의미. *사용자* 식별과 무관. 매핑 안 함.
- **모바일 production_concerns 분리 부재**: 모바일 앱의 Sentry / Crashlytics / TestFlight 같은 운영도 production_concerns 의 일부일 수 있으나, 현재 atom 으로는 백엔드 운영과 구분 못함. 잠재 미래 결함 (별도 atom 분리 또는 fragment 본문 분기 필요).
- **`external_deps` provider gap**: 의도된 상태. 사용자가 직접 명시.

## 6. BaaS / 외부 backend 사용 (Group 1-D)

`plan.external_capabilities` 필드로 사용자가 명시:

```yaml
external_capabilities:
- http_server
- storage
- users
```

또는 CLI:

```bash
harness migrate-plan ... # OR
~/.claude/skills/ha-init/run.py write \
  --profiles react-native-expo \
  --external-capabilities "http_server,users,storage" \
  ...
```

효과:
- `compute_has_keys` 가 외부 capability 도 union → fragment 활성에 반영
- `find_consistency_violations` 가 external 인정 → false-positive 제거

예: Firebase 사용 RN 앱은 `react-native-expo` profile + `external_capabilities=[http_server, users, storage]` 명시. `auth`, `persistence`, `interface.http` 모두 정당하게 활성, consistency violation 없음.

## 7. 변경 이력

본 문서의 변경은 `capabilities.py`, `consistency.py`, profile frontmatter, fragment trigger 와 동기. 코드 변경 시 본 문서도 동시 갱신 — `feedback_holistic_thinking` 룰.

- 2026-05-11: Group 1 보강 단계 A+C+D+E 완료 — 본 문서 신규 작성.
