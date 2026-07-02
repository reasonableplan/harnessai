---
id: interface.http
name: HTTP API
required_when: has.http_server
description: REST API 엔드포인트, Request/Response, 공통 규칙
decision_points:
  - id: idempotency
    ask: "생성/결제 같은 변경 요청이 중복 제출되면 어떻게 되나요? (멱등키 / 중복 방지 / 허용)"
    detect: [멱등, idempoten, 중복 제출, 중복 요청, 중복 방지, 중복 생성, dedup]
    hint: "더블클릭/재시도로 중복 레코드 생기는 게 흔한 사고 — 막을지 정해야 함"
  - id: list_query
    ask: "목록 API 를 어떻게 필터/정렬/검색하나요? (쿼리 파라미터 명시)"
    detect: [정렬, 필터, 검색, sort, filter, search, order_by, 조회 조건, 쿼리 파라미터]
    hint: "페이지네이션 외에 어떤 필드로 거르고 정렬하는지 — 미정이면 코더가 추정"
---

## {{section_number}}. HTTP API

### 공통 규칙
- **응답 네이밍**: camelCase (`projectId`, `createdAt`)
- **Query params**: snake_case (`?project_id=1`)
- **날짜/시간**: ISO 8601 (`2026-04-01T09:00:00Z`)
- **페이지네이션**: `{ items: [...], total: N, page: N, limit: N }`
- **limit 상한**: 보드/백로그 500, 단순 목록 50

### 응답 래핑
```json
// 성공 — 단일
{ "data": { ... } }

// 성공 — 목록
{ "items": [...], "total": 100, "page": 1, "limit": 50 }

// 에러
{ "error": "...", "code": "...", "details": {} }
```

### 엔드포인트

#### Auth

**`POST /api/auth/register`**
```
Request:  { email: string, password: string (min 8자) }
Response 201: { id, email, createdAt }
Error 409: RESOURCE_002 (이메일 중복)
Error 422: VALIDATION_001
```

**`POST /api/auth/login`** `[public]`
```
Request:  { email, password }
Response 200: { accessToken, refreshToken, tokenType: "bearer" }
Error 401: AUTH_001
```

#### <도메인 그룹>

**`GET /api/<resource>`** `[Auth]`
```
Query: (필요시)
Response 200: items
```

> 작성 가이드:
> - 엔드포인트 표기는 **`METHOD /path`** (backtick+bold) 엄수 — `/ha-review` 역방향 contract 검증이 이 표기를 파싱
> - 각 엔드포인트: Method, Path, [Auth 여부], Request, Response, 에러 코드
> - N+1 쿼리 방지 주석 (예: eager load)
> - 전체 목록은 `persistence` 스키마와 1:1 대응
> - `ha-build` 실행 시 이 섹션을 직접 읽어 구현
