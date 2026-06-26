# The Verification Ladder *Is* the Eval Harness — Positioning ha-eval

> Status: **Draft (analysis / positioning)** · Written 2026-06-26 · No code changes
> Origin: review of a proposal to add "#3 Agent Eval" to the HarnessAI pipeline as a new `/ha-eval` skill.
> Decision: **do not build it (deferred).** The *reasoning* — not the verdict — is the value of this document.
> (Korean canonical: `eval-harness-positioning.md`)

---

## 1. Background

In the industry, "agent eval" is treated as the line separating a *demo* from a *product*:
*"If you can't write a rubric distinguishing acceptable from unacceptable tool behavior, your
agent is a demo, not a product."* HarnessAI is a **pipeline where a team of agents generates
software**, so a natural question arises:

> Should we add a meta-eval (`/ha-eval`) that measures whether the pipeline *itself* is getting
> better or worse over time?

This document records the decision — reached after a full cycle of analysis (concept → oracle
definition → literature research → adversarial self-critique → error analysis → ecosystem survey)
— **not** to add it, and why.

## 2. The Core Claim

> **HarnessAI's verification ladder is already an eval harness — we just never called it "eval."**

When you lay out what standard eval methodology (OpenAI / Anthropic / Hamel Husain) recommends,
most of it is **already implemented** in HarnessAI. The task is not to build a new subsystem, but
to *re-recognize existing infrastructure as an eval harness*.

### 2.1 Mapping: industry eval concepts ↔ existing HarnessAI infrastructure

| Industry eval concept | Source | Existing HarnessAI counterpart |
|---|---|---|
| Deterministic checks first, rubric only for the residual | OpenAI skill-regression (outcome/process/style/efficiency) | `ha-verify` (test/lint/type) + `GATES.md` 15 BLOCK gates |
| repo cleanliness / command sequences / toolchain pass | OpenAI | `ha-verify` toolchain enforcement (LESSON-021) |
| policy-violation count | AgentOps 4 metrics | 7 `security_hooks` + auth-guard (LESSON-022~027) |
| regression evals (~100%) vs capability evals (climbing) split | Cursor | pytest 1228-test regression suite + dogfood-defect→regression-test discipline |
| runtime boot check (compilable ≠ functional) | "failure-to-admit" structural failure | `ha-smoke` (boot) + layer 2 (declared endpoints actually hit) |
| seed from real failures ("20–50 real failures") | Hamel | `shared-lessons.md` LESSON-NNN + dogfood #1~#15 |
| binary pass/fail > Likert | Hamel | gate exit codes (BLOCK/PASS) |
| judge-free (avoid LLM-as-judge bias) | LLM-as-judge reliability literature | every gate is deterministic — zero judges |

## 3. Why Not Build a New Skill — Triple Convergence

Three independent lines of analysis converged on the same conclusion.

### 3.1 Error analysis — the true residual is a single thing

Classifying the 35 dogfood failures (LESSON-NNN) by mechanism:

- **Dominant failure = "gate is green, artifact is broken"** (LESSON-021/031/032/033/036/037).
  This is the *weak-oracle problem* that SWE-bench empirically documented (~31% of passing
  patches rely on weak test suites) manifesting in our own dogfood.
- This class **is already recovered** — each LESSON's fix shipped with a regression test
  (tsc -b, encoding smoke, `.py` gating, real-Ollama smoke), and the hardened gate blocks
  recurrence.
- The only residual catchable *solely* by regeneration is **"does the agent apply accumulated
  LESSONs to a *new* spec?"** — and even that is partly absorbed by each project's own tests
  (LESSON-013/021).

### 3.2 Adversarial self-critique — all 3 oracle-mechanism flaws depend on "regeneration"

The oracle spec drafted during review (Tier 1 deterministic + Tier 2 independent acceptance) had
three flaws: (1) `k=3 + pass^k` is statistically worst-of-both; (2) Tier 1 (present/gates) is
nearly circular on its own output because the pipeline already enforces them as exit conditions
(always green, low information); (3) the "regeneration" run model contradicts the strategic
conclusion "don't build the runner." **All three depend on the premise that we are measuring the
regeneration-based residual** — if that residual is small, the entire flaw debate dissolves.

### 3.3 Ecosystem — nobody builds the "pipeline → whole repo" unit

Surveying off-the-shelf eval tools (Promptfoo, DeepEval, EvalView, SkillTester, OpenAI
skill-regression):

