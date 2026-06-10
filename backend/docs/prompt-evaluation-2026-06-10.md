# HarnessAI 프롬프트 종합 평가 (2026-06-10)

전체 프롬프트 표면 21개(에이전트 11 + `mobile_coder_shared` 1 + `/ha-*` 스킬 9) +
`agents.yaml` 를 읽고, 최신 멀티에이전트/컨텍스트 엔지니어링 연구에 비추어 평가한 기록.

> 적용 상태: 본 평가 직후 **B(스킬 dedup 완성)** 적용함. H2(이중 경로)·M1·M2·L1 은 미적용 — 아래 우선순위 표 참조.

---

## 총평

**현업 시니어 기준 B+ / A-.** 개별 프롬프트의 규율(rigor)은 상위 1% — 모호성 제거, 결정론적
게이트, 자기검증 루프가 공개된 멀티에이전트 프레임워크(MetaGPT/ChatDev) 프롬프트보다 정교하다.
다만 **시스템 차원의 정합성(DRY · altitude · 이중 경로)** 에서 구조적 부채가 있다.
한마디로: **"각 프롬프트는 A, 프롬프트들의 집합은 B".**

| 영역 | 점수 | 근거 |
|---|---|---|
| 모호성 제거 / 결정권 분리 | A | 금지표현→요구표현 표, 자율결정 금지 매트릭스(전 코더 공통) |
| 결정론적 게이트 설계 | A | run.py exit-code 차단, prepare(advisory)/record(차단) 분리 |
| 자기검증 / 반-환각 | A− | ha-review §2.6 fp-check, LESSON Pending(자동적용 안 함) |
| 보안 내장 | A− | 7훅 + 모바일 룰 + insecure-defaults/sharp-edges 이식 |
| DRY / 단일 진실원천 | C → **B+** (dedup 적용 후) | 6스킬 guideline 블록 복붙(→해소), 모바일 룰 4중 인라인(의도적) |
| 프롬프트 altitude | B− | architect/backend_coder 규칙 과적재(laundry list) |
| 아키텍처 정합성 | C+ | 스킬경로 vs Orchestra경로 이중화 → 리뷰 기준 표류 위험 |
| "시니어 팀" 협업감 | B− | 산출물만 반환, 전문가 의견·우려 채널 부재(Designer만 예외) |

---

## 1. 잘된 점 (유지·강화할 자산)

1. **결정론과 LLM 판단의 분리** — `prepare` 는 항상 advisory(exit 0), 차단은 `record` 에서.
   `record --passed false` 에 `--rework-tasks` 없으면 run.py 가 exit 1 (ha-verify). LLM 이 게이트를
   무드로 통과시키는 실패를 코드로 막음.
2. **반-환각 검증 내장** — ha-review §2.6 fp-check: "BLOCK/WARN 을 REJECT 로 보고하기 전 코드를
   직접 읽어 TRUE/FALSE 판정". LLM-as-judge 의 "raw 출력 무비판 신뢰 금지" 원칙 구현.
3. **모호성 제거 매트릭스 일관** — 모든 코더에 "자율 결정 금지" 표 + 에스컬레이션 절차.
   Anthropic "right altitude(구체적이되 유연)" 의 구체적 실행.
4. **안전한 자기개선 루프** — ha-review 가 LESSON 을 Pending 섹션에만 자동 추출, main 적용은
   사용자 promotion. 가짜 LESSON 자동 적용 방지.
5. **TDD Iron Law + AI Slop 차단** 이 구현 단계(ha-build)에 명시.

---

## 2. 구조적 문제

### H1 — DRY 위반 / 다중 진실원천 (일부 해소)
- **"guideline_paths 읽으세요" + 5프로파일 목록** 이 ha-init/ha-design/ha-plan/ha-build/ha-verify/
  ha-review 중 4개에 토씨까지 복붙됐었음. `_ha_shared/GUIDELINES_NOTE.md` 가 이미 단일 원천으로
  존재하고 ha-plan/ha-build 는 참조만 하고 있었음 → **나머지 4개도 참조로 교체(B 적용 완료).**
- **모바일 골든원칙** 이 shared.md + 4개 코더에 인라인 — 단, 이는 *런타임이 단일 파일만 전달*
  하는 제약 때문에 **의도된 설계**(mobile_coder_shared.md 가 직접 명시). DRY 로 보이지만 손대면
  런타임 무효 → **건드리지 않음.** 대신 "shared.md 수정 시 4개 동기화" 규칙을 지켜야 함.

