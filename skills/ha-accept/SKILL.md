---
name: ha-accept
description: |
  HarnessAI v2 — 수용 검증 (advisory 게이트). skeleton 의 GWT 수용 기준을
  실행 가능한 시나리오(acceptance.yaml)로 파생해 결정론적으로 실행한다.
  검증 사다리 최상단: test/lint/type(ha-verify) → 기동(ha-smoke) 다음,
  "요구사항대로 동작하는가"를 확인하는 마지막 칸.
  Use when: /ha-smoke PASS 후 배포 전, "수용 기준대로 되는지 확인", "/ha-accept"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
---

## 역할

skeleton 의 `requirements` 섹션에 확정된 기능마다 사용자와 합의한 **GWT 수용 기준**
(Given/When/Then)을 실행 가능한 HTTP/CLI 시나리오로 번역하고, 결정론적으로 실행해
`verify_history` 에 기록한다 (step=`accept`). test/lint/type 은 코드 조각의 정합성을,
ha-smoke 는 "앱이 뜨는가"를 본다 — 이 스킬만이 "의도대로 동작하는가"를 본다.

**입력**: verified 또는 reviewed 상태 + skeleton.md 의 GWT 수용 기준
**출력**: `docs/acceptance.yaml` (신규 아티팩트) + 시나리오 PASS/FAIL + verify_history 갱신
**다음**: PASS 시 `/ha-review`, FAIL 시 원인 수정 후 `/ha-verify` 부터 재검증

## 실행 순서

### 1. prepare — 추출

```bash
python ~/.claude/skills/ha-accept/run.py prepare
```

JSON 출력: 확정 기능별 `{name, gwt: [...]}`, `legacy_skeleton`(GWT 라인이 하나도
없으면 true — 구버전 skeleton), `declared_endpoints`(interface.http 선언 전부,
변경계 메서드 포함), `profiles`(활성 프로파일 `{id, path, toolchain.smoke}`),
`acceptance_yaml_exists`.

`legacy_skeleton: true` 면 GWT 수용 기준 자체가 없는 프로젝트다 — 사용자에게
알리고, 억지로 시나리오를 발명하지 말 것. `/ha-design` 재실행(Step D) 또는
스킵을 사용자에게 확인한다. **사용자가 스킵을 선택하면** 그 결정을 audit trail 로 남긴다
(이 기록이 있어야 /ha-run 드라이버가 accept 단계를 넘어간다):

```bash
python ~/.claude/skills/ha-accept/run.py record \
  --passed true --summary "SKIP — legacy skeleton (GWT 수용 기준 없음, 사용자 확인)"
```

### 2. (LLM) acceptance.yaml 파생

`prepare` 출력을 근거로 `docs/acceptance.yaml` 을 **직접 Write/Edit** 로 작성한다.
run.py 는 실행하지 않는다 — 이 단계는 판단(GWT 산문 → 구조화 시나리오)이라 LLM 몫.

**스키마 (v1)**:

