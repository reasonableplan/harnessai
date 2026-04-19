# E2E 2차 (초기): ui-assistant (fastapi + react-vite monorepo)

**진행 중** — 2026-04-18 현재 backend `building`, frontend `planned`. 본 문서는 초기 발견 + 중간 지표. 완주 후 전면 업데이트 예정.

## 프로젝트

- **이름**: ui-assistant
- **목적**: Figma 스타일 드로잉 → 프론트엔드 코드 변환 개인용 도구
- **스택**: 모노레포 — FastAPI 백엔드 + React+Vite 프런트엔드
- **위치**: `C:/Users/juwon/OneDrive/Desktop/ui-assistant`
- **프로파일**: `fastapi` (backend/), `react-vite` (frontend/)
- **plan 구성**: 독립 `harness-plan.md` **2개** (`backend/docs/` + `frontend/docs/`)

## 왜 이 프로젝트를 2차 E2E 로 택했나

- **code-hijack (1차) 와 상반되는 특성** 필요: 단일 스택 CLI vs **모노레포 + 웹**
- **프로파일 기반 아키텍처** ([ADR-001](../decisions/001-profile-based-architecture.md)) 의 진짜 검증 — 2개 스택 동시 감지 + 2개 독립 plan
- **JS/TS 쪽 첫 실전** — HarnessAI 가 Python 편향된다는 약점 (평가 지적) 을 직접 테스트
- **규모가 code-hijack 보다 큼** — 60+ 프런트 모듈, 40+ 백엔드 모듈 → 게이트 부하 테스트

## 타임라인 (진행 중)

| 날짜 | 이벤트 | 결과 |
|---|---|---|
| 2026-04-17 17:39 | `/ha-init` (양쪽) | fastapi + react-vite 자동 감지 ✅ |
| 2026-04-17 17~22 | `/ha-design` (양쪽) | skeleton.md 채움 |
| 2026-04-17 22~ | `/ha-plan` | tasks.md 생성 |
| 2026-04-18 01~ | `/ha-build` (backend 진행) | backend: `building`, frontend: `planned` |
| 2026-04-18 03 | **이번 세션 시점: 신규 게이트 실전 투입** | |
| 이후 | ... 완주 시 업데이트 |

## 초기 발견 (신규 게이트 2차 실전 발동)

본 세션에서 HarnessAI v2 의 신규 게이트 (harness integrity, 테스트 분포) 가 실제 프로젝트에서 어떻게 작동하는지 검증.

### 🔴 발견 1: placeholder 정규식 HTML 태그 false positive

**현상**: ui-assistant frontend 의 `/ha-verify` → `harness integrity` 실행 시:

```
[ERROR] <div>  — /ha-design 에서 실제 값으로 기입
[ERROR] <pre>  — /ha-design 에서 실제 값으로 기입
[ERROR] <pkg>  — /ha-design 에서 실제 값으로 기입  ← 진짜 placeholder
```

React 컴포넌트 문서화에서 `<div>`, `<pre>` 같은 **HTML 태그** 가 `<[a-z_]...>` 패턴 매칭됨.

**원인**: `find_placeholders` 의 정규식이 HTML 태그를 구분 못 함.

**수정**: `_HTML_TAGS` frozenset (85개 표준 HTML/SVG 태그) blacklist 추가. commit `273fdb5`.

### 🔴 발견 2: 마크다운 인라인 백틱 템플릿 예시 false positive

**현상**: `<pkg>` 가 `` `<pkg>` `` 인라인 백틱 안에 있어도 placeholder 로 감지.

```markdown
| 날짜 | 패키지 | 변경 | 사유 |
|------|--------|------|------|
| `<YYYY-MM-DD>` | `<pkg>` | `<v1 → v2>` | <사유> |
```

이건 "의존성 변경 기록 **format 예시**" — 템플릿 문법. 치환 대상 아님.

**수정**: 스캔 전에 백틱 인라인 코드 제거. commit `273fdb5`.

### ✅ 수정 후 결과

```
backend/  integrity: 0 errors, 0 warnings
frontend/ integrity: 0 errors, 0 warnings
```

### ✅ 테스트 분포 체크

두 프로파일 모두 **0 findings** — 분포 건강.
- backend: src 40+ vs tests 30+ (편차 10x 미만)
- frontend: src 41 vs `__tests__/` 16 파일 × 평균 5 test/file = 76 함수 (편차 10x 미만)

**모노레포 → 프로파일별 독립 집계** 가 정상 작동. 이 기능은 code-hijack (단일 스택) 에서는 검증 불가했음.

## HarnessAI 에 반영한 산출물 (초기)

| 발견 | 반영 | 커밋 |
|---|---|---|
| 1. HTML 태그 false positive | `_HTML_TAGS` blacklist + 회귀 테스트 | `273fdb5` |
| 2. 백틱 인라인 false positive | 스캔 전 백틱 제거 + 회귀 테스트 | `273fdb5` |
| 3. `\`\`\`filesystem` 블록 없을 때 WARN noise | opt-in 전환 (블록 없으면 silent) | `e9ab925` |
| 4. **`done` 상태 drift — 단위 테스트만 통과 → type/lint 스킵** | **LESSON-021 신규** + `ha-build/run.py::cmd_complete` 게이트 강화 제안 | (진행) |

## 🚨 가장 큰 발견 (LESSON-021)

**현상**: backend 13 + frontend 13 태스크가 모두 `done` 상태. verify_history 는 비어있음.

실제 toolchain 돌린 결과:

| 프로파일 | test | lint | type |
|---|---|---|---|
| backend (fastapi) | pytest 53 ✅ | ruff clean ✅ | **pyright 15 errors** ❌ |
| frontend (react-vite) | vitest 60 ✅ | **eslint config 없음** ❌ | tsc clean ✅ |

