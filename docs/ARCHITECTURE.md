# HarnessAI Architecture

🌐 **English** · [한국어](ARCHITECTURE.ko.md)

**Audience**: contributors, portfolio reviewers, future-you — anyone who wants a 30-minute grasp of the system.

**One line**: *profile-based multi-agent orchestration*. You declare per-stack rules; the agents have to follow them; gates block anything that escapes.

---

## 1. Big picture

```
┌──────────────────────────────────────────────────────────────────────┐
│                             User (CLI)                               │
│  /ha-init → /ha-design → /ha-plan → /ha-build → /ha-verify → /ha-review │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                 ┌──────────────────┼──────────────────┐
                 ▼                  ▼                  ▼
        ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
        │  profile     │   │  skeleton    │   │  plan_manager│
        │ (stack rules)│   │  (contract)  │   │ (state m/c)  │
        └──────────────┘   └──────────────┘   └──────────────┘
                 │                  │                  │
                 └──────────────────┼──────────────────┘
                                    ▼
                ┌──────────────────────────────────────┐
                │   7 agents (Claude CLI subprocess)   │
                │   Architect / Designer / Orchestrator│
                │   Backend Coder / Frontend Coder /   │
                │   Reviewer / QA                      │
                └──────────────────────────────────────┘
                                    │
                                    ▼
                ┌──────────────────────────────────────┐
                │   Quality gates                      │
                │   · 6 security hooks                 │
                │   · ai-slop (incl. LESSON-018) — 7 patterns │
                │   · test distribution                │
                │   · skeleton integrity (harness)     │
                └──────────────────────────────────────┘
```

The core idea is a **closed "declare → generate → verify" loop**: the user declares intent in `skeleton.md` (the contract), agents generate the implementation, gates block any contract violation.

---

## 2. Profile system

### Why profiles?

v1 hardcoded four stacks (`fastapi / nextjs / react-native / electron`). Each new stack (python-cli, python-lib, claude-skill) forked the implementation skills (`/my-api`, `/my-ui`, …). Unmaintainable.

v2 abstracts them into **profiles** — one file per stack holding every rule.

```
~/.claude/harness/profiles/
  _base.md          # 11 shared principles (testing, git, errors, security,
                    #   code quality, dependencies, typing, config, two laws)
  _registry.yaml    # detection rules (which files → which profile)
  fastapi.md        # FastAPI backend rules
  react-vite.md     # React + Vite frontend rules
  python-cli.md     # click-based CLI rules
  python-lib.md     # pure library rules
  claude-skill.md   # Claude Code skill rules
```

Each profile frontmatter declares:
- `paths` + `detect` — which directories / files trigger this profile
- `components` — required / optional component types
- `skeleton_sections` — which of the 20 section IDs apply
- `toolchain` — test / lint / type / format commands
- `whitelist` — allowed runtime and dev dependencies
- `lessons_applied` — LESSON IDs the Reviewer must enforce
- `gstack_mode` — auto / manual / prompt integration

Inheritance: every profile `extends: _base`. Child overrides parent; lists union.

### Adding a new stack

