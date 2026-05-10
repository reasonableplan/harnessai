---
id: observability
name: 로깅 / 모니터링
required_when: has.production_concerns and scale.medium_or_larger
description: 로그 레벨, 메트릭, 알람, 트레이싱
---

## {{section_number}}. 로깅 / 모니터링

### 로그
**레벨 체계**:
- `DEBUG`: 개발 디버깅 전용. prod 비활성.
- `INFO`: 정상 흐름의 주요 이벤트 (로그인, 생성, 완료).
- `WARN`: 복구 가능한 문제 (재시도 성공, degraded 모드).
- `ERROR`: 요청 실패 / 예외 발생.
- `CRITICAL`: 서비스 중단 가능성 (DB 연결 실패, 시크릿 누락).

**구조화 로깅 (JSON)**:
```json
{
  "ts": "2026-04-01T09:00:00Z",
  "level": "INFO",
  "logger": "app.auth",
  "msg": "user logged in",
  "user_id": 42,
  "request_id": "abc-123"
}
```

**절대 로그에 포함 금지**:
- 비밀번호, 토큰, API 키 (CLAUDE.md §7)
- 개인정보 (전체 이메일/주소 — 필요 시 마스킹)

### 메트릭
| 이름 | 타입 | 레이블 | 용도 |
|------|:---:|--------|------|
| `http_requests_total` | counter | `method, path, status` | 요청 수 |
| `http_duration_seconds` | histogram | `method, path` | 응답 시간 |
| `<domain>_total` | counter | `<labels>` | <도메인 이벤트> |

### 알람 / SLA
| 조건 | 임계값 | 대응 |
|------|--------|------|
| 5xx rate | > 1% (5분) | 페이지 |
| p99 latency | > 2초 (5분) | 페이지 |
| DB connection fail | > 0 (즉시) | 페이지 |

### 트레이싱 (사용 시)
- 프레임워크: `<OpenTelemetry / Jaeger>`
- Propagation 헤더: `traceparent`, `tracestate`
- 샘플링: `<rate>`

### 헬스체크
- `GET /healthz` → `{status: ok, version, uptime_s}` 200
- `GET /readyz` → DB/큐 연결 확인 후 200/503

> 작성 가이드:
> - `print()` 금지. 반드시 구조화 logger 사용
> - request_id 헤더로 분산 트레이싱 시작
> - 알람은 실제로 조치 가능한 것만 (alert fatigue 방지)
