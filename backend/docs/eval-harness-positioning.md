# 검증 사다리는 이미 Eval 하네스다 — ha-eval 포지셔닝

> 상태: **초안 (분석/포지셔닝)** · 작성 2026-06-26 · 코드 변경 없음
> 출발: "#3 Agent Eval 을 HarnessAI 파이프라인에 새 스킬(`/ha-eval`)로 추가" 제안 검토.
> 결론: **안 짓는다 (보류).** 근거를 기록 — 결론보다 *추론 과정*이 이 문서의 가치.
> 관련 메모리: ha-eval 설계 검토, 런타임 깨짐 최우선(검증 사다리 상단), 외부코드 추가 금지 룰.

---

## 1. 배경 / 동기

업계에서 "에이전트 eval"은 *데모와 제품을 가르는 선*으로 통한다 — *"acceptable/unacceptable
도구 행동을 구분하는 rubric을 못 쓰면 네 에이전트는 제품이 아니라 데모다."* HarnessAI는
**에이전트 팀이 소프트웨어를 생성하는 파이프라인**이므로, 자연스러운 질문이 떠오른다:

> 우리 파이프라인 *자체*가 좋아지는지 나빠지는지를 측정하는 메타 eval(`/ha-eval`)을 추가해야 하나?

이 문서는 그 질문을 전 사이클(개념 → oracle 정의 → 자료조사 → 적대적 자가평가 →
error analysis → 생태계 조사)로 검토한 뒤 **추가하지 않기로** 한 결정과 근거를 남긴다.

## 2. 핵심 주장

> **HarnessAI의 검증 사다리는 이미 eval 하네스다 — 단지 "eval"이라 부르지 않았을 뿐.**

업계 표준 eval 방법론(OpenAI/Anthropic/Hamel Husain)이 권하는 것을 그대로 펼쳐보면,
대부분이 HarnessAI에 **이미 구현되어 있다.** 새 서브시스템이 필요한 게 아니라, *기존 인프라를
eval 하네스로 재인식*하는 것이 정확하다.

### 2.1 업계 eval 개념 ↔ HarnessAI 기존 인프라 매핑

| 업계 eval 개념 | 출처 | HarnessAI 기존 대응물 |
|---|---|---|
| 결정론 체크 먼저, rubric은 잔여만 | OpenAI skill-regression (outcome/process/style/efficiency 4축) | `ha-verify`(test/lint/type) + `GATES.md` BLOCK 15 |
| repo cleanliness / 명령 시퀀스 / toolchain 통과 | OpenAI | `ha-verify` toolchain 강제 (LESSON-021) |
| 정책 위반 카운트 (policy violations) | AgentOps 4지표 | `security_hooks` 7종 + auth-guard (LESSON-022~027) |
| 회귀 eval(~100% 유지) vs capability eval(상승) 분리 | Cursor | pytest 1228개 회귀 스위트 + dogfood 결함→회귀테스트 규율 |
| 런타임 기동 검증 (compilable ≠ functional) | "failure-to-admit" 구조 실패 | `ha-smoke`(기동) + layer2(선언 엔드포인트 실타격) |
| seed-from-real-failure (실패에서 출발) | Hamel ("20~50 real failures") | `shared-lessons.md` LESSON-NNN + dogfood #1~#15 |
| binary pass/fail > Likert | Hamel | 게이트 exit code (BLOCK/PASS) |
| judge-free (LLM-judge 편향 회피) | LLM-as-judge 신뢰도 literature | 모든 게이트가 결정론 — judge 0 |

## 3. 왜 새 스킬을 안 짓는가 — 3중 수렴

세 갈래의 독립 분석이 같은 결론으로 모였다.

### 3.1 error analysis — 진짜 잔여는 하나뿐

dogfood 실패 35개(LESSON-NNN)를 mechanism 별로 분류한 결과:

- **지배적 실패 = "게이트는 green, 산출물은 깨짐"** (LESSON-021/031/032/033/036/037).
  이것은 SWE-bench 가 실증한 *weak-oracle 문제*(통과 패치의 ~31%가 약한 테스트에 의존)가
  우리 dogfood 에서 발현한 것이다.
- 이 클래스는 **이미 회수됐다** — 각 LESSON의 수정이 회귀테스트를 동반했고(tsc -b,
  인코딩 스모크, `.py` 게이트, 실-Ollama 스모크), 강화된 게이트가 재발을 막는다.
- 재생성(LLM) 으로만 잡히는 순수 잔여 = **"에이전트가 누적 LESSON을 *새* 스펙에 적용하나"**
  하나뿐. 그리고 그것조차 각 프로젝트의 테스트가 부분적으로 흡수한다(LESSON-013/021).

### 3.2 적대적 자가평가 — oracle 메커니즘 결함 3개가 전부 "재생성"에 의존

검토 중 세웠던 oracle spec(Tier1 결정론 + Tier2 독립 acceptance)에는 결함 3개가 있었다:
(1) `k=3 + pass^k`는 통계적으로 worst-of-both, (2) Tier1(present/gates)은 파이프라인이 이미
exit 조건으로 강제하므로 자기 출력에 거의 순환(항상 green, 저정보), (3) "재생성" run 모델이
"러너 짓지 마라"는 전략 결론과 모순. **세 결함 모두 (3.1의) 재생성-기반 잔여를 측정한다는
전제에 의존** → 그 잔여가 작으면 결함 논쟁 자체가 소멸한다.

### 3.3 생태계 — "파이프라인 → 전체 레포" 단위는 아무도 안 만든다

기성 eval 도구(Promptfoo, DeepEval, EvalView, SkillTester, OpenAI skill-regression)를 조사:

