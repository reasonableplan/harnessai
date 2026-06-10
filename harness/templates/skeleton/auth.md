---
id: auth
name: 인증 / 권한
required_when: has.users
description: 인증 방식, 토큰/세션 수명, 보호 리소스, 권한 모델
---

## {{section_number}}. 인증 / 권한

### 인증 방식
- 방식: `<JWT / 세션 쿠키 / OAuth 2.0 / API Key / mTLS / ...>`
- 선택 근거: `<이 방식을 고른 이유>`
- OAuth 선택 시 추가 확정: callback URL / `state` + PKCE 사용 여부 / 기존 이메일 계정과의 연결 정책 (자동 연결 금지 권장 — 계정 탈취 벡터)

### 자격 증명 수명
| 항목 | 수명 | 저장 위치 |
|------|------|----------|
| Access token | `<예: 15분>` | **인메모리** (localStorage/sessionStorage/AsyncStorage 금지 — LESSON-027) |
| Refresh token | `<예: 7일>` | httpOnly cookie (웹) / flutter_secure_storage·SecureStore·Keychain·Keystore (모바일) |

### JWT Payload 구조
```json
{
  "sub": "<user_id>",
  "type": "access",
  "ver": "<token_version>",
  "exp": "<unix_timestamp>"
}
```
- `type` claim 필수 — "access" / "refresh" 구분 (LESSON-022)
- `ver` claim 필수 — User.token_version 과 일치 검증, logout 시 서버에서 증가 (LESSON-023)

### 인증 흐름
핵심 시나리오별 시퀀스:

```
로그인:        <클라이언트 → 서버 → access(인메모리) + refresh(httpOnly cookie) 발급>
토큰 갱신:      <401 → /auth/refresh (쿠키 전용, body.refresh_token 수락 금지) → 재시도>
로그아웃:      <서버에서 token_version 증가 → 기존 토큰 전부 무효화 (no-op 금지 LESSON-023)>
비밀번호 재설정: <있을 시 절차>
```

### 프론트엔드 세션 관리

#### Silent Refresh 전략
- **방식**: `<예: 401 응답 시 자동 갱신 / 만료 N초 전 선제 갱신>`
- **구현 위치**: `<예: axios interceptor / fetch wrapper>`
- **동시 요청 처리**: `<예: refresh 중 다른 요청은 대기 (queue) / 실패 처리>`

#### 페이지 새로고침 후 복원
- **동작**: `<예: refresh token(쿠키)으로 자동 로그인 복원 / 로그아웃 유지>`
- **복원 중 UX**: `<예: 로딩 스피너 표시 후 원래 페이지 / 로그인 페이지 redirect>`

#### 세션 만료 UX
- **만료 감지 시점**: `<예: API 401 수신 / 타이머 기반 사전 감지>`
- **UX 동작**: `<예: "세션이 만료됐습니다" Modal → 로그인 후 원래 페이지 복원 / 즉시 redirect>`
- **작업 중 데이터 보존**: `<예: localStorage에 폼 임시 저장 / 버림>`

#### 탭 간 동기화
- **로그아웃 전파**: `<예: BroadcastChannel / localStorage event → 다른 탭 자동 로그아웃 / 미지원>`
- **토큰 갱신 전파**: `<예: 한 탭에서 갱신 시 다른 탭에도 반영 / 미지원>`

### 보호 라우트 / 리소스
- 인증 필요: `<리스트>`
- 인증 불필요 (public): `<리스트>`
- 익명 접근 가능하지만 인증하면 다르게 응답: `<리스트>`

### 권한 모델
| 역할 | 권한 |
|------|------|
| `user` | 자신의 리소스 CRUD |
| `admin` | 모든 리소스 + 관리 기능 |

**권한 검증 지점**: `<어디서 권한을 확인하는가 — 미들웨어 / 서비스 레이어 / 쿼리 필터>`

### 시크릿 관리
- JWT 서명 키: `<환경변수 이름>` (configuration 섹션 참조)
- 로테이션 정책: `<예: 분기별>`
- 비상 폐기 절차: `<키 교체 시 기존 토큰 전부 무효화>`

### 보안 원칙 체크리스트
- [ ] 비밀번호 해시 (bcrypt / argon2, cost/memory 적절)
- [ ] 타이밍 공격 방지 (`hmac.compare_digest` 또는 등가)
- [ ] CSRF 방어 (쿠키 인증 시)
- [ ] Rate limit (무차별 대입 방어)

> 작성 가이드:
> - 인증 프레임워크 구체 사용법은 프로파일 본문 참조 (예: FastAPI의 `Depends(get_current_user)`)
> - 비밀값 이름은 configuration 섹션의 환경변수 목록과 1:1 일치
> - OAuth 공급자 목록은 integrations 섹션에 기록
> - 모든 시크릿은 절대 커밋 금지 — `.env` + `.env.example` 분리
