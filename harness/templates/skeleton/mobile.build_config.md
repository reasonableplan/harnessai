---
id: mobile.build_config
name: 빌드 설정
required_when: has.build_config
description: 빌드 변형 (debug/staging/release), 서명/시크릿 정책, 환경변수 주입, 번들 크기 예산
---

## {{section_number}}. 빌드 설정

### 빌드 변형

| 변형 | 용도 | 환경변수 prefix | 로깅 | 번들 압축 |
|------|------|---------------|------|---------|
| `debug` | 개발 / 시뮬레이터 | `<DEV_>` | verbose | off |
| `staging` | 사내 테스트 / TestFlight 베타 | `<STAGING_>` | info | on |
| `release` | App Store / Play Store | `<PROD_>` | error only | on |

### 환경변수 주입

| 변수 | 어디서 | 변형별 값 | 비고 |
|------|--------|---------|------|
| `<API_BASE_URL>` | `<Expo app.config.ts profiles / Gradle BuildConfig / xcconfig>` | debug=`<localhost>` / staging=`<...>` / release=`<...>` | URL 만 — 토큰/키 X |
| `<SENTRY_DSN>` | (필요 시) | release 만 enabled | dev 에서는 noisy |

> **시크릿 절대 코드/리소스 X** — env 파일은 빌드 타임 주입, gitignore. 루트 `.env.example` 에 키 이름만 기록.

### 서명 / 코드 사이닝

#### Android (`mobile.build_config.android`)
- keystore 파일: `<경로 — git 외부, 안전 백업>`
- keystore 비밀번호: 환경변수 `<KEYSTORE_PASSWORD>`
- key alias: `<alias>`
- v1 + v2 + v3 서명 모두 활성

#### iOS (`mobile.build_config.ios`)
- Apple Developer Team ID: `<10자리>`
- Provisioning Profile: `<Development / Distribution>`
- Bundle Identifier: `<com.example.app>`
- 자동 서명 vs 수동: `<선택>`

### 번들 크기 예산

| 항목 | 예산 | 측정 방법 |
|------|------|---------|
| 초기 번들 (RN) | `<6 MB>` | `expo export --dump-sourcemap` |
| 초기 번들 (Flutter) | `<8 MB>` | `flutter build apk --analyze-size` |
| 이미지 자산 총량 | `<2 MB>` | `<측정 명령>` |
| 최대 화면 진입 시간 | `<3초>` | `<측정 — TTI 등>` |

### 배포 채널 (선택)

- **Expo OTA**: JS/asset 만 OTA, 네이티브 코드 변경 시 store 업데이트
- **Firebase App Distribution**: 베타 배포
- **Google Play Internal Testing / TestFlight**: 정식 베타

### 버전 관리

- semver 정책: `<MAJOR.MINOR.PATCH>`
- buildNumber: `<자동 증가 / 수동>`
- iOS `CFBundleShortVersionString` ↔ `CFBundleVersion` 분리 정책

> 작성 가이드:
> - **시크릿 누수 0** — keystore / API key / Sentry DSN 모두 env 또는 별도 파일, gitignore 강제
> - **release 와 debug 의 차이를 명시** — 둘 다 똑같으면 변형 의미 없음
> - **번들 크기 예산은 측정 가능한 수치로** — "최소화" 같은 모호 표현 금지
> - **프레임워크별 권장**:
>   - RN+Expo: `app.config.ts` + `EAS_PROFILE` env, `eas.json` profiles
>   - Flutter: `--flavor` + `--dart-define` + `flavorDimensions` (Gradle), Xcconfig (iOS)
>   - Android: `buildTypes` (debug/release/staging) + `productFlavors`
>   - iOS: Build Configuration (Debug/Staging/Release) + xcconfig 파일
