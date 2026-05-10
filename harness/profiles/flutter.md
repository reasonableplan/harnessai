---
id: flutter
name: Flutter (Dart)
status: confirmed
extends: _base
version: 1
maintainer: harness-core

paths: [".", "apps/mobile/", "mobile/"]
detect:
  files: [pubspec.yaml]
  contains:
    pubspec.yaml: ["flutter:"]

components:
  - id: view.screens
    required: true
    skeleton_section: view.screens
    description: lib/screens/<domain>/ — go_router route → screen widget 1:1
  - id: view.components
    required: true
    skeleton_section: view.components
    description: lib/widgets/ 공용 + lib/screens/<domain>/widgets/ 도메인별
  - id: state.flow
    required: true
    skeleton_section: state.flow
    description: Riverpod (Notifier / AsyncNotifier) — 도메인별 provider
  - id: mobile.navigation
    required: true
    skeleton_section: mobile.navigation
    description: go_router declarative routing + redirect callback
  - id: mobile.build_config
    required: true
    skeleton_section: mobile.build_config
    description: --flavor + --dart-define + flavor-specific Gradle/xcconfig
  - id: mobile.lifecycle
    required: true
    skeleton_section: mobile.lifecycle
    description: permission_handler + WidgetsBindingObserver + firebase_messaging
  - id: persistence
    required: false
    skeleton_section: persistence
    description: drift / sqflite / shared_preferences / flutter_secure_storage
  - id: interface.http
    required: false
    skeleton_section: interface.http
    description: dio + interceptor (paired 모드만)
  - id: core.logic
    required: true
    skeleton_section: core.logic
    description: 유틸 (formatters, validators) — pure Dart

skeleton_sections:
  required:
    - overview
    - stack
    - view.screens
    - view.components
    - state.flow
    - mobile.navigation
    - mobile.build_config
    - mobile.lifecycle
    - core.logic
    - tasks
    - notes
  optional:
    - requirements
    - configuration
    - errors
    - auth
    - persistence
    - interface.http
    - error_ux
    - environments
  order:
    - overview
    - requirements
    - stack
    - configuration
    - environments
    - errors
    - auth
    - mobile.build_config
    - mobile.lifecycle
    - persistence
    - interface.http
    - mobile.navigation
    - view.screens
    - view.components
    - state.flow
    - core.logic
    - error_ux
    - tasks
    - notes

toolchain:
  install: "flutter pub get"
  test: "flutter test"
  lint: "flutter analyze"
  type: null   # flutter analyze 가 type 검사 포함 — 별도 명령 불필요
  format: "dart format --set-exit-if-changed ."

whitelist:
  runtime:
    - flutter
    - flutter_riverpod
    - go_router
    - dio
    - drift
    - sqflite
    - shared_preferences
    - flutter_secure_storage
    - freezed_annotation
    - json_annotation
    - intl
    - cached_network_image
    - permission_handler
    - geolocator
    - firebase_core
    - firebase_messaging
    - firebase_analytics
    - cupertino_icons
  dev:
    - flutter_test
    - flutter_lints
    - build_runner
    - freezed
    - json_serializable
    - drift_dev
    - mockito
    - mocktail
    - integration_test
  prefix_allowed:
    - "google_"   # google_fonts, google_maps_flutter 등 (Google 공식)

file_structure: |
  mobile/                    # 또는 apps/mobile/
    pubspec.yaml
    pubspec.lock             # 커밋 (Flutter 표준)
    analysis_options.yaml    # flutter_lints + 추가 strict 룰
    build.yaml               # build_runner 설정
    .env.example             # --dart-define 변수 목록
    android/                 # Gradle 설정 (flavor / 서명)
    ios/                     # xcconfig (flavor)
    lib/
      main.dart              # 엔트리포인트 — flavor 별 main_dev/staging/prod.dart
      app/
        app.dart             # MaterialApp.router(routerConfig: appRouter)
        router.dart          # go_router 설정 (redirect / routes)
        theme.dart           # ThemeData (light/dark, Material3)
      shared/
        widgets/             # AppButton / AppInput / AppDialog
        providers/           # auth_provider.dart
        api/
          api_client.dart    # dio + interceptor
        models/              # Freezed + JsonSerializable
        utils/
      screens/
        <domain>/
          <domain>_screen.dart       # ConsumerWidget — Riverpod 연결
          widgets/                   # 화면 전용 widget
          providers/<domain>_provider.dart  # AsyncNotifier
      core/
        validators/
        formatters/
    test/
      unit/
      widget/
    integration_test/
    assets/
      images/
      fonts/

gstack_mode: manual
gstack_recommended:
  before_design: [office-hours]
  after_design: [plan-design-review]
  after_build: [design-review, review]
  before_ship: [qa]
  after_ship: [retro]

