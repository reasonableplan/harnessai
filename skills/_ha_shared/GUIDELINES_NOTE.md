# Guideline Paths — 프로파일별 컨벤션 문서 목록

`/ha-*` 스킬의 `prepare` 출력 JSON 에 `profiles[].guideline_paths` (또는
`tasks[].guideline_paths`) 경로가 포함됩니다. **작업 시작 전 해당 경로를 모두 Read 로 읽으세요.**

이 파일을 직접 읽는 게 아니라, run.py 출력 JSON 에서 실제 파일 경로를 받아 Read 합니다.

## 프로파일별 파일 구성

| 프로파일 | 파일 수 | 포함 내용 |
|---------|---------|----------|
| `react-native-expo` | 4 | navigation / state / storage / style — Expo Router + Zustand + SecureStore |
| `flutter` | 4 | navigation / state / storage / style — go_router + Riverpod + drift + ThemeData |
| `android-kotlin` | 4 | architecture / compose / network / storage — MVVM + Hilt + Compose + Retrofit + Room |
| `ios-swift` | 4 | architecture / swiftui / network / storage — MV pattern + SwiftUI + URLSession + Keychain |
| `fastapi` | 3 | api / services / structure — Clean Arch + DI + 패키지 구조 |
| `react-vite` | 4 | api / components / state / style — Zustand + axios 인스턴스 + CVA |
| `nextjs` | 4 | components / data / routing / style — RSC/Client 분리 + Server Actions + CVA |
| `nestjs` | 3 | api / services / structure — DTO 검증 + Module 캡슐화 + 트랜잭션 |
| `electron` | 4 | ipc / state / structure / style — IpcResult 봉투 + store-action-IPC + CVA |
| `python-cli` | 0 | (가이드라인 없음 — 프로파일 본문이 컨벤션 담당) |
| `python-lib` | 0 | (가이드라인 없음 — 프로파일 본문이 컨벤션 담당) |
| `django` | 0 | (가이드라인 없음 — 프로파일 본문이 컨벤션 담당) |
| `claude-skill` | 0 | (가이드라인 없음 — 프로파일 본문이 컨벤션 담당) |

## 경고

안 읽으면: LESSON-STYLE-001 위반 / 보안 패턴 누락 / 컨벤션 drift 발생.
시스템 프롬프트만으로는 프로파일별 세부 컨벤션을 커버하지 못합니다.

## 공통 변경 이력

이 파일을 업데이트하면 모든 `/ha-*` 스킬의 가이드라인 섹션이 동기화됩니다.
SKILL.md 6개 파일을 개별 편집하는 대신 여기서만 수정하세요.
