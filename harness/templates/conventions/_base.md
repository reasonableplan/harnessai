# 기본 프로젝트 컨벤션 (언어 무관)

> 이 파일은 HarnessAI 가 `/ha-init` 실행 시 사용자 스타일 인터뷰 답변과 결합해
> 프로젝트의 `docs/conventions.md` 를 생성하는 베이스 템플릿이다.
> 프로파일별 구체 컨벤션은 `../guidelines/<profile>/*.md` 참조.

---

## 핵심 철학

1. **테스트 먼저, 코드 나중 (TDD)** — 새 함수 작성 전 실패하는 테스트 → 구현 → 통과
2. **한 번에 완벽하게** — 인터페이스 변경 시 타입/구현/mock/테스트/호출처 전부 한 번에
3. **기존 패턴을 복붙해서 이름만 바꾸는 구조** — 새 도메인 추가가 기계적이어야 함
4. **추상화는 중복 3번 이후에만** — BaseService/DI 컨테이너/Provider 같은 선제적 추상화 금지
5. **과도한 쪼개기 금지** — 18줄 컴포넌트, 한 함수 안에서 흐름 보이는 로직은 그대로
6. **레이어 경계 엄수** — None 을 아래 레이어로 흘리지 마라
7. **명시적 > 암묵적** — 암묵적 관계, 암묵적 전환, 암묵적 기본값 최소화

---

## 완료 판단 체크리스트 (모든 PR)

- [ ] 전체 테스트 pass (unit + integration)
- [ ] 린트 0 errors
- [ ] 타입 체크 0 errors
- [ ] 새 함수에 테스트 작성
- [ ] 인터페이스 변경 시 호출처 전부 업데이트
- [ ] 파일 쓰기/JSON 로드에 예외 처리
- [ ] 환경변수 변경 시 `.env.example` 동기화

---

## 에러 처리 원칙

- `except Exception: pass` 절대 금지 — 최소 `logger.error(...)`
- 파일/네트워크/JSON 처리는 각 예외 타입 구체 catch + re-raise 또는 fallback
- HTTP 500 응답에 스택트레이스/DATABASE_URL/SECRET_KEY 절대 미포함

---

## 주석 / 사용자 문구

- 주석은 코드가 보여주지 못하는 제약/이유만 — 코드를 자연어로 번역하는 주석(`// 사용자를 가져온다`) 금지
- 사용자 노출 문구는 해당 프로젝트의 도메인 용어로 구체적으로 — 마케팅 형용사 나열("간편하고 효율적인...") 금지

---

## 보안 가드

- CLI/subprocess 인자에 시크릿 전달 금지 → 환경변수만
- 사용자 입력으로 파일명 생성 시 path traversal 방어 (`..`, `/`, `\`, null byte 제거)
- 에이전트/사용자 입력을 프롬프트에 연결 시 XML 딜리미터 (`<task>...</task>`) 감싸기

---

## 환경/설정 동기화

- 환경변수 추가/변경 시 → `.env.example` 동시 반영 (빈 값 + 한 줄 설명)
- 정규식에서 `\n` 은 **`\r?\n`** 로 (CRLF 호환)

---

## 테스트 전략 (사용자 선택)

`/ha-init` 인터뷰에서 선택된 전략이 여기 채워짐. 기본값:

- **unit**: 순수 함수/비즈니스 로직 — 빠른 피드백
- **integration**: 라우터/DB 레이어 — 실제 DB 히트 (mock-only 금지)
- **e2e**: 최소한만 — critical user flow 1-2개

---

## 상태 관리 전략 (frontend 프로파일일 때, 사용자 선택)

`/ha-init` 인터뷰에서 선택된 전략이 여기 채워짐. 옵션:

- **Zustand only** (v1 personal-jira 스타일) — store action 이 API 직접 호출, TanStack Query 없음
- **Zustand + TanStack Query 하이브리드** — server state 는 TanStack Query, UI state 는 Zustand
- **Redux Toolkit** — 대규모 팀
- **Context API** — 소규모