lessons_applied:
  - LESSON-006   # 입력 — Flutter 는 TextInputType.numberWithOptions(decimal: true) + inputFormatters
  - LESSON-STYLE-001   # ThemeData / Theme.of(context) 사용 — 인라인 BoxDecoration 2개 이상 금지
---

# Flutter (Dart) Profile

## 핵심 원칙

- **Riverpod 단일화** — Provider / setState 직접 사용 최소화. AsyncNotifier 로 비동기 상태 표준화
- **go_router** — Navigator 1.0 (Navigator.push) 직접 사용 금지. routerConfig 단일 source
- **Material3 ThemeData 단일화** — 색상 / 폰트 / spacing 모두 Theme.of(context) 경유
- **Freezed + JsonSerializable** — DTO / Domain 모델 모두 immutable + sealed
- **`build_runner`** 빌드 누락 시 빌드 fail — PR 마다 `dart run build_runner build --delete-conflicting-outputs` 검증
- **`pubspec.lock` 커밋 필수** — Flutter 표준 (web 의 lockfile 와 다름)

## components.view.screens
- **lib/screens/<domain>/<domain>_screen.dart** — ConsumerWidget 또는 ConsumerStatefulWidget
- go_router route → screen 1:1 매핑 (router.dart 에 정의)
- Provider 만 통한 상태 접근 — 화면이 `Riverpod.read` 로 action 호출

## components.view.components
- **공용**: lib/shared/widgets/ — AppButton / AppInput / AppDialog (Theme 만 사용)
- **도메인 전용**: lib/screens/<domain>/widgets/
- **stateless 우선** — 상태 필요 시 ConsumerWidget 으로 Provider 구독

## components.state.flow
- 도메인별 provider: `lib/screens/<domain>/providers/<domain>_provider.dart`
- AsyncNotifier (비동기 fetch + mutate) / Notifier (동기 UI state)
- Provider 사이 의존: ref.watch / ref.read 명시
- StateProvider 는 **단순 enum / bool 만** — 복잡 state 는 Notifier

## components.mobile.navigation
- **go_router** declarative — `GoRouter(routes: [...])` 단일 source
- Route guard: `redirect` callback (auth state 검사)
- Deep linking: pubspec 에 `app_links` 또는 go_router 의 native scheme 설정
- Navigator 2.0 / Navigator 1.0 직접 사용 금지

## components.mobile.build_config
- `--flavor dev|staging|prod` + `lib/main_<flavor>.dart` entrypoint 분리
- 환경변수: `--dart-define=API_BASE_URL=...` (빌드 시점 주입)
- 시크릿: `--dart-define-from-file=secrets.json` (gitignore) 또는 EAS-style secret manager
- Android: `productFlavors` (Gradle), iOS: xcconfig

## components.mobile.lifecycle
- 권한: `permission_handler` 의 `Permission.camera.request()` — 사용 시점에만
- 백그라운드: `workmanager` 또는 `flutter_background_service`
- 앱 상태: `WidgetsBindingObserver` 의 `didChangeAppLifecycleState`
- 푸시: `firebase_messaging` (FCM) — iOS 는 APNS 자동 변환

## components.persistence (선택)
- 관계형: **drift** (sqflite 위 type-safe) 권장
- 단순 KV: `shared_preferences`
- 시크릿: **`flutter_secure_storage`** (Keychain / EncryptedSharedPreferences)
- ObjectBox / Hive 는 신중히 (의존성 / native 빌드 복잡도)

## components.interface.http (paired 모드만)
- `lib/shared/api/api_client.dart` 의 `Dio` 단일 인스턴스
- Interceptor: 401 → refresh → 원 요청 재시도, log (debug only), retry (network error)
- JSON: `json_serializable` (Freezed 호환)

## 금지 사항 (Flutter 특화)

- `dynamic` 타입 — `Object?` + null check 또는 sealed class
- `print()` — `debugPrint` 또는 `logger` 패키지
- 비동기 작업 후 `mounted` 체크 누락 → `setState` / `Navigator` 호출
- Navigator 1.0 (`Navigator.push` / `Navigator.pop` 직접) — go_router 만
- `Provider` 패키지 사용 (Riverpod 와 혼용 금지)
- 인라인 `BoxDecoration` 2개 이상 — `BoxDecoration` 변수 추출 또는 Theme extension
- `setState` 가 build 메서드 안에서 호출되는 패턴
- `pubspec.lock` gitignore (커밋 강제)
- `analysis_options.yaml` 의 `lints` 약화 (이유 주석 + PR 설명 없으면 거부)

## 검증 명령

```bash
cd <flutter_dir>
flutter pub get
flutter test
flutter analyze
dart format --set-exit-if-changed .
dart run build_runner build --delete-conflicting-outputs   # codegen 필요 시
```
