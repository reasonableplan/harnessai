# Mobile Coder — 공통 원칙 (4개 mobile_coder_* 가 모두 따름)

> ⚠️ **본 문서는 사람용 reference** — runner 가 자동 로드하지 않음 (markdown 링크 follow X).
> 4개 mobile_coder 프롬프트 (`mobile_coder_rn/_flutter/_android/_ios/CLAUDE.md`) 의 "골든 원칙 (모바일 공통)" 섹션에 핵심 룰이 인라인됨.
> 본 파일을 수정하면 4개 프롬프트의 인라인 섹션도 함께 동기화 필요.

이 문서는 `mobile_coder_rn` / `mobile_coder_flutter` / `mobile_coder_android` / `mobile_coder_ios` 가 공통으로 지켜야 할 원칙의 **확장판** 이다 — 프레임워크별 디테일 (RN AsyncStorage / Flutter shared_preferences / Android EncryptedSharedPreferences / iOS Keychain 등) 의 패턴 비교에 활용.

## 1. 오프라인 우선

- 네트워크 실패 시 **stale 데이터 표시 + 사용자 알림**. 빈 화면 또는 무한 로딩 X
- 쓰기 작업은 로컬 큐에 저장 → 네트워크 복귀 시 동기화
- 충돌 해결 정책: last-write-wins / version-based merge / 사용자 선택 — skeleton 의 `mobile.lifecycle` 또는 `persistence` 섹션에서 결정 그대로 따름

## 2. 권한 정책

- **사용 시점에 요청** — 앱 시작 시 일괄 요청 금지 (UX 안티패턴)
- 거부 후 재요청은 **1회만** — OS 가 차단하면 시스템 설정 deeplink 안내
- 권한별 fallback 명시 (카메라 거부 → 갤러리만, 위치 거부 → 수동 입력)
- skeleton 의 `mobile.lifecycle` 표에 적힌 트리거/fallback 그대로 구현

## 3. 시크릿 / 서명

- **코드/리소스에 시크릿 절대 X** — keystore / API key / Sentry DSN 등은 환경변수 또는 빌드 시점 주입
- 토큰 저장: SecureStore / Keychain / EncryptedSharedPreferences — 일반 storage 금지
- `.env.example` 에 키 이름만 (값 X)
- skeleton 의 `mobile.build_config` 의 서명 정책 그대로

## 4. 빌드 변형

- debug / staging / release **3 변형 분리** 강제
- debug: verbose 로깅, source map, dev tools 활성
- release: error 만 로깅, source map 외부 (Sentry 등), dev tools 비활성
- skeleton `mobile.build_config` 의 변형 표 그대로 구현

## 5. 접근성 (a11y)

- 모든 인터랙티브 요소에 **accessibility label/hint** 필수
- 색상 대비 4.5:1 이상 (WCAG AA)
- 폰트 사이즈 시스템 설정 따름 (절대값 px 금지, 상대 단위)
- VoiceOver / TalkBack 시연 — 인증 흐름 / 결제 흐름 / 핵심 기능

## 6. 배터리 / 네트워크 인식

- 배터리 절감 모드 시: 백그라운드 작업 미실행 / 폴링 주기 늘림
- Wi-Fi 만 / 셀룰러 포함 — 사용자 선택 존중 (대용량 다운로드 등)
- 위치 추적은 필요 최소 정확도 (Fine vs Coarse)

## 7. 앱 상태 전환

- foreground → background: form dirty / scroll position / 검색어 보존
- background → terminated: 인증 상태 + 마지막 라우트 영속화
- cold start: deep link 우선 처리 → 인증 검사 → initial route
- skeleton `mobile.lifecycle` 의 표 그대로

## 8. 금지 사항 (모든 mobile_coder)

- `console.log` (또는 print/println) 프로덕션 코드 — logger 래퍼 사용
- AsyncStorage / SharedPreferences / UserDefaults 에 시크릿 저장
- 인라인 스타일 2개 이상 (StyleSheet / Theme / Style 으로)
- `any` 타입 (TypeScript / Dart `dynamic`) — 진짜 동적이면 사유 주석
- 무한 페이지네이션 limit 없음 — 항상 page size + total count
- 직접 OS API 호출 (Android Java reflection, iOS private API 등)

## 9. 입력 / 출력

**입력**:
- skeleton.md — 특히 `mobile.navigation`, `mobile.build_config`, `mobile.lifecycle`, `view.screens`, `state.flow`, `persistence`, `interface.http` (페어링 시)
- Orchestrator 가 작성한 태스크 스펙 블록 (생성/수정 파일 + skeleton 참조 + 구현 세부 + 테스트 + 완료 기준)

**출력**:
- 스펙 블록의 NEW / MOD 파일 그대로 구현
- 스펙에 없는 결정 추가 금지 → 미흡 시 `--status blocked` 에스컬레이션
- 테스트 파일 함께 작성 (LESSON-021)
- 검증 명령 출력 (toolchain test/lint/type 모두 통과 증거)

## 10. 프레임워크별 특화

각 mobile_coder_* 의 `CLAUDE.md` 가 담당 프레임워크의 컨벤션 (상태 관리 / 네비게이션 / 스타일 / 테스트) 을 명시.
