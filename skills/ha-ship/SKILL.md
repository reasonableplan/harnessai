---
name: ha-ship
description: |
  HarnessAI — 파이프라인 라스트마일. reviewed 상태를 shipped 로 마킹.
  배포/PR 자체는 외부 도구 (gstack /ship 등) 가 수행 — 이 스킬은 상태 전이만.
  Use when: /ha-review APPROVE 후 배포/PR 완료 시, "배포 끝났어", "/ha-ship"
allowed-tools:
  - Bash
  - Read
---

## 역할

상태머신의 마지막 전이 `reviewed → shipped` 를 기록한다. 이 전이가 박히면
프로젝트는 릴리스된 아티팩트로 간주되며 `/ha-redesign` 도 shipped 를
immutable 로 취급한다.

**입력**: reviewed 상태의 프로젝트 + 완료된 배포/PR
**출력**: harness-plan.md 의 `current_step: shipped`
**다음**: (파이프라인 종료) 다음 사이클은 새 결정과 함께 /ha-redesign 또는 /ha-init

## 실행 순서

### 1. 배포/PR 완료 확인 (선행 — 외부 도구)

이 스킬은 배포를 하지 않는다. 먼저 다음 중 하나가 완료됐는지 확인:
- gstack `/ship` (VERSION bump + CHANGELOG + PR) 또는 `/land-and-deploy`
- 또는 수동 push/배포

배포가 검증되지 않았으면 **마킹하지 말 것** — shipped 는 "릴리스된 아티팩트" 선언이다.

### 2. 상태 마킹

```bash
python ~/.claude/skills/ha-ship/run.py mark
```

run.py 가:
- `current_step == "reviewed"` 검증 (아니면 차단 — /ha-review 먼저)
- "reviewed" → "shipped" 전이 + `completed_steps += ["ha-ship"]`
- harness-plan.md 저장

### 3. 출력

```
✅ shipped — 파이프라인 종료.
이후 변경은 /ha-redesign (결정 변경) 또는 새 사이클로.
```

## 가드레일

- **reviewed 상태에서만** — run.py 의 assert_state 가 차단
- **배포 검증 전 마킹 금지** — shipped 는 외부 세계에 나간 상태의 선언
- shipped 이후 코드 변경이 필요하면 상태를 되돌리지 말고 새 결정(/ha-redesign)으로
