# Louisville Sangh Paryushan Agent

A bilingual (English/Gujarati) WhatsApp agent for Louisville Jain Sangh,
delivering daily broadcasts and personal features (fasting log,
reflections) during the 8-day Paryushan period, September 8-15, 2026. See
[CLAUDE.md](CLAUDE.md) for the full product spec.

## Status

**Build Order steps 1-6 complete.** Steps 1-5 verified end-to-end against
the real Twilio WhatsApp Sandbox: data model, onboarding state machine,
bilingual message catalog, the daily broadcast job, personal features
(fasting log, reflections, forgiveness list), and the ADK agent for
free-form routing and escalation, including one real eval loop (see
below). Step 6 (admin dashboard) is built and tested (pytest + a manual
browser pass); not yet used by a real admin day-to-day. Voice support and
the security pass (rate limiting) are not yet built.

### Admin dashboard (step 6)

Server-rendered (Jinja2, no frontend framework) at `/admin`, gated by
HTTP Basic auth against `ADMIN_USERNAME`/`ADMIN_PASSWORD` — a single
shared login, per CLAUDE.md (no per-admin accounts). If either is unset,
`/admin/*` returns 503 rather than being silently open.

- **Inbox** — pending escalations with a reply box (sends via Twilio,
  marks answered); answered ones get an "Add to FAQ" action that opens a
  bilingual form pre-filled from the original question/answer.
- **Content** — daily broadcasts and FAQ entries, both bilingual
  side-by-side; add or edit either (broadcasts upsert by date).
- **Users** — list with opt-in flags; drill into one user's fasting logs
  and reflections (per CLAUDE.md, this personal data being visible here
  to admins is a deliberate disclosed design choice, not a leak).
- **Broadcast** — today's content previewed in both languages, with a
  "Send now" button that calls the same `send_daily_broadcast` the
  Railway cron job uses.

See [`app/admin/`](app/admin/) (routes + auth) and
[`app/templates/admin/`](app/templates/admin/).

### Personal features & free-form routing (steps 4-5)

Once onboarding is complete, a message is routed one of two ways:

- **`ANTHROPIC_API_KEY` set** → the [`paryushan-brain`](paryushan-brain/)
  ADK agent handles it: free-form natural language for logging a fast,
  saving a reflection, adding to the forgiveness list, answering from the
  FAQ, or escalating an unrecognized question to a Sangh admin. This
  matches CLAUDE.md's "free-form replies anytime" wording. Runs on Claude
  via LiteLLM (not Gemini — see the eval loop section below for why).
- **`ANTHROPIC_API_KEY` unset** (default) → falls back to a deterministic
  numbered menu (reply 1/2/3, or MENU): log a fast (type + optional note),
  add a reflection, or add to the forgiveness list — no LLM involved. This
  is also the automatic fallback if the agent call errors or times out
  (10s budget — see `app/agent_runtime.py` — Twilio's own webhook timeout
  is ~15s).

Both paths respect `personal_opt_in` — opted-out users get a notice
instead. See [`paryushan-brain/brain/agent.py`](paryushan-brain/brain/agent.py)
for the agent's tools/instruction and
[`app/agent_runtime.py`](app/agent_runtime.py) for how it's wired into
this webhook's own process (single Railway service — see Architecture
below).

## Stack

