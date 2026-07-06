---
name: ha-run
description: |
  HarnessAI — 원커맨드 자동 드라이버. 파이프라인 전체(init → design → plan →
  build → verify → smoke → review → ship 확인)를 상태기계 기준으로 자동 운전한다.
  HITL 지점(인터뷰 · smoke FAIL 판단 · 배포 확인 · 게이트 BLOCK)에서만 멈춘다.
  Use when: "알아서 끝까지 진행해줘", "다음 뭐 해야 해", "이어서 계속", "/ha-run"
---

## 역할

파이프라인 운전자. 지금까지 사용자가 스킬 10개를 순서대로 직접 호출하던 것을
이 스킬 하나가 대신한다 — 각 단계 스킬을 상태기계 순서대로 호출하고,
**사람 판단이 필요한 지점에서만** 정지해 평문으로 묻는다.

**입력**: 아무 상태의 프로젝트 (플랜 없음 포함)
**출력**: 다음 HITL 지점 또는 shipped 까지 진행된 파이프라인
**원칙**: 게이트를 우회하지 않는다. 이 스킬은 순서만 자동화하고, 판정은 전부 기존 게이트가 한다.

## 실행 순서 (루프)

### 1. 다음 행동 판독

```bash
python ~/.claude/skills/ha-run/run.py next
```

JSON 출력: `action` / `mode`(auto|hitl) / `skill` / `args` / `reason` / `current_step`

### 2. action 분기

**`done`** → 종료. "✅ 파이프라인 완료 (shipped)" 보고 후 루프 탈출.

**`mode: "auto"`** → `skill` 을 Skill 툴로 즉시 호출 (`args` 전달).
호출 전 진행 상황을 한 줄로 보고:
```
▶ [현재상태 → 다음단계] /ha-verify — toolchain 검증
```

**`mode: "hitl"`** → 사용자 개입 지점. action 별:
- `init` / `design` → 해당 스킬을 Skill 툴로 호출 — **스킬 자체가 인터뷰를 진행**하므로
  드라이버는 넘겨주기만 한다. 인터뷰 완료 후 루프 복귀.
- `review` (smoke FAIL) → AskUserQuestion 으로 선택지 제시:
  "① smoke 실패 원인 수정 (원인 태스크 rebuild)" / "② advisory 로 간주하고 리뷰 진행".
  ① 선택 시 구체 4단계:
    1. `harness analyze-failure <출력파일> --tasks docs/tasks.md` → 실패 T-ID 식별
    2. `ha-verify record --passed false --rework-tasks <T-ID>` → verify_history 기록 + tasks.md needs_rebuild 전이
    3. plan.pipeline → building 자동 회귀 (pipeline_advisor 가 build --resume 반환)
    4. `/ha-build --resume` → needs_rebuild 태스크 자동 선택 후 재구현
    fallback: smoke output 에서 T-ID 매칭 못 하면 entrypoint 태스크 또는 사용자 선택
- `ship_confirm` → AskUserQuestion: "배포/PR 을 완료했나요?" — 완료 시에만 `/ha-ship` 호출.
  미완료면 배포 방법 안내 후 정지 (shipped 는 릴리스 선언 — 선마킹 금지).

### 3. 루프 복귀

호출한 스킬이 정상 종료하면 1 로 돌아간다. 상태는 각 스킬이 전이시키므로
드라이버는 plan 을 직접 수정하지 않는다.

## 정지 규칙 (가드레일)

- **게이트 BLOCK**: 하위 스킬이 exit≠0 + 게이트 메시지(skeleton drift 3분기,
  frozen gate, 루프 가드 등)를 내면 — **우회 플래그를 자동으로 붙이지 말 것**.
  게이트 메시지의 선택지를 사용자에게 평문으로 제시하고 정지.
- **무전이 반복**: 같은 `action` 이 3회 연속 나왔는데 `current_step` 이 그대로면
  정지하고 상황 보고 (드라이버 무한루프 방지 — 게이트 루프 가드와 별개의 안전망).
- **세션당 최대 30 루프**: 초과 시 진행 요약 + 남은 단계 보고 후 정지.
  (무전이 3회 가드가 무한루프를 잡으므로 이 상한은 비용 안전망 — Fable 급 장기 자율 런 기준.)
- **rework 회귀는 정상 흐름**: verify/review FAIL 로 building 회귀 시 그대로
  build 부터 재진행 (동일 T-ID 3회 FAIL 은 ha-verify 게이트가 알아서 BLOCK).

## 진행 보고 형식

각 루프마다 사용자에게 한 줄씩 (전문 용어 최소화):

```
▶ 설계 확정 → 태스크 분해 (/ha-plan)
▶ T-003 구현 중 (/ha-build --resume)
⏸ 확인 필요: 앱 기동 검증이 실패했습니다 — 수정할까요, 그대로 리뷰로 갈까요?
✅ 파이프라인 완료 — 8단계 · 태스크 12개 · rework 1회
```

## 가드레일

- 이 스킬은 **판정하지 않는다** — 게이트/인터뷰/승인 로직은 전부 기존 스킬 소유.
- plan/tasks/skeleton 파일을 직접 편집하지 않는다 (전이는 하위 스킬 경유만).
- 사용자가 중간에 개입하면 (수동 스킬 호출 등) 다음 루프의 `next` 가 상태를
  다시 읽으므로 그대로 이어진다 — 상태 캐싱 금지.
