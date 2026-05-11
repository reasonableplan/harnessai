---
id: ios-swift
name: iOS Swift (SwiftUI)
status: confirmed
extends: _base
version: 1
maintainer: harness-core

paths: [".", "ios/", "apps/ios/"]
detect:
  files_any: [Package.swift, Podfile]

components:
  - id: view.screens
    required: true
    skeleton_section: view.screens
    description: SwiftUI View (`Sources/<App>/Views/<Feature>View.swift`) — NavigationStack route 와 1:1
  - id: view.components
    required: true
    skeleton_section: view.components
    description: 공용 View / Modifier (`Sources/<App>/Components/`) + feature 별 (`Sources/<App>/Views/<Feature>/Components/`)
  - id: state.flow
    required: true
    skeleton_section: state.flow
    description: "@Observable (Swift 5.9+) 또는 @StateObject — sealed enum UI state"
  - id: mobile.navigation
    required: true
    skeleton_section: mobile.navigation
    description: NavigationStack + NavigationPath + value-typed routes (iOS 16+)
  - id: mobile.build_config
    required: true
    skeleton_section: mobile.build_config
    description: Build Configuration (Debug/Staging/Release) + xcconfig 분리 + Info.plist
  - id: mobile.lifecycle
    required: true
    skeleton_section: mobile.lifecycle
    description: scenePhase + AVCaptureDevice.requestAccess + BGTaskScheduler + APNS
  - id: persistence
    required: false
    skeleton_section: persistence
    description: CoreData 또는 SwiftData (iOS 17+) + Keychain (시크릿)
  - id: interface.http
    required: false
    skeleton_section: interface.http
    description: URLSession + async/await + Codable (paired 모드만)
  - id: core.logic
    required: true
    skeleton_section: core.logic
    description: 도메인 로직 (`Sources/<App>/Domain/`) — pure Swift

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
  order:
    - overview
    - requirements
    - stack
    - configuration
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
    - tasks
    - notes

# ⚠️ Windows 호스트 제약 (사용자 환경): SwiftLint + swift build dry-run 만.
# xcodebuild test 는 macOS GitHub Actions runner CI 후속 (M4+).
toolchain:
  install: "swift package resolve"
  test: null   # macOS 에서만 xcodebuild test 가능 — Win 에서는 skip
  lint: "swiftlint lint --strict"
  type: "swift build"   # SPM 기반 부분 컴파일 검증 (Win 호스트 가능)
  format: "swiftlint --fix"

whitelist:
  runtime:
    # SPM only — CocoaPods 금지 (관리 일관성 + Xcode 통합)
    # Apple 공식 frameworks (Foundation/SwiftUI/CoreData/URLSession 등) 은
    # 시스템 제공이라 화이트리스트 X — 외부 SPM 패키지만 명시.
    - swift-collections        # github.com/apple/swift-collections
    - swift-algorithms          # github.com/apple/swift-algorithms
    - swift-async-algorithms    # github.com/apple/swift-async-algorithms
    - keychain-access           # github.com/kishikawakatsumi/KeychainAccess
    - swift-log                 # github.com/apple/swift-log
    - sentry-cocoa              # github.com/getsentry/sentry-cocoa (선택)
  dev:
    - swiftlint
  prefix_allowed:
    - "Apple"     # Apple 공식 SPM 패키지 (swift-* 포함)

file_structure: |
  ios/                       # 또는 apps/ios/
    Package.swift            # SPM root (Apps + Targets)
    .swiftlint.yml           # SwiftLint 룰 (strict 모드 + disabled_rules 사유 주석)
    .env.example             # xcconfig 주입 변수 목록
    Configurations/
      Debug.xcconfig         # API_BASE_URL 등 debug 환경변수
      Staging.xcconfig
      Release.xcconfig       # release 만 dSYM 업로드 (Sentry/Crashlytics)
    Sources/
      <App>/
        App.swift            # @main App + WindowGroup
        Domain/              # pure Swift — UI / IO 의존 X
          Models/
          UseCases/
        Data/
          Local/             # CoreData / SwiftData
          Remote/            # URLSession 기반 API client
          Repositories/
        Views/
          Theme/             # Color + Font + Style modifiers
          Components/        # AppButton / AppTextField / ToastView
          Navigation/        # AppRouter + Routes
          <Feature>/
            <Feature>View.swift
            <Feature>Model.swift   # @Observable
            Components/
        Resources/           # Localizable.strings + Assets.xcassets
    Tests/
      <App>Tests/            # XCTest (단위)
      <App>UITests/          # XCUITest (UI E2E — macOS only)

provides_capabilities:
  - ui
  - navigation
  - lifecycle
  - build_config
  - storage
  - complex_state

gstack_mode: manual
gstack_recommended:
  before_design: [office-hours]
  after_design: [plan-design-review]
  after_build: [design-review, review]
  before_ship: [qa]
  after_ship: [retro]

lessons_applied:
  - LESSON-006   # 입력 — iOS 는 keyboardType: .decimalPad / .numberPad 사용
  - LESSON-STYLE-001   # ViewModifier 추출 — 인라인 modifier 체인 5개 이상 시 별도 modifier
---

# iOS Swift (SwiftUI) Profile

## ⚠️ Windows 호스트 제약 (사용자 환경 2026-05-07)

- 빌드 검증은 **SwiftLint + `swift build`** dry-run 만
- `xcodebuild test` 는 **macOS GitHub Actions runner CI** 후속 (M4+)
- 시뮬레이터 / 실기기 테스트는 macOS 단계에서만
- Win 에서 컴파일 / 타입 / lint 통과까지 보장 — UI / 런타임 검증은 macOS

## 핵심 원칙

