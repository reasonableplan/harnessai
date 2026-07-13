# 수용검증 계층 설계 — /ha-accept (GWT → 실행 가능 시나리오) (v0.21.0)

> 2026-07-13. 조사 근거: SDD 수렴(arXiv 2602.00180, Spec Kit/Kiro), Kiro EARS 표기법
> (수용 기준은 검증 가능해야 하며 다중 해석 허용 기준은 결함), ATDD-with-AI,
> 선언적 러너 landscape (Tavern/Hurl/StepCI), AI-Gherkin 안티패턴(automationpanda).
>
> 배경: 검증 사다리의 마지막 빈 칸. test/lint/type(ha-verify) → 기동(ha-smoke 계층1)
> → 선언 GET 타격(계층2) 까지 있고, **"요구사항대로 동작하는가"** 는 없다.
> ha-smoke SKILL.md 가 이미 변경계 메서드 검증을 "시나리오 스모크의 몫"으로 유보해
> 자리를 비워뒀다 (ha-smoke/SKILL.md §2.5).

## 0. 이미 존재하는 절반 (재사용)

| 자산 | 위치 | 역할 |
|---|---|---|
| 기능별 GWT 수용 기준 (사용자 확정, HUMAN-LOCKED) | skeleton `requirements` 섹션 — fragment 가 "이 기준이 곧 QA/스모크의 체크리스트" 명시 | 시나리오의 **출처** |
| ha-design Step D 인터뷰 | skills/ha-design/SKILL.md §2.7 — 기능 확정 직후 GWT 2~3개 AI 초안 → 사용자 확인/수정 | 출처의 **품질 보장** (Then 은 "화면에 보이는 것"까지) |
| 기동/정리 인프라 | skills/ha-smoke/run.py — `_kill_tree` / readiness 폴링 / `_probe_url` | 러너의 **부팅 계층** |
| verify_history | plan_manager `record_verify(step, passed, summary)` | 결과 **기록** (step=`accept`) |
| advisor 통합 패턴 | pipeline_advisor `_smoke_state()` — verify_history 에서 마지막 passing verify 이후 레코드만 집계 | **파이프라인 배치** 패턴 |

빠진 것 = GWT 산문 → 실행 가능 시나리오 파일 → 결정론 러너 → 기록 의 연결.

## 1. 아키텍처 결정

### D1. 러너 = stdlib 미니 러너 직접 구축 (기성품 채택 안 함)

- Tavern: pytest 전용 + HarnessAI backend 에 의존성 추가. Hurl: 외부 Rust 바이너리
  (Windows 설치 부담). StepCI: node 의존.
- 세 도구 모두 verify_history/advisor 통합 래핑이 어차피 필요 — 래퍼 비용은 동일한데
  의존성만 늘어남. 필요 기능(HTTP 스텝 + 캡처 + 단언, CLI 스텝)은 유계(bounded).
- ha-smoke 가 이미 urllib 만으로 동급 작업을 함 (스킬 run.py 는 stdlib + yaml 원칙).
- **단, 스키마는 StepCI/Tavern 의미론(steps/expect/capture)에 맞춰** 향후 기성품
  이식 여지를 남긴다.

### D2. 파생(derive)은 LLM, 실행은 결정론 — ha-plan 패턴 복제

GWT 산문("When 사용자가 할일을 추가하면...")→HTTP 스텝 번역은 판단 작업이라 LLM 몫.
ha-plan 과 동일 구조: **부모 LLM 이 acceptance.yaml 작성 → run.py validate 가 게이트
→ run.py run 이 결정론 실행**. 파생은 1회성이고 산출물(acceptance.yaml)은 리뷰 가능한
버전 관리 대상 아티팩트.

### D3. Kiro EARS 차용 — 도출 불가 GWT 는 침묵 skip 금지

다중 해석되거나 HTTP/CLI 로 표현 불가한 GWT(예: 순수 시각 확인)는 acceptance.yaml 의
`underivable:` 목록에 사유와 함께 **명시 기록** — validate 가 개수를 advisory 보고.
"조용히 빠진 수용 기준" = 가장 위험한 형태의 커버리지 구멍.

### D4. advisory 게이트 (ha-smoke 와 동일 시맨틱)

