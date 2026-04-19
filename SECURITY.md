# Security Policy

## Supported Versions

HarnessAI is in pre-1.0 development. Only the **latest `main` branch** receives
security updates. Tagged releases (e.g. `v0.1.0`) are snapshots — upgrade to
the latest `main` or the most recent tag to receive fixes.

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Send a detailed report to **juwon123465@gmail.com** with:

1. **Affected component** — file path or subsystem (e.g. `security_hooks.py`,
   `install.sh`, `harness/bin/harness`).
2. **Impact** — what an attacker could achieve (RCE, data leak, privilege
   escalation, denial of service, etc.).
3. **Reproduction steps** — minimal command sequence or code snippet.
4. **Affected versions** — commit SHA or tag.
5. **Suggested fix** (optional but appreciated).

## Response Timeline

- **Acknowledgement**: within 72 hours of report.
- **Initial assessment**: within 7 days — severity classification (critical /
  high / medium / low) and disclosure plan.
- **Fix**: target turnaround depends on severity —
  - Critical (RCE, secret leak): patch within 7 days.
  - High: within 30 days.
  - Medium / low: scheduled for the next minor release.

Reporters are credited in `CHANGELOG.md` unless they request anonymity.

## Scope

HarnessAI is a developer-facing tool that runs locally and invokes LLM CLIs
(`claude`, `gemini`). In-scope issues include:

- Arbitrary code execution via malicious skeleton / profile / agent output
- Secret exfiltration through logs or dashboard
- Shell / SQL / path-traversal injection in subprocess invocation
- Bypass of `SecurityHooks` or `harness integrity` gates that results in
  unauthorized code being committed

Out of scope:

- Vulnerabilities in upstream dependencies (`fastapi`, `uv`, Claude CLI, etc.)
  — report to those projects directly.
- LLM hallucinations or incorrect code output (these are a product concern,
  not a security vulnerability).
- Issues requiring physical access to the developer's machine.

Thank you for helping keep HarnessAI and its users safe.
