# Baseline — 2026-10-13, Claude Code vX.Y.Z, before CLAUDE.md/settings/hooks

| Slowest 5 tests | 3.74s of 6.80s (55%) — 3 broadcast (test_admin), 2 onboarding language tests | `--durations=5` |
| Open question | Suspected unpatched sleep/retry or live translate call — candidate task for step 3 | |

| Coverage (source only) | __% (app + brain; tests excluded) | `--cov=app --cov=paryushan-brain/brain` |
| Lowest covered | app/twilio_client.py 53% (send path mocked), brain/agent.py 80%, + __ | |

| Fresh clone → green | 15.0s, cold uv cache, first try | clone + `uv sync` + pytest |
| Manual steps not in README | none | |
| Test runtime, fresh clone (no .env) | 4.31s vs 6.80s in working copy | → tests likely reading local .env; step 3 candidate |
| Coverage (source only) | TODO — rerun with --cov=app | |
| PR review time | skipped — no PR history | |

PR review time: skipped — no PR history