run FAIL 이어도 상태 전이 없음. verify_history step=`accept` 기록. advisor 가
FAIL 시 HITL (수정 재검증 vs 진행 — 사용자 선택). validate 만 BLOCK 성격
(스키마 위반 / skeleton 미선언 엔드포인트 참조 = 산출물 결함이므로).

### D5. UI(브라우저) 시나리오는 v1 제외

HTTP/CLI 레벨만. 브라우저 검증은 gstack /qa·/browse 존재 — 중복 투자 금지.
Then 의 "화면에 보이는 것" 중 API 응답으로 환원 가능한 것만 도출, 나머지는
underivable 로 기록 (사유: "browser-only").

## 2. acceptance.yaml 스키마 (v1)

위치: `docs/acceptance.yaml` (skeleton/tasks.md 와 동급의 파이프라인 아티팩트).

```yaml
version: 1
scenarios:
  - id: A-001                    # ^A-\d{3}$ (T-ID 계약과 동형)
    feature: "할일 추가"          # requirements 확정 기능명 (traceability)
    gwt: "Given 빈 목록 / When 제목 입력 후 추가 / Then 목록에 1건 + done=false"
    profile: fastapi             # 활성 프로파일 id — 실행 대상/부팅 결정
    kind: http                   # http | cli
    steps:
      - method: POST
        path: /api/todos
        json: {title: "우유 사기"}
        expect: {status: 201}
        capture: {todo_id: "id"}          # 응답 JSON dotted path → 변수
      - method: GET
        path: /api/todos/{todo_id}        # {var} 치환
        expect:
          status: 200
          json: {done: false, title: "우유 사기"}   # dotted path = 기대값 (부분 일치)
  - id: A-002
    feature: "todo CLI 추가"
    gwt: "..."
    profile: python-cli
    kind: cli
    steps:
      - run: "python -m app add 우유"     # cwd = 프로파일 path
        expect: {exit: 0, stdout_contains: ["추가"]}
underivable:
  - feature: "스트릭 애니메이션"
    gwt: "Then 카드에 체크 표시가 부드럽게 나타난다"
    reason: browser-only
```

단언 최소 집합(v1): `status`, `json`(dotted path 부분 일치), `exit`,
`stdout_contains`. 캡처: dotted path → 변수, `{var}` 치환은 path/json 값/run 문자열.
dotted path 게터는 ~20줄 (jsonpath 라이브러리 도입 금지 — YAGNI).

## 3. /ha-accept 스킬 (신규)

```
prepare  → 상태 검사 (verified|reviewed — ha-smoke 와 동일) + skeleton 에서
           GWT 블록/확정 기능 목록/interface.http 선언 엔드포인트/활성 프로파일 추출
           + 기존 acceptance.yaml 유무 → JSON
(LLM)    → prepare 출력 기반 acceptance.yaml 파생 (부모 세션 judge 티어 — 번역/판단
           작업, 코드 아님. Agent 위임 불필요) — SKILL.md 가 파생 규칙 제공
validate → 스키마 검증(BLOCK) + 참조 엔드포인트가 skeleton interface.http 에 선언돼
           있는지 교차 검증(BLOCK — 시나리오가 스펙에 없는 API 를 상상하면 결함)
           + 커버리지 advisory (확정 기능 대비 시나리오 0개 기능 + underivable 집계)
run      → 프로파일별 실행: http kind 는 booted_server (스모크와 동일 부팅) 안에서
           스텝 순차 실행, cli kind 는 subprocess. 시나리오별 PASS/FAIL + 실패 스텝
           상세 → JSON. 전체 exit: 하나라도 FAIL 이면 1 (advisory 지표)
record   → record_verify(step="accept", passed, summary) — 상태 전이 없음
```

파생 규칙 (SKILL.md 에 명시 — AI-Gherkin 안티패턴 방어):
- 시나리오 1개 = GWT 1개 (다중 행동 묶기 금지)
- 존재하는 선언 엔드포인트만 사용 (validate 가 어차피 차단)
- 확신 없으면 만들지 말고 underivable + reason — **발명 금지**
- 변경계 스텝의 상태 오염: v1 은 dev 인스턴스 대상 실행을 전제 — 시나리오는
  자기 완결적으로 작성 (자기가 만든 리소스만 조회). 실행 순서는 파일 순서 보장.

