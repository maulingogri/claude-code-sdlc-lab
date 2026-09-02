# Louisville Sangh Paryushan Agent

A bilingual (English/Gujarati) WhatsApp agent for Louisville Jain Sangh,
delivering daily broadcasts and personal features (fasting log,
reflections) during the 8-day Paryushan period, September 8-15, 2026. See
[CLAUDE.md](CLAUDE.md) for the full product spec.

## Status

**Build Order steps 1-6 complete.** Steps 1-5 verified end-to-end against
the real Twilio WhatsApp Sandbox: data model, onboarding state machine,
message catalog + Google Translate, the daily broadcast job, personal
features (fasting log, reflections, family-member logging, daily vow),
and the ADK agent for free-form routing and escalation, including one
real eval loop (see below). Step 6 (admin dashboard) is built and
live-tested end-to-end, including a real admin escalation reply and a
real daily broadcast send via Twilio (see "Twilio Trust Hub" below).
Step 7's security pass is complete — signature validation, hashed-phone
logging, and per-user webhook rate limiting are all in place. Voice
support is not yet built.

**Post-launch feature changes:** the events RSVP/volunteering feature and
the forgiveness-list feature were both removed as out of scope; in their
place, three features were added — logging a fast/reflection on behalf of
a family member who doesn't have their own WhatsApp account (a young
child or elder), an opt-in daily Jain-principle vow (admin-approved pool,
bundled into the daily broadcast, never repeats for the same user until
the pool is exhausted), and a custom-message tool in the admin Broadcast
tab for one-off posts to the Sangh WhatsApp group. The hand-curated
bilingual message catalog was also replaced with the Google Cloud
Translation API — see "Google Translate migration" below.

**Broadcast further split into Individual + Group:** the WhatsApp
Business API has no way to post directly into a group chat, so
`SANGH_GROUP_WHATSAPP_NUMBER` (a blind env-var phone number) was replaced
with `User.is_group_relay` — an admin-assignable flag on the Users tab.
The daily broadcast now sends two distinct messages: **Individual**
(personalized, to every opted-in user — today's community content plus
what they/their family logged the previous day, plus their vow) and
**Group** (community content only, no individual detail) sent to
whichever user(s) are flagged as the relay, who forward it into the real
group by hand. The admin's one-off custom group message follows the same
relay-recipient list.

**Flow simplification pass:** onboarding's broadcast opt-in and name
collection were merged into one message/reply ("YES Bhavesh Shah" / "NO
Bhavesh Shah") — a low-stakes preference paired with something needed
either way — cutting one round trip without touching the two steps that
carry real consent disclosures (personal features, public recognition),
which stay separate. The WhatsApp menu's "log for a family member" option
was folded into the fast/reflection flows themselves (each now asks "who
is this for?" right after), removing a menu option and a layer of
sub-menu navigation. The admin Content tab's broadcast forms no longer
ask for a day number — it's derived from the date, removing a field that
could silently drift between the Individual and Group forms for the same
day.

**Also been through a full code-review pass** (10 confirmed findings, all
fixed — privacy-consent enforcement, a timezone bug, blocking I/O on the
event loop, a duplicate-send risk, an unhandled crash on a webhook race,
message-catalog compliance, a silent-failure broadcast bug, a schema-drift
test gap, missing timeout logging, and a stale-conversation data-integrity
bug). 15 new regression tests came out of it — see the inline comments
at each fix site (`app/main.py`, `app/agent_runtime.py`,
`app/admin/routes.py`, `app/broadcast.py`, `app/personal_features.py`,
`paryushan-brain/brain/agent.py`, `paryushan-brain/brain/data.py`) for
the reasoning behind each.

### Admin dashboard (step 6)

Server-rendered (Jinja2, no frontend framework) at `/admin`, gated by
HTTP Basic auth against `ADMIN_USERNAME`/`ADMIN_PASSWORD` — a single
shared login, per CLAUDE.md (no per-admin accounts). If either is unset,
`/admin/*` returns 503 rather than being silently open.

- **Inbox** — pending escalations with a reply box (sends via Twilio,
  marks answered); answered ones get an "Add to FAQ" action that opens a
  bilingual form pre-filled from the original question/answer.
- **Content** — daily broadcasts and FAQ entries, both bilingual
  side-by-side (broadcasts upsert by date); also a daily-vow queue —
  admins add an English candidate vow (auto-translated), then approve or
  delete it from the pending list before it can ever be assigned to a
  user.
- **Users** — list with opt-in flags and a toggle for the group-relay
  role (`is_group_relay` — who receives the Group broadcast to manually
  forward into the real Sangh WhatsApp group); drill into one user's
  fasting logs and reflections, plus any family members they've logged
  on behalf of and those members' own logs (per CLAUDE.md, this personal
  data being visible here to admins is a deliberate disclosed design
  choice, not a leak).
- **Broadcast** — today's content previewed in both languages, with a
  "Send now" button that calls the same `send_daily_broadcast` the
  Railway cron job uses (sends the personalized Individual message to
  every opted-in user, and the community-only Group message to whoever
  is flagged as the relay), plus a form to send a one-off custom message
  (English, auto-translated) to the current relay recipient(s) immediately.

See [`app/admin/`](app/admin/) (routes + auth) and
[`app/templates/admin/`](app/templates/admin/).

### Personal features & free-form routing (steps 4-5)

Once onboarding is complete, a message is routed one of two ways:

- **`ANTHROPIC_API_KEY` set** → the [`paryushan-brain`](paryushan-brain/)
  ADK agent handles it: free-form natural language for logging a fast or
  reflection (for the user or, by name, a family member), toggling the
  daily vow on/off, answering from the FAQ, or escalating an unrecognized
  question to a Sangh admin. This matches CLAUDE.md's "free-form replies
  anytime" wording. Runs on Claude via LiteLLM (not Gemini — see the eval
  loop section below for why).
