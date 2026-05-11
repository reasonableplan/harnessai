---
id: android-kotlin
name: Android Kotlin (Jetpack Compose)
status: confirmed
extends: _base
version: 1
maintainer: harness-core

paths: [".", "android/", "apps/android/"]
detect:
  files_any: [build.gradle.kts, build.gradle, settings.gradle.kts]

components:
  - id: view.screens
    required: true
    skeleton_section: view.screens
    description: Compose 화면 (`ui/<feature>/<Feature>Screen.kt`) — Navigation Compose 와 1:1
  - id: view.components
    required: true
    skeleton_section: view.components
    description: 공용 Composable (`ui/components/`) + feature 별 (`ui/<feature>/components/`)
  - id: state.flow
    required: true
    skeleton_section: state.flow
    description: ViewModel + StateFlow / SharedFlow — sealed class UI state (Loading/Success/Error)
  - id: mobile.navigation
    required: true
    skeleton_section: mobile.navigation
    description: Navigation Compose (`composable("route") { ... }`) + deep link + redirect
  - id: mobile.build_config
    required: true
    skeleton_section: mobile.build_config
    description: Gradle buildTypes + productFlavors + signingConfigs + BuildConfig env 주입
  - id: mobile.lifecycle
    required: true
    skeleton_section: mobile.lifecycle
    description: ActivityCompat.requestPermissions + WorkManager + Doze 모드 + savedStateHandle
  - id: persistence
    required: false
    skeleton_section: persistence
    description: Room (DAO + Entity + Migration) + DataStore (Preferences)
  - id: interface.http
    required: false
    skeleton_section: interface.http
    description: Retrofit + OkHttp + Moshi (paired 모드만)
  - id: core.logic
    required: true
    skeleton_section: core.logic
    description: 도메인 로직 (`domain/usecase/`, `domain/model/`) — pure Kotlin

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

toolchain:
  install: "./gradlew --refresh-dependencies"
  test: "./gradlew test"
  lint: "./gradlew ktlintCheck"
  type: "./gradlew compileKotlin"
  format: "./gradlew ktlintFormat"

whitelist:
  runtime:
    - androidx.core
    - androidx.activity
    - androidx.lifecycle
    - androidx.compose
    - androidx.navigation
    - androidx.room
    - androidx.datastore
    - androidx.hilt
    - androidx.work
    - androidx.security
    - com.squareup.retrofit2
    - com.squareup.okhttp3
    - com.squareup.moshi
    - com.google.dagger
    - org.jetbrains.kotlinx
    - kotlinx-coroutines-core
    - kotlinx-coroutines-android
    - kotlinx-serialization-json
    - io.coil-kt
  dev:
    - junit
    - androidx.test.ext.junit
    - androidx.test.espresso.core
    - androidx.compose.ui.test
    - org.jetbrains.kotlin.test
    - io.mockk
    - app.cash.turbine
    - org.jlleitschuh.gradle.ktlint
  prefix_allowed:
    - "androidx."     # AndroidX 전체 허용 (각 sub-module 명시 안 해도 됨)
    - "com.google."   # Google 공식 (Material, Firebase 등)

file_structure: |
  android/                   # 또는 apps/android/
    settings.gradle.kts
    build.gradle.kts         # 루트 (subprojects 설정)
    gradle/
      libs.versions.toml     # Version Catalog (의존성 버전 일원화)
      wrapper/gradle-wrapper.properties
    gradlew                  # Unix 실행기
    gradlew.bat              # Windows 실행기
    .env.example             # BuildConfig 주입 변수 목록
    app/
      build.gradle.kts       # productFlavors / buildTypes / signingConfigs
      proguard-rules.pro
      src/
        main/
          AndroidManifest.xml
          java/<pkg>/         # 또는 kotlin/<pkg>/
            MainActivity.kt
            App.kt            # @HiltAndroidApp
            di/               # @Module @InstallIn(SingletonComponent::class)
            data/
              local/
                room/         # @Database, @Dao, @Entity
                datastore/
              remote/
                api/          # Retrofit interface
                dto/          # @JsonClass (Moshi)
              repository/     # Repository impl
            domain/
              model/          # data class — pure Kotlin
              usecase/        # @ViewModelScoped
              repository/     # interface
            ui/
              theme/          # Material3 ColorScheme + Typography + Shape
              components/     # 공용 Composable (AppButton 등)
              navigation/     # NavHost + routes
              <feature>/
                <Feature>Screen.kt
                <Feature>ViewModel.kt
                components/
          res/
            values/strings.xml
            drawable/
        test/                 # unit (junit + mockk + turbine)
        androidTest/          # instrumented (espresso + compose-ui-test)

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
  - LESSON-006   # 입력 — Android 는 inputType="numberDecimal" + IME action 명시
  - LESSON-STYLE-001   # MaterialTheme 단일화 — 인라인 Modifier 체인 5개 이상 시 추출
---

# Android Kotlin (Jetpack Compose) Profile

## 핵심 원칙

