# HarnessAI 벤치마크

**"진짜 돌아가나?" 에 수치로 답변**. LLM 호출 없이 측정 가능한 핵심 연산 + 품질 게이트.

## 문서 인덱스

| 문서 | 무엇 | 왜 |
|---|---|---|
| **이 문서** | 핵심 연산 latency (profile 감지 / skeleton 조립 / harness CLI) | `/ha-*` UX 예측 |
| [gate-coverage.md](gate-coverage.md) | 9개 게이트 중 정규식/AST 기반 **7개** 커버리지 (35 fixtures, **100%** precision/recall/accuracy) | 게이트가 선언대로 지키는지 자기 검증 |
| [dogfooding-catches.md](dogfooding-catches.md) | LESSON 21개 ↔ 원천 프로젝트 ↔ 현재 게이트 매핑 (정성적) | LESSON 이 단순 기록에서 **게이트 강제** 로 올라가는 흐름 |

---

## 측정 대상 (핵심 연산 latency)

| 영역 | 무엇을 측정 | 왜 중요 |
|---|---|---|
| `profile_detect` | 새 프로젝트에서 프로파일 감지 (registry + paths × 파일 읽기) | `/ha-init` 의 첫 단계. 느리면 UX 저하 |
| `skeleton_assemble` | 20 섹션 조각 로드 + `{{section_number}}` 치환 + 연결 | `/ha-init` 의 두번째 단계. 매 프로젝트마다 1회 |
| `harness validate` | 27 파일 스키마 검증 (프로파일 + registry + fragments) | CI 에서 매번 실행. 느리면 dev 루프 방해 |
| `harness integrity` | skeleton.md 선언 ↔ 실재 FS 검증 + 플레이스홀더 감지 | `/ha-verify` 마다 실행 |
| `find_placeholders` | 텍스트 내 미치환 placeholder 탐색 + HTML/백틱 예외 | 크기 증가에 스케일링 |

## 측정 방법

- `scripts/benchmark.py` — 각 항목 N회 반복 (default 20) 후 mean / median / stdev / min / max
- 단위: milliseconds
- LLM subprocess 호출 포함 없음 — 순수 코드 성능
- 측정 기준: Python 3.12.12, Windows, 단일 스레드

### 재현

```bash
cd backend
uv run python ../scripts/benchmark.py --iterations 30
# 결과: docs/benchmarks/results.md + results.json
```

**install.sh 측정 포함하려면** (shell 환경 안정 필요):
```bash
HARNESS_BENCH_INSTALL=1 uv run python ../scripts/benchmark.py
```

## 최신 결과 (2026-04-18, 30 iterations)

| 측정 | mean | median | p_min | p_max |
|---|---|---|---|---|
| profile_detect | **4.70 ms** | 4.26 ms | 3.88 ms | 10.35 ms |
| skeleton_assemble | **0.13 ms** | 0.01 ms | 0.01 ms | 3.48 ms |
| harness_validate | **149.19 ms** | 146.00 ms | 139.65 ms | 174.26 ms |
| harness_integrity | **104.09 ms** | 104.30 ms | 96.88 ms | 119.15 ms |
| find_placeholders (100B) | **0.01 ms** | — | — | — |
| find_placeholders (10KB) | **0.02 ms** | — | — | — |
| find_placeholders (100KB) | **0.14 ms** | — | — | — |

상세: [results.md](results.md) · 원본 JSON: [results.json](results.json)

## 해석

- **`/ha-init` 체감 속도**: 프로파일 감지 + skeleton 조립 총 ~5ms. 사용자 느낌엔 instant. LLM 인터뷰 시간이 dominant.
- **`harness validate` 149ms**: subprocess fork + yaml 파싱 포함. CI 에서 수십 번 돌려도 부담 없음.
- **`harness integrity` 104ms**: 대부분 subprocess fork 비용. 실제 검증 로직은 <10ms (subprocess 오버헤드 ~95ms).
- **`find_placeholders` 선형 스케일링**: 100B → 100KB (1000배) 에서 시간 ~10배 증가. O(n) 확인. 10MB 급 skeleton 도 14ms 예상.

## 제외 / 향후

### LLM 호출 포함 측정 (ui-assistant 완주 후)

`harness-plan.md::verify_history` 와 `tasks` 에서 aggregate:
- 단계별 소요 시간 (ha-init → ha-design → ... → ha-review)
- 토큰 누적 (input/output)
- 추정 비용 ($USD)

구현: `scripts/collect_e2e.py` (다음 세션)

### 비교 벤치마크

**현재**: [gate-coverage.md](gate-coverage.md) 로 HarnessAI 게이트의 자기 검증 35 fixtures
(100% precision/recall/accuracy) + [dogfooding-catches.md](dogfooding-catches.md) 로 plain Claude
대비 **구조적 차이** 정성 기록.

**향후** (동일 요구사항 controlled head-to-head):
- HarnessAI (`/ha-*` 풀 파이프라인)
- Plain Claude Code (CLAUDE.md 만)
- Cursor / Copilot

메트릭: LESSON 위반 수 · 소요 시간 · 토큰/비용 · 최종 테스트 통과율.

비용/시간 제약으로 currently deferred.

## 재현 이슈

- **Windows cp949 터미널**: 결과 파일은 UTF-8 로 정상. 터미널 stdout 의 한글이 깨짐. `python -X utf8` 환경 또는 PowerShell UTF-8 모드 권장.
- **install.sh 측정**: Windows MSYS 와 Python subprocess 의 bash 경로 해석 차이로 가끔 rc=127. 환경변수 `HARNESS_BENCH_INSTALL=1` 로 opt-in.
- **subprocess overhead**: `harness validate/integrity` 의 대부분은 Python 인터프리터 startup. 같은 Python 프로세스 내 호출 시 <10ms.