- **방법론은 우리와 동일** — OpenAI의 "결정론 먼저, rubric은 잔여만"은 우리 사다리 철학 그대로.
  즉 우리는 재발명이 아니라 표준을 이미 구현 중.
- **그러나 모든 도구의 eval 단위 = "단일 프롬프트 1회 실행 / 단일 작업 디렉토리".**
  Promptfoo는 명시한다: *"내장 artifact 파이프라인 없음 — 다중 코드베이스 생성·교차 레포
  통합테스트를 native로 오케스트레이션하지 않음."*
- HarnessAI의 eval 단위는 **"`ha-init`→`design`→`plan`→`build`→`verify` 파이프라인이 통째
  레포를 만들고 그것이 build+run 돼야 함."** 이 오케스트레이션은 어떤 도구도 다루지 않으며,
  곧 3.1/3.2가 *가장 비싸다*고 판정한 재생성 부분 그 자체다.

→ 새로 짓는다면 가장 비싼 custom 오케스트레이션을 직접 떠안으면서, 스코어링·CI·리포팅
(이미 promptfoo/DeepEval이 푸는 층)을 재발명하게 된다. 비용 대비 정당성 없음.

## 4. 생태계 갭 (포지셔닝)

조사에서 드러난 사실: **dogfood 기반 "하네스 파이프라인 self-regression" eval은
기성품이 없다** (awesome-harness-engineering의 evals 섹션에도 부재). 도구들은 *production
agent의 트래픽*을 평가하지, *code-gen 파이프라인이 동작하는 소프트웨어를 만드는지*를
self-eval 하지 않는다.

이 갭은 두 방향의 의미를 가진다:
- **비용 방향(−):** 우리가 그 길을 가면 선구자라 참고할 기성 오케스트레이션이 없다.
- **서사 방향(+):** *"검증 사다리 = eval 하네스"* 라는 우리 구조와, *"하네스 self-eval은
  아직 빈칸"* 이라는 관찰은 그 자체로 글·발표거리다. 짓는 것보다 *명확히 기술하는 것*이
  현 시점 더 높은 레버리지다.

## 5. 결정 — A + C

- **A (채택): 안 짓는다.** `pytest 1228 + GATES 15 + ha-verify/smoke`를 *eval 하네스로
  명시 인식*하고, **dogfood 결함마다 회귀테스트를 추가하는 규율**만 유지한다. 신규 코드 0줄.
- **C (채택): 이 문서.** 구조와 갭을 서사로 남긴다.
- **B (보류 조건부): capability eval 을 정말 원할 때만.** promptfoo/DeepEval을 *wrap*하고,
  "HarnessAI 파이프라인 1회 실행"만 하는 custom provider를 작성해 골든 1~2개에 **수동·비정기**
  실행한다. CI 게이트로 만들지 않고, eval 프레임워크를 재발명하지 않는다.

## 6. 다시 검토할 트리거 (언제 B로 가나)

아래 중 하나가 참이 되면 B를 재고한다:
- 동일 클래스 로직 버그(C4/C5)가 **회귀테스트로 회수됐는데도 새 프로젝트에서 재발**
  → 에이전트가 LESSON을 적용 못 한다는 신호 = 재생성 eval 의 직접 표적.
- HarnessAI가 **여러 주력 에이전트(Gemini/Copilot)** 로 확장되어 "어느 백엔드가 더 나은
  소프트웨어를 만드나"의 비교가 필요해질 때 (cross-provider capability eval).
- dogfood가 **수동 회귀 검증이 버거운 규모**가 될 때.

---

## 부록 A. 실패 taxonomy (error analysis 산출)

| 클래스 | 대표 LESSON | 지금 잡는 층 |
|---|---|---|
| C1 정적 코드 결함 | 018, 029, STYLE-001 | ha-verify type/lint + ai-slop 훅 |
| C2 보안 결함 | 022~024, 027, 028 | auth-guard 훅 |
| C3 설계 완전성 | 008, 013, 014, 002 | ha-review cross-check + skeleton |
| C4 의미 로직 버그 | 001, 003, 017, 034 | ⚠️ 자동 게이트 없음 (테스트 필요) |
| C5 동시성/async | 015, 016, 025, 026 | ⚠️ 동시성 테스트 필요 |
| **C6 vacuous/mocked 게이트 통과** | 021, 031, 032, 033, 036, 037 | ⚠️ 사다리 자신이 구멍 → 대부분 회귀테스트로 회수됨 |

## 부록 B. 조사 출처

- [Anthropic — Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) (3-grader, pass^k vs pass@k, "두 전문가가 같은 pass/fail")
- [Hamel Husain — LLM Evals FAQ](https://hamel.dev/blog/posts/evals-faq/) (error-analysis-first, 70% 통과율, eval-driven-dev 함정)
- [UTBoost — Rigorous Evaluation on SWE-Bench](https://arxiv.org/html/2506.09289v1) (weak-oracle 31%, solution leakage 32.67%)
- [Promptfoo — Evaluate Coding Agents](https://www.promptfoo.dev/docs/guides/evaluate-coding-agents/) (단일 작업디렉토리 한계, no built-in artifact pipeline)
- [awesome-harness-engineering](https://github.com/ai-boost/awesome-harness-engineering) (OpenAI skill-regression 4축, dogfood self-eval 기성품 부재)
- [Datadog — Offline evaluation for AI agents](https://www.datadoghq.com/blog/offline-llm-evaluations/) (offline+online 이중 eval; online은 프로덕션 트래픽 전제 → 우리에 무관)