```yaml
version: 1
scenarios:
  - id: A-001                    # ^A-\d{3}$, 파일 내 유일
    feature: "할일 추가"          # prepare 의 확정 기능명과 정확히 일치 (커버리지 집계 기준)
    gwt: "Given 빈 목록 / When 제목 입력 후 추가 / Then 목록에 1건 + done=false"
    profile: fastapi             # 활성 프로파일 id
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
  - id: A-003
    feature: "월 지출 합계"
    gwt: "Given 빈 목록 / When 17,000원 구독 추가 / Then 월 합계에 17,000원 반영"
    profile: fastapi
    kind: http
    steps:
      - method: GET
        path: /api/summary
        capture: {base_total: "monthlyTotal"}       # 집계 baseline
      - method: POST
        path: /api/subscriptions
        json: {name: "넷플릭스", amount: 17000, startedOn: "{today+2}"}   # 날짜식
        expect: {status: 201}
      - method: GET
        path: /api/summary
        expect:
          json_delta: {monthlyTotal: {from: base_total, add: 17000}}   # 변화량 단언
          json_not_contains: {cancelled: {name: "넷플릭스"}}            # 부재 단언
  - id: A-002
    feature: "todo CLI 추가"
    gwt: "Given 빈 목록 / When CLI 로 추가 / Then 목록에 표시"
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

단언 집합 (http): `status`, `json`(dotted path 부분 일치), `json_delta`, `json_not_contains`.
(cli): `exit`, `stdout_contains`.

- `capture` 는 dotted path → 변수. `{var}` 는 이후 스텝의 path/json 값/run 문자열/expect 값에
  치환된다. 문자열 전체가 `{var}` 면 타입이 보존된다 (id 7 → "7" 이 되지 않음).
- **`json_delta: {<dotted>: {from: <변수>, add: <숫자>}}`** — 응답값이 `baseline + add` 인지 본다.
  감소는 음수 (`add: -17000`).
- **`json_not_contains: {<dotted(list)>: 스칼라 | {필드: 값}}`** — 리스트에 그 원소(또는 필드가
  일치하는 원소)가 **없어야** 통과.
- **날짜식 `{today}` / `{today+N}` / `{today-N}`** — 실행일 기준 로컬 날짜(YYYY-MM-DD). "오늘
  기준 2일 후 결제" 처럼 실행일에 의존하는 GWT 에 쓴다 (고정 날짜는 다음 날 깨진다).

**파생 규칙 (엄수 — AI-Gherkin 안티패턴 방어)**:

- **시나리오 1개 = GWT 1개** — 여러 GWT/여러 행동을 한 시나리오에 묶지 말 것.
- **선언된 엔드포인트만** 사용 — `prepare` 의 `declared_endpoints` 에 없는 경로를
  상상해 쓰면 `validate` 가 BLOCK 한다. 없으면 skeleton 이 부족한 것이지 시나리오가
  임의로 채울 자리가 아니다.
- **확신 없으면 만들지 말 것** — 애매하면 `underivable` 에 `feature`/`gwt`/`reason`
  으로 명시 기록한다. 조용히 빠뜨리는 것이 가장 위험한 형태의 커버리지 구멍이다.
  브라우저에서만 확인 가능한 Then(애니메이션, 시각적 배치 등) → `reason: browser-only`.
- **자기 완결적 시나리오** — v1 은 dev 인스턴스를 대상으로 직접 실행한다(임시 DB
  프로비저닝 없음). 각 시나리오는 자신이 만든 리소스만 조회/검증할 것 — 다른
  시나리오나 기존 데이터에 의존하면 실행 순서에 따라 flaky 해진다.
- **집계는 절대값이 아니라 `json_delta` 로** — 합계·개수·잔액처럼 DB 전체 상태의 함수인 값에
  `json: {monthlyTotal: 27000}` 같은 절대값 단언을 쓰면, 다른 시나리오가 만든 데이터에 오염돼
  실행 순서에 따라 깨진다. 반드시 baseline 을 `capture` 하고 변화량으로 단언할 것.
  ("Then 월 합계 27,000원" → 17,000 + 120,000/12 두 건을 만들고 `add: 27000`)
- **실행일에 의존하는 GWT 는 `{today±N}` 로** — "오늘 기준 2일 전 결제일" 을 고정 날짜로 쓰면
  내일 깨진다.
- **"목록에 없음" 은 `json_not_contains` 로** — 부정 조건을 검증 없이 넘기지 말 것.
- `feature` 필드는 `prepare` 가 보고한 확정 기능명과 **정확히 동일한 문자열**로
  쓸 것 — 다르면 커버리지 집계가 "시나리오 0개"로 오탐한다.

### 3. validate — 게이트

```bash
python ~/.claude/skills/ha-accept/run.py validate
```

BLOCK (exit 1): YAML 파싱 실패 / 스키마 위반(버전·ID 형식·중복·필수필드·kind·
steps·expect 허용 키·capture 값 타입) / skeleton `interface.http` 에 없는
엔드포인트 참조(path 파라미터는 `{id}`↔`{todo_id}` 처럼 세그먼트 위치로 비교) /
활성 프로파일에 없는 `profile` 참조.

advisory (exit 0 유지, JSON 의 `coverage` 필드로만 보고): 시나리오가 0개인
확정 기능 목록, `underivable` 개수. BLOCK 이 없으면 이 단계에서 exit 0.

BLOCK 이 나오면 acceptance.yaml 을 Edit 으로 수정 후 재실행 — 스키마/참조
오류는 파생 실수이지 run.py 결함이 아니다.

### 4. run — 실행

프로파일별로 실행한다 (모노레포는 프로파일마다 반복):

```bash
# http kind 시나리오가 있는 프로파일 — 기동 명령/url 도출은
# ha-smoke SKILL.md §2 의 표를 그대로 참조 (동일한 휴리스틱)
python ~/.claude/skills/ha-accept/run.py run \
  --profile fastapi \
  --command "<smoke 명령>" --url "http://127.0.0.1:<port>/" --ready-timeout 60

# cli kind 전용 프로파일 — --command/--url 불필요
python ~/.claude/skills/ha-accept/run.py run --profile python-cli
```

JSON 출력: `{profile, scenarios: [{id, feature, passed, failed_step, detail}, ...]}`.
`failed_step` 은 1-base, 통과 시 `null`. 하나라도 FAIL 이면 exit 1.

프로파일 부팅 자체가 실패하면(ready 전 종료, ready 타임아웃) 그 프로파일의
**모든** 시나리오가 `passed: false` + "부팅 실패 — 시나리오 실행 불가"로
보고된다 — 실행이 안 된 것을 PASS 로 발명하지 않는다.

### 5. record — 기록

```bash
python ~/.claude/skills/ha-accept/run.py record \
  --passed true|false \
  --summary "<예: A-001 PASS, A-002 FAIL(step 2: status 기대 200 실제 404)>"
```

- `verify_history` 에 step=`accept` 엔트리 추가. **상태 전이 없음** — advisory 게이트.
- FAIL 이어도 verified/reviewed 유지 — 다음 판단(수정 후 재검증 vs 진행)은 사용자 몫.
- summary 에 실패 시나리오 id + failed_step + detail 핵심을 포함할 것.

## 가드레일

- **부팅은 반드시 run.py 의 `run` 서브커맨드 경유** (내부적으로 `booted_server`
  사용) — 직접 백그라운드 프로세스를 띄우고 시나리오를 때리지 말 것 (좀비 프로세스,
  ha-smoke 와 동일 이유).
- **FAIL 을 환경 탓으로 PASS 기록 금지** — "타이밍 이슈였을 것" 같은 추측으로
  passed=true 를 기록하지 않는다. 판단 불가면 FAIL 로 기록하고 원인을 detail 에 남긴다.
- **시나리오 발명 금지** — skeleton 에 없는 엔드포인트/기능을 그럴듯하게 채우지
  말 것. `validate` 가 이를 기계적으로 막지만, 애초에 만들지 않는 것이 먼저다.
- `underivable` 로 미룬 GWT 는 이 스킬의 책임 밖(브라우저 검증은 gstack `/qa`,
  `/browse` 의 몫) — 여기서 억지로 HTTP 로 우회 검증하지 말 것.