### H2 — 스킬 경로 vs Orchestra 경로 이중화 (미해결, 최우선 후보)
HarnessAI 엔 실행 경로가 둘이다:
- **/ha-* 스킬 경로**: ha-design 이 architect/designer 를 Read, ha-plan 이 orchestrator 를 Read.
  단 **ha-review 는 reviewer/CLAUDE.md 를 안 읽고 자체 재구현**(fp-check 등 최신 로직). qa 도 동일.
- **백엔드 Orchestra 경로**(FastAPI 대시보드, port 3002): `orchestrate.py` 가
  `runner.run("reviewer", ...)`(:579,:722) / `runner.run("qa", ...)`(:764) 로 dispatch,
  `runner._resolve_prompt_path` 가 agents.yaml 의 `prompt_path` 로 reviewer/qa CLAUDE.md 로드.

→ **결론: reviewer/qa CLAUDE.md 는 죽지 않았다**(Orchestra 경로에서 살아있음). 단 ha-review
  SKILL.md(최신, fp-check 포함)와 reviewer/CLAUDE.md(grep 중심, 구식)가 **서로 다른 리뷰 기준**
  을 가짐 → 어느 경로로 도느냐에 따라 리뷰 품질이 갈린다. 둘 중 정본을 정하거나 단일화해야 함.

### M1 — 프롬프트 altitude 과적재
`backend_coder/CLAUDE.md` 에 SSE 스트리밍 전체 코드블록, MAX()+1 retry 전체 코드가 인라인.
모든 백엔드 태스크가 단순 CRUD 라도 이 가이드를 항상 짊어진다. Anthropic "edge case laundry list
금지, 예시는 just-in-time" 위반. 이미 `docs/guidelines/fastapi/` JIT 인프라가 있으니 그쪽으로 이동 권장.

### M2 — 모바일 4프롬프트 구조 불일치
rn 은 `권위순서 → 자율결정금지 → 골든원칙` 순, flutter/android/ios 는 `골든원칙 → 담당 → 권위순서`
순. 같은 역할군인데 섹션 순서 제각각 = 템플릿 없이 복붙-수정한 흔적. 공통 템플릿으로 통일 권장.

### L1 — "시니어 팀" 협업감 부재
모든 에이전트가 산출물만 반환. "내가 우려하는 1가지", "스펙은 따랐지만 이견 있음" 채널이 Designer 의
`CONFLICT` verdict 외엔 없음. 각 에이전트에 distilled 요약 + 전문가 우려 반환 블록 추가 시
"시니어 팀 운영" 체감이 크게 오른다(Anthropic 의 1-2k 토큰 distilled summary 패턴).

### L2 — 모델 버전 노후
agents.yaml 이 claude-opus-4-6 / sonnet-4-6 / haiku-4-5. 현재 최신 opus-4-8. 단 스킬 경로
(Agent model="sonnet")엔 무관, Orchestra 경로만 해당 → H2 판단 후 결정.

### (신규 발견) 미러 divergence
repo `skills/` 와 런타임 `~/.claude/skills/` 가 심링크가 아닌 별도 복사본이고 현재 내용이 다름.
한 쪽만 수정하면 런타임에 반영 안 됨 → 수정 후 미러 동기화 필수.

---

## 3. 우선순위

| # | 문제 | 심각도 | 처방 | 상태 |
|---|---|---|---|---|
| H1 | 스킬 guideline 블록 복붙 | 높음 | GUIDELINES_NOTE 참조로 통일 | **적용 완료** |
| H2 | 스킬/Orchestra 이중 경로, 리뷰 기준 표류 | 높음 | 정본 경로 결정 → 단일화 | 미해결 |
| M1 | backend_coder altitude 과적재 | 중간 | 코드블록을 guidelines/fastapi/ 로 이동 | 미해결 |
| M2 | 모바일 4종 구조 불일치 | 중간 | 공통 템플릿으로 순서 통일 | 미해결 |
| L1 | 시니어 협업감 부재 | 낮음(목표 직결) | 전 역할에 "작업요약+우려" 반환 블록 | 미해결 |
| L2 | 모델 노후 | 낮음 | H2 판단 후 결정 | 미해결 |

---

## 참고 문헌 (리서치 출처)

- Anthropic — Effective Context Engineering for AI Agents
  https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Anthropic — How we built our multi-agent research system
  https://www.anthropic.com/engineering/multi-agent-research-system
- MetaGPT (arXiv 2308.00352) / ChatDev (IBM Think)
- Live-SWE-agent (arXiv 2511.13646) / SWT-Bench (NeurIPS 2024)
- LLM-as-a-Judge (Evidently AI guide; Monte Carlo 7 best practices)
- "When 'A Helpful Assistant' Is Not Really Helpful" (arXiv 2311.10054) — 페르소나 문구의
  정확도 개선 효과는 신뢰 불가; 멀티에이전트 토론만 +13% 검증됨.
