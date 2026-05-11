---
id: runbook
name: 운영 Runbook
required_when: availability == high and has.production_concerns
description: 알람 → 대응 절차 매트릭스. observability 가 "무엇을 보는가" 라면 runbook 은 "신호가 떴을 때 무엇을 하는가".
---

## {{section_number}}. 운영 Runbook

### 알람 → 대응 매트릭스

| 알람 시그널 | 심각도 | 1차 대응 | 에스컬레이션 (5분) | 에스컬레이션 (15분) |
|------------|--------|---------|-------------------|---------------------|
| `service_down` (헬스체크 실패) | P1 | 즉시 페이지 / 인스턴스 재시작 | 팀 리드 | CTO |
| `error_rate > 5%` (5분 평균) | P1 | 최근 배포 롤백 검토 | 팀 리드 | |
| `p95_latency > 2x SLO` (10분) | P2 | DB 슬로우쿼리 / 캐시 hit 율 확인 | 팀 리드 | |
| `db_connection_pool > 80%` | P2 | 연결 누수 / 트랜잭션 길이 점검 | DBA | |
| `disk_usage > 85%` | P3 | 로그 / 임시파일 정리 | 인프라 | |
| `payment_failure_spike` | P1 | PG 상태 확인 / 폴백 활성화 | 결제팀 | CTO |

P1: 즉시 페이지 (24/7) / P2: 업무 시간 페이지 / P3: 다음 영업일 처리

### 흔한 사고 시나리오 (Pre-written Runbooks)

#### 1. DB Connection Pool 고갈
- **증상**: 신규 요청 timeout, `connection pool exhausted` 로그 증가
- **즉시 조치**:
  1. `pg_stat_activity` (Postgres) 또는 동등 — 장시간 실행 쿼리 확인
  2. 의심 쿼리 `pg_terminate_backend(pid)`
  3. 풀 사이즈 임시 증설 (rollback 계획 필수)
- **근본 원인**: <트랜잭션 길이 / N+1 쿼리 / 누수>
- **재발 방지**: <ORM 쿼리 점검 / 트랜잭션 타임아웃 설정>

#### 2. 배포 직후 에러율 급증
- **증상**: 배포 후 5분 내 `error_rate > 5%`
- **즉시 조치**:
  1. 이전 버전으로 롤백 (`ci_cd` 의 롤백 절차)
  2. 사용자 영향 범위 측정 (audit_log / 분석)
  3. 핫픽스 vs 다음 배포 결정
- **post-mortem 필수**

#### 3. 외부 의존 다운 (Stripe / OAuth / SendGrid)
- **즉시 조치**: `external_deps` 의 폴백 정책 활성화
- **사용자 알림**: 상태 페이지 업데이트
- **복구 후**: 큐에 쌓인 작업 재처리

### 에스컬레이션 / 온콜 로테이션

- **로테이션**: <주간 / 격일 / 24x7>
- **연락처 우선순위**: <Slack #incidents → 전화 → SMS>
- **OOO 대체**: <백업 온콜 지정 정책>

### Post-mortem 정책

- P1 사고 발생 시 48시간 내 작성 (blameless)
- 템플릿 위치: `<docs/post-mortems/YYYY-MM-DD-<slug>.md>`
- 액션 아이템은 이슈 트래커에 등록 + due date

> 작성 가이드:
> - 모든 P1/P2 알람에 1차 대응 절차 사전 작성 — "현장에서 생각" 금지
> - 명령어 / 쿼리는 실제 실행 가능한 형태 (복붙 가능)
> - 에스컬레이션 경로는 이름이 아니라 역할 — 사람 바뀌어도 살아남음
> - `slo` 의 위반 임계가 알람 시그널 → runbook 의 입력
> - 사고 후 runbook 을 갱신 — 다음에 더 빠르게 대응
