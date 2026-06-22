---
name: ha-converge
description: |
  HarnessAI v2 — 코드↔스펙 미구현 회수 (Spec Kit /converge 흡수).
  skeleton 에 선언됐지만 소스에 없는 컴포넌트를 tasks.md 에 신규 태스크로 회수(append).
  Use when: /ha-verify 또는 /ha-review 후 배포 전, "빠진 거 없나 확인", "/ha-converge"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
---

## 역할

`/ha-review` 의 역방향 contract 검증(skeleton 에 선언했는데 미구현)은 **advisory WARN** 에
그친다. `/ha-converge` 는 같은 신호를 **actionable** 하게 만든다: 선언-미구현 컴포넌트를
`tasks.md` 에 신규 `대기` 태스크로 **회수(append)** 해 빌드 루프로 되돌린다.

**입력**: 빌드된 코드(built/verified/reviewed) + skeleton.md + tasks.md
**출력**: tasks.md 에 회수된 신규 태스크 (멱등 — 중복 추가 안 함)
**다음**: 회수된 태스크가 있으면 `/ha-build` (reviewed 상태면 building 으로 회귀)

> **상태 전이 없음** — 이 스킬은 태스크만 append 한다. 회수된 `대기` 태스크의 실제 빌드는
> `/ha-build` 가 담당하며, reviewed 이후라면 `/ha-build` 가 building 으로 회귀시킨다(iteration).

## 실행 순서

### 1. 미구현 컴포넌트 보고 (read-only)

```bash
python ~/.claude/skills/ha-converge/run.py prepare
```

JSON 출력:
```json
{
  "findings": [
    {"kind": "missing_endpoint", "identifier": "GET /api/orders/{id}", "detail": "/api/orders"}
  ],
  "uncovered": ["GET /api/orders/{id}"],
  "already_covered": [],
  "tasks_path": "<...>/tasks.md"
}
```

- `findings` — skeleton `interface.http` 에 선언됐지만 소스 어디에도 정적 prefix 가 없는 엔드포인트.
- `uncovered` — 아직 태스크로 존재하지 않는 것 (회수 대상).
- `already_covered` — 이미 tasks.md 에 태스크가 있는 것 (멱등 — 회수 안 함).

**판정 가드 (오탐 cross-check)**: `uncovered` 가 의도적 `skipped`/Phase 2 항목인지 먼저 확인.
의도적 보류라면 회수하지 말고 skeleton 또는 tasks.md 에 그 사유를 명시하세요. 실제 누락만 회수.

### 2. 회수 (tasks.md append)

```bash
python ~/.claude/skills/ha-converge/run.py commit
```

- `uncovered` 엔드포인트마다 신규 `대기` 태스크 행을 Phase 테이블 끝에 추가.
- 태스크 ID 는 기존 최대 T-NNN 다음부터 순차 할당.
- **멱등**: identifier 가 이미 tasks.md 에 있으면 건너뜀 — 두 번 돌려도 중복 없음.
- tasks.md 가 없으면 (`/ha-plan` 미실행) exit 3.

### 3. 다음 안내

회수됨:
```
✅ /ha-converge — 2개 미구현 컴포넌트를 태스크로 회수했습니다.
  + T-015: GET /api/orders/{id}
  + T-016: DELETE /api/users
다음: /ha-build T-015 (reviewed 상태면 building 으로 회귀)
```

없음:
```
✅ /ha-converge — 회수할 미구현 컴포넌트 없음 (또는 이미 태스크화됨).
```

## 가드레일

- **read-only 우선**: 반드시 `prepare` 로 먼저 보고 → 의도적 보류(skipped/Phase 2) 걸러낸 뒤 `commit`.
- v1 범위는 **HTTP 엔드포인트**(skeleton `interface.http`)만. 선언 파일시스템 경로 누락은
  `harness integrity` 게이트가 담당(`/ha-verify` 1.5 단계).
- 회수 태스크의 에이전트는 `backend_coder` 고정 — 다른 컴포넌트 유형은 수동 조정.
- 상태(built/verified/reviewed)가 아니면 exit 2 — 코드가 있어야 대조가 의미 있음.
