# HarnessAI Example — `python-cli-hello`

**Goal**: show what `/ha-init` produces for a minimal python-cli project,
and how `/ha-design` would fill it in. The artifacts in `docs/` are real
`ProfileLoader` + `SkeletonAssembler` output — you can regenerate them.

## What's in this directory

| Path | Contents |
|---|---|
| `pyproject.toml` | Minimal click-based CLI — triggers the `python-cli` profile |
| `docs/harness-plan.md` | `/ha-init` state file with `current_step: init` |
| `docs/skeleton.md` | Empty skeleton assembled from `python-cli.required` section IDs |

> **Note on section headings.** `docs/skeleton.md` uses Korean section titles
> ("프로젝트 개요", "기술 스택", …) because the default skeleton templates
> ship with Korean `name:` fields and the `SECTION_TITLES` map in
> `backend/src/orchestrator/context.py` matches those titles for extraction.
> Body content can be written in any language. To localize the titles,
> override the fragments under `{project}/.claude/harness/templates/skeleton/<id>.md`.

## Reproduce in 5 minutes

1. Install HarnessAI (from the repo root):
   ```bash
   ./install.sh                     # Windows: .\install.ps1
   export HARNESS_AI_HOME="$(pwd)"
   ```

2. Detect the profile:
   ```bash
   cd examples/python-cli-hello
   python ~/.claude/skills/ha-init/run.py detect "$(pwd)"
   ```
   Expected JSON includes `{"profile": "python-cli", "path": "."}`.

3. In a fresh Claude Code session inside `examples/python-cli-hello/`:
   ```
   /ha-init
   ```
   Expected output matches `docs/harness-plan.md` and `docs/skeleton.md`
   already committed here.

4. Next step:
   ```
   /ha-design
   ```
   Architect + Designer fill skeleton sections. The skeleton's 7 required
   sections (`overview`, `stack`, `errors`, `interface.cli`, `core.logic`,
   `tasks`, `notes`) get populated in-place.

## Why it matters

This example is the smallest possible surface where all of these pieces
work end-to-end:

- Profile detection (`python-cli` via `pyproject.toml` + click dep)
- Skeleton assembly (7 standard section IDs concatenated, numbered 1-7)
- Plan state machine (`init` → `designed` → `planned` → `building` → …)
- `harness integrity` gate (the ```filesystem block in skeleton matches the
  real tree)

If any of the regeneration steps above fails, that's a bug — please open an
issue with the profile ID and the failing output.
