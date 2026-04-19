# Gate Coverage Benchmark

**Purpose**: HarnessAI 총 9개 품질 게이트 중 정규식/AST 기반 **7개** 가 "잡아야 할 패턴" 을 실제로 잡는지, "깨끗한 코드" 를 잘못 잡지 않는지를 정량 측정.

**스코프**: 9개 게이트 중 이 벤치마크가 다루는 7개 = **SecurityHooks 6개 + ai-slop 1개**. 나머지 2개 (`test-distribution`, `skeleton-integrity`) 는 filesystem fixture 가 필요한 구조라 `backend/tests/skills/` 의 pytest 회귀 테스트 + `harness integrity` CLI 로 별도 검증.

**측정 대상** (이 벤치마크):
- `secret-filter` — 하드코딩 시크릿, API 키, DB 연결 문자열
- `command-guard` — `rm -rf`, `curl | bash`, `eval`, `DROP TABLE` 등
- `db-guard` — raw SQL, f-string SQL, WHERE-less DELETE/UPDATE
- `dependency-check` — 프로파일 whitelist 외 패키지
- `code-quality` — 빈 `except`, `print` 디버그, 과도한 `# type: ignore`
- `contract-validator` — skeleton 에 선언 안 된 엔드포인트
- `ai-slop` — 7개 정규식 패턴 (장황한 docstring / 의미 없는 try/except / TODO / unused / pass later / dead 상수 (LESSON-018) / ...)

**방법**:
- 게이트별로 positive fixture (감지해야 함) + negative fixture (건드리면 안 됨) 를 작성
- 각 fixture 를 해당 게이트 함수에 통과시켜 TP/TN/FP/FN 집계
- `precision = TP/(TP+FP)`, `recall = TP/(TP+FN)`, `accuracy = (TP+TN)/전체`

**실행**: `uv --project backend run python scripts/gate_benchmark.py` (`--json` 옵션 지원).

---

## Results (2026-04-19)

| Gate | Fixtures | Precision | Recall | Accuracy | Missed | False alarms |
|------|---------:|----------:|-------:|---------:|:-------|:-------------|
| `secret-filter` | 5 | 100% | 100% | 100% | — | — |
| `command-guard` | 6 | 100% | 100% | 100% | — | — |
| `db-guard` | 5 | 100% | 100% | 100% | — | — |
| `dependency-check` | 4 | 100% | 100% | 100% | — | — |
| `code-quality` | 5 | 100% | 100% | 100% | — | — |
| `contract-validator` | 2 | 100% | 100% | 100% | — | — |
| `ai-slop` | 8 | 100% | 100% | 100% | — | — |
| **전체** | **35** | **100%** | **100%** | **100%** | | |

## 처음 시도의 두 결함 (정직한 기록)

벤치마크 초기 실행에서 두 항목이 실패했고, 이 실패 자체가 유의미한 발견이었다:

**1. `db-guard` false alarm — `parameterized_query`**

Fixture: `cursor.execute("SELECT * FROM t WHERE id = ?", (uid,))`

게이트가 감지함 → 처음엔 오탐으로 보임. 그러나 규칙 재검토 결과 **정당한 감지**. 프로젝트 정책이 "ORM 우선" 이라 `cursor.execute()` 사용 자체가 경고 대상. Negative fixture 를 SQLAlchemy `select()` 기반으로 교체 → 게이트 의도와 일치.

**교훈**: 벤치마크 fixture 가 게이트 의도를 드러내 정책 경계 재확인.

**2. `ai-slop` recall miss — `dead_const_lesson_018`**

Fixture 초안:
```python
_BACKOFF_SECONDS = (1.0, 2.0, 4.0, 8.0)
for i in range(max_retries := 2):
    time.sleep(_BACKOFF_SECONDS[i])
```

게이트 정규식:
```
max_(?:retries|attempts|tries)\s*=\s*[12]
```

Walrus operator (`:=`) 때문에 `=` 하나 매칭에 실패. Fixture 를 LESSON-018 의 실제 패턴으로 수정:
```python
_BACKOFF_SECONDS = (1.0, 2.0, 4.0, 8.0)
max_retries = 2
for i in range(max_retries):
    time.sleep(_BACKOFF_SECONDS[i])
```

**교훈**: Walrus 사용 시 dead 상수 감지 정규식에 빠짐. 향후 패턴 확장 여지 (LESSON-018 개선 후보).

---

## CI 통합

`exit` code:
- `0` — 모든 fixture 가 기대대로 동작
- `1` — 한 개 이상 missed 또는 false_alarm 발생

향후 `.github/workflows/` 에 이 스크립트를 회귀 테스트로 추가 가능 (LLM 호출 없음, 0.1초 이내).

## 한계와 범위

- **측정 대상**: 정규식/AST 기반 **결정론적 게이트**. LLM 판단 (Reviewer agent approve/reject) 은 측정 대상 아님.
- **Fixture 규모**: 게이트별 2-8개. 실전에서는 LESSON 원천 프로젝트 (HabitFlow/code-hijack/ui-assistant 등) 에서 발견된 실제 패턴이 이미 정규식 튜닝에 반영됨 (dogfooding 참조).
- **외부 비교 없음**: plain Claude / Cursor / Copilot 와의 head-to-head 가 아님. 이 문서의 목적은 "HarnessAI 게이트 계약이 선언대로 지켜지는지" 의 자기 검증.

## 관련 문서

- [dogfooding-catches.md](dogfooding-catches.md) — LESSON 원천 프로젝트 & 해당 게이트로 이어진 경로 (정성적)
- [benchmark-results.md](benchmark-results.md) — 핵심 연산 지연 시간 (profile 감지 / skeleton 조립 등)
- [`docs/decisions/004-ai-slop-as-7th-hook.md`](../decisions/004-ai-slop-as-7th-hook.md) — ai-slop 을 게이트로 통합한 배경