- Python 3.11+, managed with [uv](https://docs.astral.sh/uv/) as a
  [workspace](pyproject.toml) (this project + `paryushan-brain`)
- FastAPI (Twilio webhook) + SQLAlchemy (SQLite for Stage 1 testing)
- Twilio WhatsApp API
- Google ADK (`paryushan-brain/`) for free-form message routing, Claude via
  LiteLLM (not Vertex AI — no GCP project needed for Stage 1)

## Architecture: why one process, not two

`agents-cli scaffold` normally produces a standalone, separately-deployed
agent service (its own FastAPI server + Dockerfile, called over HTTP/A2A).
We deliberately don't run it that way: CLAUDE.md commits to a single
Railway Hobby-plan service, and a second service would add hosting cost
and per-message network latency for a ~80-90 user community bot with no
other consumers of the agent.

Instead, `paryushan-brain` is a uv workspace member, installed editable
into this project's own environment (see `[tool.uv.workspace]` in
[pyproject.toml](pyproject.toml)). `app/agent_runtime.py` imports its
`root_agent` directly and drives it with an in-process ADK `Runner` — one
Python process, one Railway service. The tradeoff: `paryushan-brain`'s
tools ([`brain/data.py`](paryushan-brain/brain/data.py)) can't import this
project's `app` package (that would break `agents-cli playground`/`eval`,
which run it standalone in its own venv), so they talk to the same SQLite
file directly via `DATABASE_URL` instead — a small, deliberate duplication
of a handful of table writes, not business logic.

## Setup

```bash
uv sync
cp .env.example .env
```

Fill in `.env`:
- `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` — from the Twilio Console
- `TWILIO_WHATSAPP_NUMBER` — defaults to the shared Sandbox number `whatsapp:+14155238886`
- `SANGH_GROUP_WHATSAPP_NUMBER` — the existing Sangh WhatsApp group's number, if you want the daily broadcast to also post there
- Leave `SKIP_TWILIO_SIGNATURE_VALIDATION=false` except for local testing without a real Twilio account
- `ANTHROPIC_API_KEY` — optional. Get a key at https://console.anthropic.com/settings/keys to enable the free-form ADK agent (step 5); leave blank to use the deterministic menu only. If your key is identity-linked rather than workspace-scoped, also set `ANTHROPIC_WORKSPACE_ID` (Anthropic's API will tell you via a "workspace-id required" error if so)

Create the database tables:

```bash
uv run python -m scripts.init_db
```

> Run scripts with `-m` (e.g. `python -m scripts.init_db`) from the repo
> root, not `python scripts/init_db.py` — that form puts `scripts/` on
> `sys.path` instead of the repo root, so `app` won't be importable.

## Running locally

```bash
uv run uvicorn app.main:app --reload
```

The webhook is served at `POST /webhook/twilio`; health check at `GET /healthz`.

### Testing against the Twilio Sandbox

1. Join the Twilio WhatsApp Sandbox from your phone (Console → Messaging → Try it out → Send a WhatsApp message).
2. Expose your local server publicly, e.g. `ngrok http 8000`.
3. In the Twilio Console, set the Sandbox's "When a message comes in" webhook to `https://<your-ngrok-domain>/webhook/twilio` (HTTP POST).
4. Message the Sandbox number from WhatsApp — you should get the greeting and language prompt, then can walk through onboarding.

## Seeding a day's broadcast content

The admin dashboard's Content tab (Build Order step 6) doesn't exist yet.
Until then, seed a day's broadcast manually:

```bash
uv run python -m scripts.seed_broadcast \
  --date 2026-09-08 --day-number 1 \
  --theme-en "Compassion" --theme-gu "કરુણા" \
  --pratikraman-timing "7:00 PM" \
  --announcements-en "Please arrive 15 min early." \
  --announcements-gu "કૃપા કરી 15 મિનિટ વહેલા આવો."
```

Then send it (this is what the Railway cron job runs daily in production):

```bash
uv run python -m scripts.run_daily_broadcast
```

It sends to every user with `broadcast_opt_in=true`, in their chosen
language, plus the Sangh group number if configured. It's a no-op (logs a
warning) if no broadcast content has been seeded for the current date.

## Tests

```bash
uv run pytest
```

## Testing the ADK agent standalone

From within `paryushan-brain/` (its own venv, but shares the workspace
lockfile), with `ANTHROPIC_API_KEY` (and `ANTHROPIC_WORKSPACE_ID` if your
key is identity-linked rather than workspace-scoped) set in
`paryushan-brain/.env`:

