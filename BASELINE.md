# Baseline — 2026-10-13, before CLAUDE.md / settings / hooks

Environment: macOS, Python 3.11, uv, Claude Code v2.1.287  ← fill from `claude --version`

Scope: root `tests/` only. `paryushan-brain/` has its own tests and evals; out of scope for this lab.

| Metric | Value | Command / note |
|---|---|---|
| Tests | 111 passed, 3 warnings | `uv run pytest tests/ -q` |
| Runtime, working copy (warm) | 6.80s pytest / 7.64s wall | `time uv run pytest tests/ -q --durations=5` |
| CPU vs wall | user+sys ≈ 3.0s of 7.6s → ~60% of runtime is waiting | from `time` |
| Slowest 5 tests | 3.74s of 6.80s (55%): 3 broadcast tests (test_admin), 2 onboarding language tests | `--durations=5` |
| Runtime, fresh clone (no .env) | 4.31s | same command in /tmp/fresh-clone |
| Fresh clone → green | 15.0s total, cold uv cache, first try | clone + `uv sync` + pytest |
| Manual steps not in README | none | |
| Coverage (source only) | TODO — 96% reported total includes test files | `--cov=app --cov=paryushan-brain/brain` |
| Lowest covered | app/twilio_client.py 53% (send path only mocked), brain/agent.py 80% | partial view; full table TODO |
| Warnings | 3 deprecations, all from dependencies (starlette/httpx, opentelemetry, ADK BaseAgentConfig) | |
| PR review time | skipped — no PR history | |

## Open questions (candidate tasks for step 3)
- Tests are ~2.5s faster without a local `.env` → some tests likely read live config or make network calls. To confirm: `--durations=5` in the fresh clone.
- Slow broadcast tests: possible unpatched sleep/retry.