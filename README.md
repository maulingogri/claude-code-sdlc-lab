# Louisville Sangh Paryushan Agent

A bilingual (English/Gujarati) WhatsApp agent for Louisville Jain Sangh,
delivering daily broadcasts and personal features (fasting log,
reflections) during the 8-day Paryushan period, September 8-15, 2026. See
[CLAUDE.md](CLAUDE.md) for the full product spec.

## Status

**Build Order steps 1-4 complete and verified end-to-end against the real
Twilio WhatsApp Sandbox:** data model, onboarding state machine, bilingual
message catalog, the daily broadcast job, and personal features (fasting
log, reflections, forgiveness list). **Step 5 (escalation + free-form
routing) is built but not yet live-tested** — it needs a Gemini API key
(see below). Admin dashboard, voice support, and the security pass (rate
limiting) are not yet built.

### Personal features & free-form routing (steps 4-5)

Once onboarding is complete, a message is routed one of two ways:

- **`GEMINI_API_KEY` set** → the [`paryushan-brain`](paryushan-brain/)
  ADK agent handles it: free-form natural language for logging a fast,
  saving a reflection, adding to the forgiveness list, answering from the
  FAQ, or escalating an unrecognized question to a Sangh admin. This
  matches CLAUDE.md's "free-form replies anytime" wording.
- **`GEMINI_API_KEY` unset** (default) → falls back to a deterministic
  numbered menu (reply 1/2/3, or MENU): log a fast (type + optional note),
  add a reflection, or add to the forgiveness list — no LLM involved. This
  is also the automatic fallback if the agent call errors at runtime.

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
- Google ADK (`paryushan-brain/`) for free-form message routing, Gemini via
  Google AI Studio (not Vertex AI — no GCP project needed for Stage 1)

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
- `GEMINI_API_KEY` — optional. Get a free key at https://aistudio.google.com/apikey to enable the free-form ADK agent (step 5); leave blank to use the deterministic menu only

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

### Known gap from live testing: dietary/ritual fabrication

Live-tested against the Twilio Sandbox: natural-language fast logging
(with note extraction), reflections, forgiveness list, escalation instead
of guessing on an unanswerable logistics question, opt-out gating, and
graceful handling of a request with no matching tool (asked to "change
language," it escalated rather than fabricating that feature) all worked
as intended. **But** asked "I probably ate some green beans" (implicitly,
whether that broke a fast), the agent confidently said "should be fine"
with no FAQ match and no escalation — a direct miss of the "never
fabricate, always escalate for religious/ritual questions" instruction in
[`brain/agent.py`](paryushan-brain/brain/agent.py). Needs a real eval loop
(`google-agents-cli-eval` — dataset cases covering dietary/ritual
ambiguity, 5-10+ prompt-iteration cycles) before this is trustworthy for
real users; the instruction alone isn't holding reliably.

## Not yet built (see CLAUDE.md Build Order)

5. Escalation flow is built and live-tested (see above), but the
   dietary/ritual fabrication gap above needs a real eval loop before
   production use — `paryushan-brain`'s eval suite is still placeholders
6. Admin dashboard (Inbox / Content / Users / Broadcast tabs) — this is
   also where escalations/FAQ would actually get reviewed and answered;
   right now `escalate` just writes a pending row with no way to see it
7. Security pass: webhook rate limiting (signature validation and
   hashed-phone logging are already in place)

Voice message support (Google Cloud Speech-to-Text / TTS) and Railway
deployment are also outstanding.