- **`ANTHROPIC_API_KEY` unset** (default) → falls back to a deterministic
  numbered menu (reply 1/2/3, or MENU): log a fast (type + optional note),
  add a reflection, or toggle the daily vow — no LLM involved. Both
  logging flows ask "who is this for?" right after (reply YOU, or a
  family member's name, reused thereafter) rather than routing family
  logging through a separate menu option. This is also the automatic
  fallback if the agent call errors or times out (10s budget — see
  `app/agent_runtime.py` — Twilio's own webhook timeout is ~15s).

Both paths gate fast/reflection/family-member logging behind
`personal_opt_in` — opted-out users get a notice instead — but the menu
itself and the vow toggle work regardless, since the vow isn't the same
kind of personal data. See [`paryushan-brain/brain/agent.py`](paryushan-brain/brain/agent.py)
for the agent's tools/instruction and
[`app/agent_runtime.py`](app/agent_runtime.py) for how it's wired into
this webhook's own process (single Railway service — see Architecture
below).

### Google Translate migration

The earlier hand-curated bilingual message catalog (English + Gujarati
strings side by side in `message_catalog.json`) has been replaced:
callers now author English only, and [`app/translation.py`](app/translation.py)
translates to Gujarati on demand via the Google Cloud Translation API
(v2, simple API-key auth — no GCP ADC/service account needed), caching
every result in a `translation_cache` DB table so identical strings are
only ever translated once. Leave `GOOGLE_TRANSLATE_API_KEY` blank to fall
back to English-unchanged for Gujarati users (never a broken message, a
worse one). `paryushan-brain/brain/data.py` — which deliberately doesn't
import the root `app` package (see Architecture above) — has its own
stdlib-only (`urllib`) copy of this function that shares the same cache
table, so the ADK agent's escalation acknowledgment and the deterministic
menu's messages always agree.

### Daily vow feature

Users can opt in (menu option 3, or "toggle the vow" via the agent) to
receive one Jain-principle vow each morning, appended to their daily
broadcast. Candidate vows are admin-gated: [`scripts/seed_vows.py`](scripts/seed_vows.py)
seeds ~25 starter English vows (auto-translated), all unapproved by
default — an admin must approve each one in the Content tab before it can
ever be assigned. [`app/broadcast.py`](app/broadcast.py)'s
`_pick_vow_for_user` picks a random *approved* vow the user hasn't
received before (tracked via `VowAssignment`), only allowing a repeat
once the whole approved pool has been exhausted for that user.

```bash
uv run python scripts/seed_vows.py
```

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
- Leave `SKIP_TWILIO_SIGNATURE_VALIDATION=false` except for local testing without a real Twilio account
- `ANTHROPIC_API_KEY` — optional. Get a key at https://console.anthropic.com/settings/keys to enable the free-form ADK agent (step 5); leave blank to use the deterministic menu only. If your key is identity-linked rather than workspace-scoped, also set `ANTHROPIC_WORKSPACE_ID` (Anthropic's API will tell you via a "workspace-id required" error if so)
- `GOOGLE_TRANSLATE_API_KEY` — optional. Create a GCP project, enable the Cloud Translation API, then create an API key under Credentials; leave blank to have all Gujarati messages fall back to English untranslated (see "Google Translate migration" above)

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

## Seeding broadcast content

The admin dashboard's Content tab has two sections — Daily individual
broadcast message and Daily group broadcast messages (one row per
Paryushan day, English only; Gujarati is auto-drafted via Google
Translate at send time) — each editable directly there. To avoid starting
from a blank form for all 16 messages, seed a draft set for all 8 days:

```bash
uv run python -m scripts.seed_paryushan_broadcasts
```

Drafts only — review and edit each one (Pratikraman timing especially,
which is seeded as an explicit placeholder) before relying on them.
Safe to re-run: skips any date that already has content, so it won't
clobber edits already made.

Then send today's (this is what the Railway cron job runs daily in production):

```bash
uv run python -m scripts.run_daily_broadcast
```

It sends the personalized Individual message to every user with
`broadcast_opt_in=true`, in their chosen language, plus the community-only
Group message to whoever is flagged `is_group_relay` on the Users tab.
It's a no-op (logs a warning) if no broadcast content has been seeded for
the current date.

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

- **`agents-cli eval generate` originally didn't work in this
  environment.** It constructs a `vertexai.Client` internally for tracing
  infra, regardless of the agent's own model provider, which needs
  working Google Cloud ADC — blocked at the time by a broken local
  `gcloud` install. **Fixed**: reinstalled `gcloud`, ran `gcloud auth
  login` and `gcloud auth application-default login` (both need a real
  interactive browser session — not something an agent can do
  unattended), and set a quota project the account actually has access
  to. `agents-cli eval generate` + `eval grade` now run for real — see
  the results below. `paryushan-brain/.env` needs its own `DATABASE_URL`
  (kept separate from the root project's `paryushan.db` so eval runs
  don't write into real dev data) — schema initialized once via
  `DATABASE_URL="sqlite:///$(pwd)/paryushan-brain/paryushan.db" uv run
  python -m scripts.init_db` from the repo root.
- **Standalone fallback still available:** [`paryushan-brain/tests/eval/run_local_eval.py`](paryushan-brain/tests/eval/run_local_eval.py)
  — runs the same dataset
  ([`tests/eval/datasets/basic-dataset.json`](paryushan-brain/tests/eval/datasets/basic-dataset.json))
  against the live agent with the same scoring logic as
  [`tests/eval/metrics.py`](paryushan-brain/tests/eval/metrics.py) (an
  LLM-as-judge using Claude, not Gemini/Vertex) plus the deterministic
  `escalate()` check
  ([`tests/eval/eval_config.yaml`](paryushan-brain/tests/eval/eval_config.yaml),
  duplicated by hand — keep both in sync). Useful for a quick check with
  no GCP/ADC dependency at all; the real `agents-cli eval` path above is
  now the primary one. Run from the repo root with `ANTHROPIC_API_KEY`
  set: `uv run python paryushan-brain/tests/eval/run_local_eval.py`.
- **Latest full run (all 7 cases, `agents-cli eval generate` + `eval
  grade`):** `custom_response_quality` mean 4.86/5 (stdev 0.38),
  `escalation_used_when_expected` mean 1.0/1.0 — every case expected to
  escalate did.
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

## Twilio Trust Hub / compliance KYC — resolved

Live testing (2026-09-02) found that sending a message **proactively**
via the REST API (`Client.messages.create()`, used by both
`app/twilio_client.py:send_whatsapp_message` — so both the admin Inbox's
reply feature and `send_daily_broadcast`) failed with a 401 ("Primary
compliance profile is not approved... complete the KYC process in Trust
Hub"). This was an **account-level Twilio restriction**, not a code bug —
it didn't affect replies returned as TwiML directly in the webhook
response (onboarding, the ADK agent's own replies), which is why prior
WhatsApp testing had worked fine; it only blocked admin-initiated and
cron-triggered outbound sends. The error handling behaved correctly
around it (escalations stayed `pending`, nothing left in a bad state,
failures logged).

**Resolved same day**: an individual Trust Hub profile was approved.
Retested both paths live — admin Inbox reply (`Response Status Code: 201`,
real message SID, escalation correctly marked `answered`) and a real
daily broadcast send (`sent=1 failed=0`, `Broadcast.sent_at` correctly
stamped) — both now work end-to-end.

## Not yet built (see CLAUDE.md Build Order)

Escalation flow is built, live-tested, and has been through one real
eval loop (see above) — the critical dietary-fabrication bug is fixed;
the minor confirm-before-escalate wrinkle noted above is accepted for
now. Formal eval via `agents-cli eval` was blocked on a broken local
`gcloud` install — now fixed (see "Eval loop" above); the real
`generate`/`grade` pipeline runs cleanly.

Step 7 (security pass) is complete: signature validation, hashed-phone
logging, and per-user webhook rate limiting
([`app/rate_limit.py`](app/rate_limit.py) — in-memory sliding window, 15
messages/60s per phone number, silently drops over-limit messages rather
than replying to every one) are all in place.

Voice message support (Google Cloud Speech-to-Text / TTS) and Railway
deployment are the remaining outstanding items.
