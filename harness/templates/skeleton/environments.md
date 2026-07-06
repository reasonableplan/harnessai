---
id: environments
name: 환경 분리
required_when: (has.http_server or has.cli_entrypoint) and (lifecycle in [mvp, ga] or availability in [standard, high])
description: dev / staging / prod 환경별 설정 차이, 시크릿 관리, CORS, 보안 헤더
---

## {{section_number}}. 환경 분리

### 환경 목록
| 환경 | 목적 | 배포 트리거 |
|------|------|------------|
| dev | 로컬 개발 | 수동 |
| staging | QA / 배포 전 검증 | `<예: main 브랜치 push>` |
| prod | 실서비스 | `<예: 태그 릴리즈 / 수동 승인>` |

### 환경별 설정 차이
| 설정 항목 | dev | staging | prod |
|----------|-----|---------|------|
| DB | `<예: SQLite / 로컬 PostgreSQL>` | `<예: 격리된 PostgreSQL>` | `<예: 운영 PostgreSQL (RDS)>` |
| 로그 레벨 | DEBUG | INFO | WARNING |
| CORS origin | `http://localhost:5173` | `<예: https://staging.example.com>` | `<예: https://example.com>` |
| 이메일 발송 | 콘솔 출력 (발송 안 함) | `<예: 테스트 계정으로만>` | 실제 발송 |
| 에러 상세 노출 | 스택 트레이스 | 코드만 | 코드만 |
| Sentry / 모니터링 | 비활성 | 활성 (별도 프로젝트) | 활성 |

### 시크릿 관리
- **저장 위치**: `<예: .env (로컬) / GitHub Secrets (CI) / AWS Secrets Manager (prod)>`
- **로테이션 주기**: `<예: 분기별 / 침해 사고 시 즉시>`
- **비상 폐기 절차**: `<예: 시크릿 교체 → 환경변수 업데이트 → 재배포>`

### CORS 정책
| 환경 | 허용 Origin |
|------|------------|
| dev | `http://localhost:5173`, `http://localhost:3000` |
| staging | `<예: https://staging.example.com>` |
| prod | `<예: https://example.com>` |

⚠️ prod CORS 에 와일드카드(`*`) 절대 금지.

### 보안 헤더 (staging / prod 필수)
| 헤더 | 값 |
|------|-----|
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Content-Security-Policy` | `<정책 — default-src 'self' 최소>` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |

> 작성 가이드:
> - dev CORS 에 prod 도메인 포함 금지
> - 환경변수 이름은 configuration 섹션과 1:1 일치
> - CI/CD 섹션이 있으면 배포 트리거를 그 섹션과 동기화