**분석**: 각 `/ha-build` 실행 시 pytest 만 돌려서 "done" 으로 mark 됨. `toolchain.type`
(pyright) 과 `toolchain.lint` (eslint) 는 **한 번도 실행 안 됐음**. 15 pyright errors 가
몇 주에 걸쳐 누적된 채 숨어 있음.

### 15 pyright errors 분류

- **SQLModel + pydantic 혼용 (11건)**: `model_config = ConfigDict(...)` 을 SQLModel 클래스에
  쓰면 타입 체크 실패. `SQLModelConfig` 필요. 또는 스키마 클래스를 `BaseModel` 로 전환 (이번 수정).
- **SQLAlchemy `.desc()` 추론 실패 (4건)**: `Project.updated_at.desc()` — pyright 가
  `datetime` annotation 으로 추론 → `.desc()` 못 찾음. `from sqlalchemy import desc; desc(col)`
  로 전환 + 남는 `datetime | None` 타입은 `# type: ignore[arg-type]`.

### 수정 후

- backend: pytest 53 / ruff clean / pyright **0 errors** (15 → 0)
- frontend: vitest 60 / tsc clean / eslint **0 errors, 3 warnings** (unused import — 후속 cleanup)
- **verify_history 갱신** — 첫 `/ha-verify` 통과 공식 기록

### HarnessAI 에 미치는 영향

1. **[LESSON-021](../../backend/docs/shared-lessons.md#lesson-021)** 신규 추가:
   "태스크 `done` = toolchain 전체 통과"
2. `ha-build/run.py::cmd_complete` 강화 제안 — 현재 pytest 만 → 전체 toolchain 강제
3. **모든 프로파일에 `toolchain.type` 필드 있는지 확인** — 현재 python-cli / fastapi / react-vite 모두 있음 ✅

## 중간 지표

| 지표 | 값 |
|---|---|
| 감지된 프로파일 | 2 (fastapi, react-vite) |
| skeleton 총 섹션 수 | backend 7 required + 7 optional / frontend 8 required + 5 optional |
| 초기 integrity errors | 4 (HTML×2 + 백틱×1 + 진짜 placeholder×1) |
| **수정 후 integrity errors** | **0** |
| 테스트 분포 findings | 0 (양쪽 모두 healthy) |
| 발견된 false positive 패턴 | 2 (HTML, 백틱) |
| HarnessAI 에 반영된 수정 | 3 커밋 (2 정규식 + 1 opt-in) |

## 교훈 (초기 단계)

### 1. 두 번째 스택 투입이 진짜 검증

code-hijack (Python) 만으로는 HTML 태그 false positive 를 **발견할 수 없었다**. 정규식이 `<[a-z_]...>` 를 매칭하는데 Python 코드에는 HTML 이 안 등장.

ui-assistant 의 React 문서화 (`\`\`\`markdown` 블록 안에 `<div>`) 에서 즉시 드러남.

**일반화**: 새 프로파일/스택을 실증할 때마다 이전엔 보이지 않던 edge case 가 나온다. 6번째 7번째 스택에도 같은 일이 예상됨. → 게이트 설계 시 "언어별 context" 고려 필요.

### 2. 실전 상황이 예상보다 복잡

code-hijack 은 `/ha-init` → 단일 plan 으로 진행. 하지만 ui-assistant 에서는 **유저가 backend/ 와 frontend/ 에 독립 plan 을 만듦**. HarnessAI 는 모노레포 → 단일 plan + 2 프로파일 로 설계됐는데, 실전은 2 plan + 각 1 프로파일 패턴이 등장.

**시사점**: 프로파일 시스템은 작동하지만, plan 구성의 자유도가 더 필요. 이 패턴이 일반적이라면 ADR 추가 필요.

### 3. ai-slop 자동 감지의 한계 확인

harness integrity 는 정규식 기반 — HTML 태그 / 백틱 예시 등 **문맥 의존** false positive 를 완전히 없애기 어려움. 각 실전 프로젝트에서 발견하고 blacklist 확장하는 방식 (현재) 이 가장 실용적. → Phase 5 "LLM 기반 의미론 분석" (ADR TBD) 의 정당화.

### 4. `` ```filesystem `` 블록은 opt-in 이 옳다

처음엔 "블록 없으면 WARN" 으로 설계 — 매 프로젝트 noise. 실전에선 skeleton 템플릿 조각에 해당 섹션이 없어 **모든 프로젝트가 WARN** 발생. 결국 opt-in 으로 전환. 

**일반화**: "선언적 규약" 은 사용자 가 그 규약을 채택하려는 incentive 가 있을 때만 의미. 강제하면 noise.

## 미완성 (ui-assistant 완주 후 업데이트 예정)

- [ ] backend 태스크 완주 → verify_history + tasks 최종
- [ ] frontend `/ha-build` → `/ha-verify` → `/ha-review`
- [ ] `/ship` 까지 완주
- [ ] 토큰/시간/비용 집계 (LLM 포함 벤치마크)
- [ ] 프런트엔드 특화 LESSON 추가 여부 (스타일/접근성 관련)
- [ ] `/ha-review` APPROVE 받은 후 최종 권장사항 정리
- [ ] **두 프로젝트 통합 리포트** (`combined-insights.md`) 작성

## 관련 자료

- **ui-assistant 레포**: `C:/Users/juwon/OneDrive/Desktop/ui-assistant` (사용자 로컬)
- **HarnessAI 반영 커밋**: `273fdb5`, `e9ab925`
- **관련 회귀 테스트**: `backend/tests/orchestrator/test_skeleton_assembler.py` (HTML/백틱 exclusion 3개)
- **1차 리포트**: [code-hijack.md](code-hijack.md)