## 4. 공용 부팅 모듈 추출 — `skills/_ha_shared/runtime.py`

ha-smoke 의 `_kill_tree` + readiness 폴링을 추출해 `kill_tree()`, `wait_ready()`,
`booted_server()` (contextmanager: 기동→ready 대기→yield origin→트리 정리) 제공.
- ha-accept 가 사용. **ha-smoke 도 같은 커밋에서 이 모듈로 리팩터** (헬퍼 중복 금지
  규칙 — 기존 ha-smoke 테스트 그린 유지가 리팩터의 검증 기준).
- probe 의 판정 로직(_probe_url 의 결과 dict 구성)은 ha-smoke 에 남긴다 — 공유는
  프로세스 수명주기 관리만.

## 5. pipeline_advisor 통합

`_accept_state()` = `_smoke_state()` 와 동형 (마지막 passing verify 이후의
step=="accept" 레코드만 집계). 배치: **smoke passed 이후** (accept 는 앱 부팅을
전제하므로 smoke 실패 상태에서 돌릴 의미 없음).
- smoke passed + accept pending → `/ha-accept` 제안 (mode=auto)
- accept failed → HITL (smoke FAIL 과 동일 — 수정 재검증 vs 진행, 사용자 선택)
- accept passed → 기존 다음 스텝 (ship_confirm 등)
- **acceptance.yaml 부재 + GWT 도 부재(구버전 skeleton)** → accept 단계 자체를
  skip (advisor 가 제안하지 않음) — 하위 호환.

ha-run SKILL.md 파이프라인 문자열 + CLAUDE.md 파이프라인 맵 + README 갱신 필요.

## 6. 게이트 등재 (GATES.md)

| 게이트 | severity | 우회 |
|---|---|---|
| acceptance.yaml 스키마/미선언 엔드포인트 참조 (validate) | BLOCK | — (파생 수정이 조치) |
| 시나리오 실행 FAIL (run) | advisory | HITL 판단 (smoke 와 동일) |
| 커버리지 구멍 (기능당 시나리오 0개 / underivable) | advisory | — |

## 7. 변경 파일 전수

| 파일 | 변경 |
|---|---|
| skills/_ha_shared/runtime.py | 신규 — kill_tree/wait_ready/booted_server |
| skills/ha-smoke/run.py | runtime.py 사용으로 리팩터 (동작 불변) |
| skills/ha-accept/run.py + SKILL.md | 신규 스킬 |
| backend/src/orchestrator/pipeline_advisor.py | _accept_state + 배치 |
| skills/ha-run/SKILL.md, CLAUDE.md(파이프라인 맵), README | 파이프라인 문자열 |
| backend/docs/GATES.md | §6 게이트 3행 + 집계 |
| backend/tests/skills/test_ha_accept_*.py | 신규 (스키마/validate/러너/캡처/치환) |
| backend/tests/orchestrator/test_pipeline_advisor*.py | accept 상태 회귀 |
| 미러 | cp + drift 0 |

## 8. 리스크

- **파생 품질**: LLM 이 GWT 를 잘못 번역 → validate 의 엔드포인트 교차 검증 +
  acceptance.yaml 이 리뷰 가능한 아티팩트라는 점 + underivable 강제로 3중 완화.
- **상태 오염**: 변경계 스텝이 dev DB 에 흔적 — v1 수용 (시나리오 자기 완결 규칙 +
  SKILL.md 경고). 임시 DB 프로비저닝은 후속.
- **flaky**: readiness 폴링 재사용 + 스텝당 타임아웃 3s(스모크 계층2와 동일) +
  재시도 없음 (fail fast — flaky 는 산출물 결함 신호).
- **구버전 skeleton (GWT 없음)**: advisor skip + prepare 가 명시 보고 — 하위 호환.

## 9. 구현 순서

1. Phase 1: runtime.py 추출 + ha-smoke 리팩터 (기존 테스트 그린)
2. Phase 2: ha-accept run.py (스키마/validate/러너) + SKILL.md + 테스트
3. Phase 3: advisor 통합 + 문서 (GATES/CLAUDE.md/README/ha-run) + 미러 동기
