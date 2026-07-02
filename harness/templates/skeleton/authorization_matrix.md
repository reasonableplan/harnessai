---
id: authorization_matrix
name: 권한 행렬 (Authorization Matrix)
required_when: has.users
description: 인증(auth)과 분리된 "역할 × 리소스 × 액션" 행렬. 누가 무엇을 할 수 있는지 명시. 후반 retrofit 비용 가장 큰 영역. 민감 데이터 (pii / payment) 다룰 때 critical.
---

## {{section_number}}. 권한 행렬 (Authorization Matrix)

### 역할 목록

| 역할 | 한 줄 설명 | 어떻게 부여되는가 |
|------|------------|------------------|
| `admin` | 시스템 전체 관리자 | <초기 seed / 전용 콘솔> |
| `user` | 인증된 일반 사용자 | <회원가입 + 이메일 인증> |
| `guest` | 비인증 (read-only) | `<기본값>` |
| `<custom>` | `<설명>` | <부여 절차> |

### 권한 매트릭스

| 리소스 | 액션 | guest | user | admin | 비고 |
|--------|------|:-----:|:----:|:-----:|------|
| `<resource>` | `read` | ✅/❌ | ✅/❌ | ✅ | <조건 — 자기 것만 / 전체> |
| `<resource>` | `create` | ❌ | ✅/❌ | ✅ | |
| `<resource>` | `update` | ❌ | ✅ (own) | ✅ | row-level 검증 필수 |
| `<resource>` | `delete` | ❌ | ✅ (own) / soft | ✅ (hard) | |

> "✅ (own)" 는 row-level 검증 — `resource.owner_id == current_user.id`. 컨트롤러 단에서 무조건 강제.

### 권한 검증 위치 (방어 계층)

| 계층 | 검증 내용 | 이유 |
|------|----------|------|
| API Gateway / 미들웨어 | 인증 토큰 유효성 + 기본 역할 | 빠른 실패 |
| 서비스 / 컨트롤러 | 액션 + row-level 소유권 | 비즈니스 룰 |
| DB constraint | RLS (Row-Level Security) — 옵션 | 마지막 방어선 |

3계층 모두 통과해야 — 단일 계층 의존 금지 (defense in depth).

### 권한 변경 절차

- **승격 / 강등**: `<누가 / 어떻게 / 감사 로그 남기는가>`
- **임시 권한**: `<expires_at 컬럼 또는 별도 테이블>`
- **권한 회수**: `<즉시 vs 다음 로그인 — 토큰 만료 정책과 결합>`

> 작성 가이드:
> - 행렬은 **모든 (역할 × 리소스 × 액션) 조합** 명시 — 빈 칸 금지 (암묵적 허용 = 보안 사고)
> - row-level 권한은 컨트롤러에서 무조건 강제. ORM 쿼리에 `WHERE owner_id = ?` 자동 주입 권장
> - 신규 역할 추가 시 모든 매트릭스 업데이트 필수 — `audit_log`, `threat_model` 도 같이 갱신
> - 6축 `data_sensitivity in [pii, payment]` 면 권한 변경 자체가 audit_log 기록 대상
