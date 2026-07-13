---
name: ha-deepinit
description: |
  HarnessAI v2 — 기존 코드베이스 분석 → hierarchical AGENTS.md 자동 생성.
  /ha-init 대안 또는 보완: 빈 skeleton 대신 코드 분석 결과 기반 채움.
  Use when: 기존 프로젝트에 v2 도입, "기존 코드 분석", "/ha-deepinit"
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - Agent
---

## 역할

이미 코드가 있는 프로젝트에서 (예: code-hijack, HabitFlow), 코드 구조를 분석해서:
1. 루트 `AGENTS.md` — 프로젝트 전체 요약
2. 주요 디렉토리별 `AGENTS.md` — 해당 디렉토리의 역할/규약/주요 파일
3. (선택) `harness-plan.md` 의 `user_description_original` 보강

이렇게 만들면 `/ha-design` 단계에서 빈 skeleton 채울 때 훨씬 풍부한 컨텍스트로 시작 가능.

**입력**: 기존 코드베이스
**출력**: `AGENTS.md` 파일 N개 (계층적)
**다음**: `/ha-init` 또는 `/ha-design`

## 실행 순서

### 1. 프로젝트 스캔
```bash
python ~/.claude/skills/ha-deepinit/run.py scan --depth 3
```
JSON 출력: 주요 디렉토리 목록 (size, file count, primary language), 의미 있는 디렉토리 필터링 결과 (test/__pycache__/node_modules 제외).

### 2. 디렉토리별 분석 (Agent 병렬)
의미 있는 디렉토리(보통 5~15개) 각각에 대해 Agent 호출:
```
Agent({
  description: "Analyze <dir>",
  subagent_type: "Explore",
  model: "sonnet",   // 부모 모델(1M 컨텍스트 등) 상속 방지 — 표준 컨텍스트 강제
  prompt: "디렉토리 <dir> 의 역할, 주요 파일, 컨벤션 패턴, 외부 의존성을 200단어 이내로 요약해서 AGENTS.md 형식으로 출력. 모든 역할/컨벤션 주장에는 근거 인용을 백틱으로 포함 — `상대/경로.py` 또는 `상대/경로.py:라인`, 실재 파일만 (validate 게이트가 경로 실재를 기계 검증). 파일 3개 미만이면 요약 없이 단순 인덱스만."
})
```

### 3. 루트 AGENTS.md 합성
모든 sub-agent 결과 + 프로젝트 메타(README, pyproject.toml/package.json) 종합 → 루트 AGENTS.md:
```markdown
# <Project Name>

<1줄 요약>

## 구조
- backend/ — <역할>
- frontend/ — <역할>
- ...

## 핵심 컨벤션
- <발견된 패턴 N개>

## 외부 의존성
- <목록>
```

### 4. 디렉토리별 AGENTS.md 작성
각 sub-agent 결과를 해당 디렉토리에 `AGENTS.md` 로 저장 (이미 있으면 backup).

### 4.5. 인용 게이트 (validate — 필수)
```bash
python ~/.claude/skills/ha-deepinit/run.py validate --project "$PROJECT_ROOT"
```
- 각 AGENTS.md 의 백틱 파일 인용 (`path` / `path:line`) 을 기계 검증:
  경로 실재 (AGENTS.md 디렉토리 → 프로젝트 루트 순 해석) + 최소 1개 존재 + 라인 번호가 파일 길이 이내
- **exit 1 (환각 경로 / 라인 초과 / 인용 0개) → 해당 AGENTS.md 수정 후 재실행.**
  인용 없는 요약 = 검증 불가 주장 — Agent 산출물의 주 실패 모드가 환각 경로다.
- 의도적 완화 (인덱스만 있는 소형 디렉토리 등): `--min-citations 0`

### 5. (선택) harness-plan 보강
이미 `/ha-init` 이 실행됐다면 `harness-plan.md` 의 `user_description_original` 을 분석 결과 요약으로 보강:
```bash
python ~/.claude/skills/ha-deepinit/run.py augment-plan
```

### 6. 다음 안내
```
✅ /ha-deepinit 완료
생성: <root>/AGENTS.md + N개 디렉토리

다음:
  - 새 프로젝트라면: /ha-init (이제 AGENTS.md 가 풍부한 컨텍스트 제공)
  - 이미 init 했으면: /ha-design (skeleton 채우기 — 더 정확한 결과 기대)
```

## 가드레일

- **validate (§4.5) 통과 전 완료 보고 금지** — 인용 게이트가 이 스킬의 유일한 기계 검증
- 기존 AGENTS.md 가 있으면 항상 backup (`.AGENTS.md.bak-<ts>`)
- 분석 결과를 코드에 반영 (수정) X — 문서만
- 큰 프로젝트(>500 파일)는 depth 2 권장 (성능)
- node_modules/__pycache__/.venv/dist 자동 제외

## 트러블슈팅

**Agent 호출 너무 느림**: depth 줄이거나 디렉토리 화이트리스트 (`--include backend,frontend`).
**분석 품질 낮음**: 디렉토리 크기 너무 작으면 의미 X. 통합해서 분석.