```bash
cd paryushan-brain
agents-cli playground   # interactive chat with the agent
```

Note: `paryushan-brain/tests/eval/datasets/basic-dataset.json` and
`tests/integration/test_server_e2e.py` are still scaffold placeholders
(weather-agent examples, standalone-server checks) — not yet updated for
our actual agent's tools. `tests/integration/test_agent.py` was updated to
seed the session state our instruction needs, but still requires a real
API key to run, which is why it's excluded from the root project's
`uv run pytest` (see `testpaths` in [pyproject.toml](pyproject.toml)).

### Eval loop and the dietary/ritual fabrication fix

Live testing against the Twilio Sandbox found a real bug: asked "I
probably ate some green beans" (implicitly, whether that broke a fast),
the agent confidently said "should be fine" instead of escalating — a
direct miss of the "never fabricate, escalate for religious/ritual
questions" instruction. This was fixed through an eval loop:

- **`agents-cli eval generate` doesn't work in this environment.** It
  constructs a `vertexai.Client` internally for tracing infra, regardless
  of the agent's own model provider, which needs working Google Cloud ADC.
  The local `gcloud` CLI install is independently broken (fails the same
  way under both Python 3.11 and 3.14 — a corrupted/stale SDK install, not
  a version issue), so this path isn't available.
- **Workaround:** [`paryushan-brain/tests/eval/run_local_eval.py`](paryushan-brain/tests/eval/run_local_eval.py)
  — a standalone script that runs the real dataset
  ([`tests/eval/datasets/basic-dataset.json`](paryushan-brain/tests/eval/datasets/basic-dataset.json))
  against the live agent and scores it with the same logic as
  [`tests/eval/metrics.py`](paryushan-brain/tests/eval/metrics.py) (an
  LLM-as-judge using Claude, not Gemini/Vertex — no GCP dependency) plus a
  deterministic check
  ([`tests/eval/eval_config.yaml`](paryushan-brain/tests/eval/eval_config.yaml))
  that specific cases must trigger `escalate()`. Run it from the repo root
  with `ANTHROPIC_API_KEY` set: `uv run python paryushan-brain/tests/eval/run_local_eval.py`
  (needs `DATABASE_URL` pointed at a SQLite file with tables created via
  `scripts.init_db` first, since the agent's tools write to it).
- **3 iterations, tracked in git history on [`brain/agent.py`](paryushan-brain/brain/agent.py):**
  a HARD RULE added for dietary/ritual questions fixed the original bug,
  confirmed stable across two clean reruns. A second rule (escalate
  whenever the reply promises admin follow-up) closed a related gap where
  the agent told users to "contact an admin" without actually logging an
  escalation.
- **Known remaining issue, accepted as low-severity:** for one case, the
  model now asks "should I let them know?" before escalating rather than
  escalating immediately — reasonable conversational UX, but means the
  escalation only lands after a confirmation turn a single-turn eval case
  can't exercise. Not a fabrication/safety issue like the original bug;
  deliberately not chased further (see the eval skill's guidance on
  diminishing returns per case).
- `tests/integration/test_server_e2e.py` and `tests/unit/test_dummy.py`
  are still scaffold placeholders — not part of this project's real
  coverage.

## Not yet built (see CLAUDE.md Build Order)

5. Escalation flow is built, live-tested, and has been through one real
   eval loop (see above) — the critical dietary-fabrication bug is fixed;
   the minor confirm-before-escalate wrinkle noted above is accepted for
   now. Formal eval via `agents-cli eval` itself remains blocked on the
   broken local `gcloud` install (a system-level fix someone would need to
   run separately)
7. Security pass: webhook rate limiting (signature validation and
   hashed-phone logging are already in place)

Voice message support (Google Cloud Speech-to-Text / TTS) and Railway
deployment are also outstanding.