One file under `harness/profiles/<stack>.md` + one entry in `_registry.yaml`. Optional: stack-specific skeleton fragments under `harness/templates/skeleton/`. See [CONTRIBUTING.md](../CONTRIBUTING.md#a-새-프로파일-추가).

---

## 3. Skeleton — the contract

`skeleton.md` is the **single source of truth** declaring what the project is. Twenty standard section IDs; each profile picks a subset.

```
overview · requirements · stack · configuration · errors · auth ·
persistence · integrations · interface.{http,cli,ipc,sdk} ·
view.{screens,components} · state.flow · core.logic ·
observability · deployment · tasks · notes
```

### Assembly

`SkeletonAssembler.assemble()` loads fragments from `harness/templates/skeleton/<id>.md`, replaces `{{section_number}}` placeholders with 1-based indices, and joins them into the final `docs/skeleton.md`.

### Contract power

Two gates use the skeleton directly:

1. **`harness integrity`** — parses the ```filesystem block in `skeleton.md` and asserts every declared path exists. Also detects placeholder leakage (`<pkg>`, `<cmd_a>`, …).
2. **`contract-validator` security hook** — checks every `@router.*("/path")` in agent output against the endpoints declared in `interface.http`. Extra endpoints → BLOCK.

---

## 4. State machine

`PlanManager` drives `docs/harness-plan.md` through eight states:

```
init → designed → planned → building → built → verified → reviewed → shipped
```

Rules:
- Forward only. Backward transitions require an explicit `backup()` call.
- No skipping (`init → planned` is rejected).
- Idempotent same-state transitions are allowed.

The plan file has a YAML frontmatter (profiles, skeleton sections, pipeline step, verify_history, backups) and a markdown body. One file, git-friendly.

---

## 5. Skill ↔ agent mapping

| Skill | Agent(s) | Model | Role |
|---|---|---|---|
| `/ha-init` | — | Opus | Detect profile, interview user, write plan + empty skeleton |
| `/ha-design` | Architect + Designer | Opus | Fill skeleton sections (up to 3 negotiation rounds) |
| `/ha-plan` | Orchestrator | Opus | Decompose into `tasks.md` with dependency graph |
| `/ha-build` | Backend / Frontend Coder | Sonnet | Implement one task (parallel via `--parallel`) |
| `/ha-verify` | — | Sonnet | Run toolchain + integrity gate + record verify_history |
| `/ha-review` | Reviewer | Opus | Security hooks + LESSONs + ai-slop + test distribution |
| `/ha-deepinit` | — | Opus | Analyze existing codebase → hierarchical AGENTS.md |

Sonnet for mechanical work (build / verify); Opus for judgement (design / plan / review).

---

## 6. Quality gates

### 6.1 Six security hooks (`security_hooks.py`)

Enforced by Orchestra on every agent output:

| Hook | Checks |
|---|---|
| `check_dependency` | Imports outside the profile whitelist |
| `check_command_guard` | `rm -rf`, `curl \| bash`, `eval`, `DROP TABLE`, … |
| `check_secret_filter` | Hardcoded tokens / keys / DB connection strings |
| `check_db_guard` | Raw SQL, f-string SQL, WHERE-less DELETE/UPDATE |
| `check_code_quality` | Bare `except:`, `print` debugging, excessive `# type: ignore` |
| `check_contract_validator` | Endpoints outside the skeleton's `interface.http` |

Profile whitelist is injected via `SecurityHooks.from_profile(profile)`.

### 6.2 ai-slop — the seventh hook (integrates LESSON-018)

`/ha-review` runs 7 regex patterns against the git diff:

| Pattern | Severity |
|---|---|
| Verbose docstring (>200 chars) | WARN |
| Cosmetic try/except (re-raise only) | WARN |
| New TODO/FIXME without issue number | WARN |
| Unused-function prefix (`_unused_`) | WARN |
| Stub `pass` with "later" | BLOCK |
| **Dead constants (LESSON-018)** — tuple/list length ≥ 3 near `max_retries=1|2` | **WARN** |

`_strip_non_code_from_diff` excludes `docs/` and `templates/` to avoid false positives on placeholder examples.

### 6.3 Test distribution (new, A6)

`/ha-review` aggregates per-profile source vs. test files:
- **BLOCK** — source module exists with 0 test files.
- **WARN** — 10× skew (e.g. analyzer 43 tests vs. generator 5).

Python counts `def test_*` via AST; JS/TS counts `describe|it|test` via regex. Monorepos are counted per `profile.path` independently.

### 6.4 Skeleton integrity (new, A5)

`/ha-verify` calls `harness integrity` before running the toolchain:
- Every path in ```filesystem blocks of `skeleton.md` must exist.
- Unreplaced template placeholders (`<pkg>`, `<cmd_a>`, …) are flagged.

---

## 7. LESSONs system

`backend/docs/shared-lessons.md` holds 21 past-mistake patterns (LESSON-001 … LESSON-021). Each profile's `lessons_applied` field declares which apply.

Application mechanisms:
- **Text reference** (default): Reviewer agent receives LESSONs in its prompt and judges accordingly.
- **Auto-detect** (LESSON-018): integrated into the ai-slop regex patterns.
- **Hard gate** (LESSON-021): `/ha-build`'s toolchain gate forces test + lint + type to pass before a task is marked `done`.

LESSONs are added manually by editing `shared-lessons.md` + each profile's `lessons_applied`. Auto-learning (detect repeats → propose a new LESSON) is on the roadmap.

---

## 8. Repo layout

```
<repo>/
  backend/
    agents/               Agent system prompts (CLAUDE.md)
      architect/, designer/, orchestrator/, backend_coder/,
      frontend_coder/, reviewer/, qa/
    agents.yaml           Per-agent runtime (model, timeout, on_timeout)
    docs/
      shared-lessons.md   21 LESSONs
      skeleton.md         (generated at runtime)
      harness-plan.md     (generated at runtime)
    src/
      main.py             FastAPI dashboard (port 3002)
      dashboard/          REST + WebSocket
      orchestrator/
        orchestrate.py          Orchestra + assemble_skeleton_for_profiles
        profile_loader.py       Profile load / inherit / detect
        skeleton_assembler.py   Assembly + find_placeholders
        plan_manager.py         State transitions
        context.py              Section ID map + extract_section_by_id
        runner.py               AgentRunner (timeout / retry)
        security_hooks.py       6 hooks + from_profile
        providers/              Claude CLI / Gemini / local
    tests/                357 pytest tests
      orchestrator/
      dashboard/
      skills/              Regression guards for harness integrity + test distribution

  harness/                Installed to ~/.claude/harness
    bin/harness           CLI (validate + integrity subcommands)
    profiles/             _base + 5 stack profiles + _registry.yaml
    templates/skeleton/   20 section fragments

  skills/                 Installed to ~/.claude/skills/ha-*
    ha-init/, ha-design/, ha-plan/, ha-build/,
    ha-verify/, ha-review/, ha-deepinit/
    _ha_shared/utils.py   Shared utilities (HARNESS_AI_HOME loader)

  install.sh              Unix/WSL single-command install
  install.ps1             Windows PowerShell
  tests/install/          install snapshot test (12 assertions)

  examples/
    python-cli-hello/     Minimal reproducible /ha-init output

  docs/
    ARCHITECTURE.md       This document (English)
    ARCHITECTURE.ko.md    Korean mirror (detailed worklog-style)
    decisions/            5 ADRs
    benchmarks/           latency + gate coverage + dogfooding
    e2e-reports/          Dogfooding evidence
    harness-v2-design.md  v2 redesign detailed worklog (Korean)
```

---

## 9. Design decisions (see `docs/decisions/` for full ADRs)

| # | Decision | Rationale | ADR |
|---|---|---|---|
| D1 | Shared schemas + validation CLI (`harness validate`) | Auto-detect profile schema drift | [001](decisions/001-profile-based-architecture.md) |
| D2 | `~/.claude/harness/` global + `{project}/.claude/harness/` local override | Global rules + project-specific exceptions | [001](decisions/001-profile-based-architecture.md) |
| D3 | `/my-*` fully deleted → `/ha-*` (single cut-over, Phase 4 done) | Two-skill maintenance cost outweighed gradual migration | [005](decisions/005-ha-skills-cut-over.md) |
| D4 | `docs/harness-plan.md` single file + YAML frontmatter state | Human-editable, git-friendly | [003](decisions/003-harness-plan-state-machine.md) |
| D5 | Section IDs (20 standard) instead of numbers | Refactor-safe | [002](decisions/002-skeleton-section-ids.md) |
| D6 | ai-slop as the 7th Reviewer hook | Same enforcement model as the 6 security hooks | [004](decisions/004-ai-slop-as-7th-hook.md) |

---

## 10. Extending it

- **New profile**: one `.md` + registry entry. See [CONTRIBUTING §A](../CONTRIBUTING.md).
- **New LESSON**: append to `shared-lessons.md` + each target profile's `lessons_applied`. See [CONTRIBUTING §B](../CONTRIBUTING.md).
- **New quality gate**: implement in `ha-review/run.py` or `harness/bin/harness`, add unit tests, document in this file §6. See [CONTRIBUTING §C](../CONTRIBUTING.md).
- **New `/ha-*` skill**: new `skills/<name>/SKILL.md` + `run.py` reusing `_ha_shared/utils.py`. See [CONTRIBUTING §D](../CONTRIBUTING.md).

---

## 11. Where to go next

- [`SETUP.md`](../SETUP.md) — end-to-end install + run.
- [`backend/docs/shared-lessons.md`](../backend/docs/shared-lessons.md) — all 21 past-mistake patterns.
- [`docs/benchmarks/`](benchmarks/) — latency + gate coverage + dogfooding traces.
- [`docs/e2e-reports/`](e2e-reports/) — real dogfooding evidence (code-hijack, ui-assistant).
- [`ARCHITECTURE.ko.md`](ARCHITECTURE.ko.md) — Korean version (worklog-style detail on v2 redesign).
