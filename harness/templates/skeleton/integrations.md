---
id: integrations
name: 외부 통합
required_when: has.external_deps
description: 3rd party API, OAuth 공급자, 웹훅
---

## {{section_number}}. 외부 통합

### 3rd Party API
| 서비스 | 목적 | 인증 방식 | 요금제 |
|--------|------|----------|--------|
| `<예: Stripe>` | 결제 처리 | API key (env: `STRIPE_SECRET_KEY`) | pay-as-you-go |
| `<예: SendGrid>` | 트랜잭션 이메일 | API key | free tier |

### OAuth 공급자
| 공급자 | 용도 | Client ID env | Callback URL |
|--------|------|---------------|--------------|
| `<예: GitHub>` | 소셜 로그인 | `GITHUB_CLIENT_ID` | `/auth/github/callback` |

### 웹훅
**수신**:
| 엔드포인트 | 공급자 | 서명 검증 |
|-----------|--------|----------|
| `POST /webhooks/<provider>` | `<provider>` | HMAC-SHA256 (`WEBHOOK_SECRET`) |

**발신**:
| 트리거 | 대상 | 페이로드 |
|--------|------|---------|
| `<예: 결제 완료>` | `<slack/discord url>` | JSON |

### 실패 대응
- **Retry 전략**: <예: exponential backoff, max 3회>
- **Circuit breaker**: `<임계값>`
- **Fallback**: <예: 이메일 실패 시 큐에 쌓고 나중에 재시도>

### Rate Limit
- <서비스별 limit, 우리 쪽 처리 방식>

> 작성 가이드:
> - API key 이름은 `configuration` 섹션에 실제 env 목록 동기화.
> - 웹훅 서명 검증은 반드시. 미검증 수신 금지.
> - OAuth callback URL은 환경별(dev/prod) 분리 관리.