- **The methodology matches ours** — OpenAI's "deterministic first, rubric only for the residual"
  is exactly our ladder philosophy. We are implementing the standard, not reinventing it.
- **But every tool's eval unit = "a single prompt invocation / a single working directory."**
  Promptfoo states it plainly: *"no built-in artifact pipeline — does not natively orchestrate
  multi-codebase generation and cross-repo integration testing."*
- HarnessAI's eval unit is **"the `ha-init`→`design`→`plan`→`build`→`verify` pipeline produces an
  entire repo that must build and run."** No tool handles that orchestration — and it is precisely
  the regeneration part that §3.1/§3.2 judged most expensive.

→ Building it means taking on the most expensive custom orchestration *while* reinventing the
scoring/CI/reporting layer that promptfoo/DeepEval already solve. The cost/benefit does not justify it.

## 4. The Ecosystem Gap (Positioning)

A fact surfaced by the survey: **there is no off-the-shelf "harness-pipeline self-regression" eval
seeded from dogfood** (absent even from the evals section of awesome-harness-engineering). The
tools evaluate a *production agent's traffic*; they do not self-eval whether a *code-gen pipeline
produces working software*.

This gap cuts two ways:
- **Cost direction (−):** going there makes us a pioneer with no reference orchestration to borrow.
- **Narrative direction (+):** the structure *"the verification ladder = the eval harness"* plus
  the observation *"harness self-eval is still a blank"* is itself material for an article or talk.
  At this point, **describing it clearly** is higher-leverage than building it.

## 5. Decision — A + C

- **A (adopted): do not build.** Recognize `pytest 1228 + GATES 15 + ha-verify/smoke` *explicitly
  as the eval harness*, and keep only the discipline of **adding a regression test for every
  dogfood defect**. Zero new code.
- **C (adopted): this document.** Record the structure and the gap as a narrative.
- **B (conditionally deferred): only if a capability eval is genuinely wanted.** *Wrap*
  promptfoo/DeepEval and write only a custom provider that runs the HarnessAI pipeline once, over
  1–2 golden specs, executed **manually and irregularly**. Not a CI gate; do not reinvent an eval
  framework.

## 6. Triggers to Revisit (when to move to B)

Reconsider B if any of these becomes true:
- A same-class logic bug (C4/C5) **recurs in a new project despite a regression test** — a signal
  the agent fails to apply a LESSON = the direct target of a regeneration eval.
- HarnessAI expands to **multiple primary agents (Gemini/Copilot)** and a "which backend produces
  better software" comparison becomes necessary (cross-provider capability eval).
- Dogfooding reaches **a scale where manual regression verification is impractical.**

---

## Appendix A. Failure taxonomy (error-analysis output)

| Class | Representative LESSONs | Layer that catches it today |
|---|---|---|
| C1 static code defects | 018, 029, STYLE-001 | ha-verify type/lint + ai-slop hook |
| C2 security defects | 022~024, 027, 028 | auth-guard hook |
| C3 design completeness | 008, 013, 014, 002 | ha-review cross-check + skeleton |
| C4 semantic logic bugs | 001, 003, 017, 034 | ⚠️ no automatic gate (needs a test) |
| C5 concurrency / async | 015, 016, 025, 026 | ⚠️ needs a concurrency test |
| **C6 vacuous / mocked gate pass** | 021, 031, 032, 033, 036, 037 | ⚠️ the ladder itself is the hole → mostly recovered via regression tests |

## Appendix B. Research sources

- [Anthropic — Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) (3-grader, pass^k vs pass@k, "two experts reach the same pass/fail")
- [Hamel Husain — LLM Evals FAQ](https://hamel.dev/blog/posts/evals-faq/) (error-analysis-first, ~70% pass rate, the eval-driven-development trap)
- [UTBoost — Rigorous Evaluation on SWE-Bench](https://arxiv.org/html/2506.09289v1) (weak oracles 31%, solution leakage 32.67%)
- [Promptfoo — Evaluate Coding Agents](https://www.promptfoo.dev/docs/guides/evaluate-coding-agents/) (single-working-directory limit, no built-in artifact pipeline)
- [awesome-harness-engineering](https://github.com/ai-boost/awesome-harness-engineering) (OpenAI skill-regression 4 axes; no off-the-shelf dogfood self-eval)
- [Datadog — Offline evaluation for AI agents](https://www.datadoghq.com/blog/offline-llm-evaluations/) (offline+online dual eval; online assumes production traffic → N/A for us)
