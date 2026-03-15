# 실리콘밸리 수준 완성 로드맵

> 목표: 실동작 기반 위에 프로덕션 품질 코드 완성

---

## 현재 상태

- ✅ Python/FastAPI 백엔드 구현 완료
- ✅ 91개 테스트 통과 (0 lint errors)
- ✅ 보안 강화 완료 (CRITICAL 3 + HIGH 5 + MEDIUM 5 + LOW 2)
- ✅ personal-jira repo 생성 완료
- ✅ WS 메시지 기반 인증, Board-first 원칙 전면 적용

---

## Phase 1 — 실동작 검증 (목표: 오늘)

| # | 작업 | 상태 |
|---|------|------|
| 1.1 | PR #28 (누락 테스트 32개) 머지 | ⬜ |
| 1.2 | `.env` → personal-jira 연결 (`GITHUB_REPO=personal-jira`, `GITHUB_PROJECT_NUMBER`) | ⬜ |
| 1.3 | `docker compose up -d` + `uv run alembic upgrade head` | ⬜ |
| 1.4 | `uv run python -m src.main` 기동 확인 | ⬜ |
| 1.5 | `POST /api/command` → Director → GitHub Issues → Board 확인 | ⬜ |
| 1.6 | 발견 런타임 버그 수정 | ⬜ |

---

## Phase 2 — CI / 관찰성 (목표: 이번 주)

| # | 작업 | 상태 |
|---|------|------|
| 2.1 | GitHub Actions에 Docker PostgreSQL + E2E 파이프라인 테스트 추가 | ⬜ |
| 2.2 | `_is_retryable` — 문자열 매칭 → httpx 타입 기반 수정 (M2) | ⬜ |
| 2.3 | 헬스체크 엔드포인트 `GET /health` (DB + GitHub 연결 상태) | ⬜ |
| 2.4 | 구조화 로깅 개선 — 요청 trace_id 전파, 에러 컨텍스트 강화 | ⬜ |

---

## Phase 3 — 코드 아키텍처 정리 (목표: 다음 주)

| # | 작업 | 상태 |
|---|------|------|
| 3.1 | Phase 8 타일맵 JSON 렌더링 — draw-* 프로시저럴 코드 전면 교체 | ⬜ |
| 3.2 | API response model 전체 Pydantic 화 (dict 반환 혼재 제거) | ⬜ |
| 3.3 | AgentError 서브클래스 기반 에러 분류 정리 | ⬜ |
| 3.4 | CSP unsafe-inline 제거 (nonce 기반, M3) | ⬜ |

---

## Phase 4 — 프로덕션 완성 (2주 후)

| # | 작업 | 상태 |
|---|------|------|
| 4.1 | Rate limiting / backpressure — 에이전트 동시 태스크 제한 | ⬜ |
| 4.2 | Dockerfile 최적화 (multi-stage, non-root user) | ⬜ |
| 4.3 | Kubernetes-ready 구조 (readiness/liveness probe) | ⬜ |
| 4.4 | 성능 프로파일링 — DB N+1 쿼리, 이벤트 루프 블로킹 탐지 | ⬜ |
| 4.5 | 캐릭터 배정 UI — 사용자가 도메인별 캐릭터 선택 | ⬜ |

---

## 건너뛰기로 결정

| 항목 | 이유 |
|------|------|
| M3 CSP unsafe-inline (Phase 3까지 보류) | Vite nonce 설정 복잡, 내부 대시보드 |
| M6 raw PostgreSQL JSON 쿼리 | 스키마 변경 필요, 기능 문제 없음 |
