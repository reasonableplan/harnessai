## Summary
<!-- 1–3 bullets on what this PR changes and why. -->

## Type of change
- [ ] Bug fix (non-breaking)
- [ ] New feature (non-breaking)
- [ ] Breaking change
- [ ] New profile / LESSON / gate
- [ ] Documentation only

## Checklist
- [ ] `cd backend && uv run pytest tests/ --rootdir=.` — all pass
- [ ] `uv run ruff check src/ tests/` — 0 errors
- [ ] `uv run pyright src/` — 0 errors
- [ ] `python harness/bin/harness validate` — 0 errors
- [ ] `python scripts/gate_benchmark.py` — all fixtures pass
- [ ] Tests accompany new code (implementation 1 = tests ≥ 1)
- [ ] `./tests/install/test_install_snapshot.sh` — if install/* touched
- [ ] README / ARCHITECTURE updated if user-facing behavior changed
- [ ] CHANGELOG Unreleased entry added

## Related issues
<!-- Closes #NNN -->

## Notes for reviewers
<!-- Anything non-obvious, trade-offs, or areas you want extra scrutiny on. -->
