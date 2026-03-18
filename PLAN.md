# 실리콘밸리 수준 완성 로드맵

> 목표: 실동작 기반 위에 프로덕션 품질 코드 완성

---

## 현재 상태

- ✅ Python/FastAPI 백엔드 구현 완료
- ✅ 106개 테스트 통과 (0 lint errors)
- ✅ 보안 강화 완료 (CRITICAL 3 + HIGH 5 + MEDIUM 5 + LOW 2)
- ✅ personal-jira repo 생성 완료
- ✅ WS 메시지 기반 인증, Board-first 원칙 전면 적용
- ✅ Phase 1 실동작 검증 완료 (2026-03-16)
- ✅ Director 대화형 워크플로우 구현 (2026-03-17)
- ✅ 대시보드 UI 대폭 개선 (2026-03-17)
- ✅ 타일맵 렌더링 수정 (2026-03-17)

---

## Phase 1 — 실동작 검증 ✅ (2026-03-16 완료)

| # | 작업 | 상태 |
|---|------|------|
| 1.1 | PR #28 (누락 테스트 32개) 머지 | ✅ |
| 1.2 | `.env` → personal-jira 연결 | ✅ |
| 1.3 | Docker PostgreSQL + Alembic 마이그레이션 | ✅ |
| 1.4 | `uv run python -m src.main` 기동 확인 | ✅ |
| 1.5 | `POST /api/command` → Director → GitHub Issues 12개 생성 | ✅ |
| 1.6 | 런타임 버그 수정 (포트 충돌) | ✅ |

---

## Phase 1.5 — Director 대화형 워크플로우 ✅ (2026-03-17 완료)

| # | 작업 | 상태 |
|---|------|------|
| 1.5.1 | EpicPlan/ProjectContext/TaskDraft 타입 설계 | ✅ |
| 1.5.2 | Stage 상태 머신 (GATHERING→STRUCTURING→CONFIRMING→COMMITTED) | ✅ |
| 1.5.3 | Stage별 시스템 프롬프트 (gathering, structuring, revising, confirming) | ✅ |
| 1.5.4 | WS 양방향 통신 (chat, plan.approve/revise/commit) | ✅ |
| 1.5.5 | agent-pause/resume, system-pause/resume 실제 동작 | ✅ |
| 1.5.6 | EventMapper — director.message/plan/committed 이벤트 | ✅ |
| 1.5.7 | 실동작 검증 — 3턴 대화 → 18개 태스크 분해 성공 | ✅ |
| 1.5.8 | 15개 테스트 추가 (Stage 전환, 커밋, 역행, 상태 조회 등) | ✅ |

---

## Phase 1.6 — 대시보드 UI 개선 ✅ (2026-03-17 완료)

| # | 작업 | 상태 |
|---|------|------|
| 1.6.1 | ChatPanel — Director 대화 패널 (메시지 표시, Plan 상태/액션 버튼) | ✅ |
| 1.6.2 | STOP/START 토글 — 헤더에 작은 버튼, 실제 pause/resume | ✅ |
| 1.6.3 | LOG 버튼 — 에이전트 전체 로그 표시 토글 | ✅ |
| 1.6.4 | Settings에 CHARACTER 탭 통합 (독립 모달 제거) | ✅ |
| 1.6.5 | STOP ALL/START ALL — SystemStatusBar에서 전체 에이전트 제어 | ✅ |
| 1.6.6 | 타일맵: 타일셋 floor/wall + 프로시저럴 가구 합성 | ✅ |
| 1.6.7 | 바닥/벽 타일 좌표 수정 (warm brown wood 통일) | ✅ |

---

## Phase 2 — CI / 관찰성 (다음 목표)

| # | 작업 | 상태 |
|---|------|------|
| 2.1 | GitHub Actions에 Docker PostgreSQL + E2E 파이프라인 테스트 추가 | ✅ |
| 2.2 | `_is_retryable` — 문자열 매칭 → httpx 타입 기반 수정 (M2) | ✅ |
| 2.3 | 헬스체크 엔드포인트 `GET /health` (DB + GitHub 연결 상태) | ✅ |
| 2.4 | 구조화 로깅 개선 — 요청 request_id 전파, 에러 컨텍스트 강화 | ✅ |

---

## Phase 3 — 코드 아키텍처 정리

| # | 작업 | 상태 |
|---|------|------|
| 3.1 | 타일맵 좌표 정밀 매핑 (가구 타일셋 활용) | ⬜ |
| 3.2 | API response model 전체 Pydantic 화 (dict 반환 혼재 제거) | ⬜ |
| 3.3 | AgentError 서브클래스 기반 에러 분류 정리 | ⬜ |
| 3.4 | CSP unsafe-inline 제거 (nonce 기반, M3) | ⬜ |
| 3.5 | `command.py` REST → WS 전용으로 정리 | ⬜ |

---

## Phase 4 — 프로덕션 완성

| # | 작업 | 상태 |
|---|------|------|
| 4.1 | Rate limiting / backpressure — 에이전트 동시 태스크 제한 | ⬜ |
| 4.2 | Dockerfile 최적화 (multi-stage, non-root user) | ⬜ |
| 4.3 | Kubernetes-ready 구조 (readiness/liveness probe) | ⬜ |
| 4.4 | 성능 프로파일링 — DB N+1 쿼리, 이벤트 루프 블로킹 탐지 | ⬜ |

---

## 건너뛰기로 결정

| 항목 | 이유 |
|------|------|
| M3 CSP unsafe-inline (Phase 3까지 보류) | Vite nonce 설정 복잡, 내부 대시보드 |
| M6 raw PostgreSQL JSON 쿼리 | 스키마 변경 필요, 기능 문제 없음 |
| 캐릭터 배정 UI (Phase 4에서 제거) | Settings 모달 CHARACTER 탭으로 해결됨 |
