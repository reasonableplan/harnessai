---
id: rate_limiting
name: Rate Limiting
required_when: has.http_server
description: 엔드포인트별 요청 제한, 초과 응답 형식, 클라이언트 처리 방식
---

## {{section_number}}. Rate Limiting

### 엔드포인트별 제한
| 엔드포인트 | 제한 | 윈도우 | 기준 |
|-----------|------|--------|------|
| `POST /auth/login` | `<예: 5회>` | `<예: 1분>` | IP |
| `POST /auth/register` | `<예: 3회>` | `<예: 1시간>` | IP |
| `POST /auth/refresh` | `<예: 10회>` | `<예: 1분>` | IP |
| 일반 인증 API | `<예: 100회>` | `<예: 1분>` | 사용자 |
| 파일 업로드 | `<예: 10회>` | `<예: 1시간>` | 사용자 |

### 초과 시 응답
- HTTP 상태: `429 Too Many Requests`
- 헤더: `Retry-After: <초>` / `X-RateLimit-Limit` / `X-RateLimit-Remaining`
- 본문:
```json
{
  "error": "요청 한도를 초과했습니다",
  "code": "RATE_LIMIT_001",
  "retry_after": 60
}
```

### 구현 방식
- 라이브러리: `<예: slowapi (FastAPI) / express-rate-limit (Node)>`
- 저장소: `<예: 인메모리 (단일 서버) / Redis (분산 환경 필수)>`
- 윈도우 방식: `<예: 슬라이딩 윈도우 / 고정 윈도우>`

### 클라이언트 처리
- 429 수신 시: `Retry-After` 헤더 읽어 자동 재시도 또는 `<예: "N초 후 시도해 주세요" Toast 표시>`
- 자동 retry 여부: `<예: 있음 (최대 1회, 헤더 지정 시간 후) / 없음>`

> 작성 가이드:
> - 로그인/회원가입 등 인증 엔드포인트는 반드시 포함
> - 분산 서버 환경이면 Redis 저장소 필수 (인메모리는 서버별 독립 카운트)
> - error_ux 섹션의 "RATE_LIMIT_001" 코드와 연동