- **Jetpack Compose 단일** — XML View / `findViewById` 신규 사용 금지
- **MVVM + Clean Architecture** — `data` / `domain` / `presentation` 레이어 분리
- **StateFlow / SharedFlow** — LiveData 신규 사용 금지
- **Coroutines + Flow** — RxJava / AsyncTask 신규 사용 금지
- **Hilt DI 단일화** — Koin / 수동 DI 금지 (단일 프로젝트 일관성)
- **Version Catalog** (`libs.versions.toml`) 강제 — 라이브러리 버전 분산 금지

## components.view.screens
- `ui/<feature>/<Feature>Screen.kt` — `@Composable` stateless (state hoisting)
- `<Feature>ViewModel.kt` — `@HiltViewModel class ... @Inject constructor(...)`
- UI state: sealed class (Loading / Success / Error) + 단일 data class
- Navigation: `composable("route") { ... }` 안에서 `viewModel: <Feature>ViewModel = hiltViewModel()`

## components.view.components
- 공용: `ui/components/` — Theme + Modifier 만 (도메인 X)
- Feature 전용: `ui/<feature>/components/`
- **stateless 우선** — state hoisting 통해 부모로 끌어올림

## components.state.flow
- `viewModelScope.launch { ... }` 안에서 suspend 호출
- StateFlow 단일 노출 (`val state: StateFlow<UiState> = _state.asStateFlow()`)
- side effect: `Channel` 또는 `SharedFlow` (snackbar / navigation event)
- `init { }` 에서 데이터 로딩 — Compose 의 `LaunchedEffect` 와 분리

## components.mobile.navigation
- **Navigation Compose** — `androidx.navigation:navigation-compose`
- Route: `composable("home") { HomeScreen() }` + `composable("item/{id}", arguments = listOf(navArgument("id") { type = NavType.LongType })) { ... }`
- Auth 가드: `LaunchedEffect(authState) { if (!authState.isAuthenticated) navController.navigate("login") { popUpTo(0) } }`
- Deep link: `composable("route", deepLinks = listOf(navDeepLink { uriPattern = "myapp://item/{id}" }))`
- Back stack: `popUpTo(...) { inclusive = true }` 사용

## components.mobile.build_config
- `productFlavors` — dev / staging / prod (또는 brand 별)
- `buildTypes` — debug (minifyEnabled false) / release (minifyEnabled true + R8 + proguard)
- `signingConfigs` — keystore 파일 path 는 env 변수 (`KEYSTORE_PATH`) — 절대 코드 X
- `BuildConfig` 주입: `buildConfigField("String", "API_BASE_URL", "\"${env}\"")`
- `versionName` / `versionCode` — Gradle 의 git tag 자동 생성 또는 CI 단계에서

## components.mobile.lifecycle
- 권한: `ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.CAMERA), REQ)` — 사용 시점에만
- 백그라운드: `WorkManager` 의 `OneTimeWorkRequest` / `PeriodicWorkRequest` (최소 15분 간격)
- 앱 상태: `ProcessLifecycleOwner.get().lifecycle.addObserver(...)` 로 foreground/background 감지
- Process death: `SavedStateHandle` 의 `getStateFlow` 로 ViewModel 상태 복원
- 푸시: FCM (`FirebaseMessagingService`) — release 변형만 활성

## components.persistence (선택)
- 관계형: **Room** (`@Database`, `@Entity`, `@Dao` + suspend / Flow<T> 반환)
- 마이그레이션: `Migration(from, to)` 객체 명시 (auto-migrate 신중히)
- 단순 KV: **DataStore Preferences** (SharedPreferences 신규 사용 금지)
- 시크릿: **EncryptedSharedPreferences** (androidx.security:crypto)

## components.interface.http (paired 모드만)
- `data/remote/api/` 의 Retrofit interface (`@GET`, `@POST` + suspend)
- OkHttp interceptor: 인증 토큰 주입 + refresh 처리 + retry + logging (debug only)
- JSON: kotlinx.serialization 또는 Moshi (`@JsonClass(generateAdapter = true)`)

## 금지 사항 (Android 특화)

- LiveData 신규 사용 (StateFlow / SharedFlow 만)
- AsyncTask / RxJava (Coroutines + Flow 만)
- `findViewById` / View 시스템 / XML layout (Compose only — 기존 코드는 별도)
- `BuildConfig` 에 시크릿 평문 (release 빌드는 환경변수 주입 / proguard 보호)
- `versions.toml` 외부에 라이브러리 버전 직접 명시 (Version Catalog 일원화)
- `compileSdk` / `targetSdk` 임의 변경 (별도 승인)
- SharedPreferences 신규 사용 (DataStore Preferences)
- 시크릿을 SharedPreferences 에 저장 (EncryptedSharedPreferences 또는 Keystore)
- Hilt 외 DI (Koin 등)
- Kotlin sealed interface 사용 후 `else ->` branch (when 문이 exhaustive)

## 검증 명령

```bash
cd <android_dir>
./gradlew --refresh-dependencies
./gradlew test
./gradlew ktlintCheck
./gradlew compileKotlin
./gradlew ktlintFormat
```