- **SwiftUI 단일** — UIKit 신규 사용 금지 (기존 코드 마이그레이션 시만)
- **MV pattern** (Apple 공식) — View ↔ Model 직접 바인딩. ViewModel 없이도 OK (복잡 도메인은 Service / Repository 별도)
- **`@Observable` (Swift 5.9+)** — `ObservableObject` + `@Published` 보다 우선
- **NavigationStack** (iOS 16+) + value-typed routes — `NavigationView` deprecated
- **SPM only** — CocoaPods 금지 (Xcode 통합 + 관리 일관성)
- **Codable + JSONDecoder/Encoder** — 별도 JSON 라이브러리 금지
- **`async/await`** — completion handler / Combine 신규 사용 금지

## components.view.screens
- `Sources/<App>/Views/<Feature>/<Feature>View.swift` — SwiftUI View struct
- View 는 stateless — `@State` 는 view-local UI state 만 (하단 modal 열림 등)
- 도메인 state 는 `@Observable` 모델 또는 `@Environment`
- `.task { ... }` 안에서 await — `Task { ... }` 직접 생성은 lifecycle 주의

## components.view.components
- 공용: `Sources/<App>/Views/Components/` (AppButton, AppTextField, ToastView)
- Feature 전용: `Sources/<App>/Views/<Feature>/Components/`
- ViewModifier 로 재사용 패턴 추출 (`func cardStyle() -> some View`)

## components.state.flow
- `@Observable class FeatureModel { ... }` (Swift 5.9+) — `@Published` 불필요
- 또는 `@Observable @MainActor class FeatureModel`
- View: `@State private var model = FeatureModel()` 또는 `@Environment(FeatureModel.self) private var model`
- async work: View 의 `.task { await model.load() }` 안에서

## components.mobile.navigation
- **NavigationStack + NavigationPath** (iOS 16+)
- `.navigationDestination(for: Route.self) { route in DetailView(route: route) }`
- Route 는 `enum Route: Hashable { case item(id: Int); case settings }`
- Deep link: `.onOpenURL { url in path.append(parseRoute(url)) }`
- Modal: `.sheet(isPresented:) { ... }` / `.fullScreenCover(...)`
- Back: `path.removeLast()` 또는 `dismiss()` (Environment)

## components.mobile.build_config
- **Build Configuration**: Debug / Staging / Release — Xcode `Configurations/` 디렉토리에 xcconfig 분리
- 환경변수: `Bundle.main.infoDictionary?["API_BASE_URL"]` 또는 `ProcessInfo.processInfo.environment["..."]`
- 시크릿: **xcconfig 의 release Configuration 만**, 절대 평문 코드 X
- Info.plist 에 환경별 분기는 `$(VARIABLE_NAME)` 매크로
- Bundle ID + Version: project.pbxproj 의 build settings 단일 source

## components.mobile.lifecycle
- 권한: `AVCaptureDevice.requestAccess(for: .video) { granted in ... }` — 사용 시점에만
- 거부 시 fallback + `UIApplication.shared.open(URL(string: UIApplication.openSettingsURLString)!)`
- 앱 상태: SwiftUI `@Environment(\.scenePhase)` + `.onChange(of: scenePhase) { newPhase in ... }`
- 백그라운드: `BGTaskScheduler.shared.register(forTaskWithIdentifier: "...")` (Info.plist `BGTaskSchedulerPermittedIdentifiers` 필수)
- 푸시: `UNUserNotificationCenter` + APNS — release Configuration 만 활성

## components.persistence (선택)
- 관계형 (iOS 13+): **CoreData** + `NSPersistentContainer` + 백그라운드 컨텍스트 분리
- 관계형 (iOS 17+): **SwiftData** (`@Model class Item { ... }`) — type-safe API 권장
- 마이그레이션: lightweight migration 우선 (`NSPersistentStoreDescription` 의 `NSMigratePersistentStoresAutomaticallyOption`)
- 시크릿: **Keychain** (`KeychainAccess` SPM 패키지) — `UserDefaults` 금지

## components.interface.http (paired 모드만)
- `Sources/<App>/Data/Remote/APIClient.swift` 의 actor 또는 class
- `URLSession.shared.data(for: request)` async/await
- JSON: `JSONDecoder` + `Codable` (`keyDecodingStrategy = .convertFromSnakeCase`)
- 401 처리: refresh token → retry (Sendable 안전 보장)

## 금지 사항 (iOS 특화)

- UIKit 신규 사용 (SwiftUI only — 기존 코드 별도)
- NSObject / Objective-C bridging 신규 (Swift native)
- Combine 신규 사용 (async/await 만)
- `print()` 프로덕션 — `os.Logger` 또는 `swift-log` 사용
- **force unwrap (`!`)** — `guard let` / `if let` / `??` (테스트 코드도 권장)
- private API / runtime introspection (App Store reject)
- Keychain 외 시크릿 저장 (`UserDefaults` 금지)
- SwiftLint 룰 약화 (`disabled_rules` 사용 시 사유 주석 + PR 설명 필수)
- **CocoaPods** (SPM 만)
- `@StateObject` 와 `@Observable` 혼용 (Swift 5.9+ 는 `@Observable` 만)

## 검증 명령

### Windows 호스트 (사용자 환경)
```bash
cd <ios_dir>
swift package resolve
swiftlint lint --strict
swift build              # SPM 기반 타입 / 컴파일 검증 (UIKit 미포함 부분만 가능)
```

### macOS CI (M4+ 후속)
```bash
xcodebuild build -scheme <Scheme> -configuration Debug
xcodebuild test -scheme <Scheme> -destination 'platform=iOS Simulator,name=iPhone 15'
```
