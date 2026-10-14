# Paryushan WhatsApp Agent — Louisville Jain Sangh

WhatsApp bot (Twilio + FastAPI) for the Paryushan festival, English and Gujarati.
Product behavior (onboarding, daily loop, escalation, data model, deployment) is in
`docs/SPEC.md` — read the relevant section before changing any user-facing flow.

## Commands
- Install: `uv sync`
- All tests: `uv run pytest tests/ -q`
- One test: `uv run pytest tests/test_admin.py::<test_name> -q`
- Always go through `uv run`; never bare `pytest` or `pip install`.
- Brain eval (separate): `uv run python paryushan-brain/tests/eval/run_local_eval.py`

## Architecture
- `app/` — webhook and WhatsApp flows. `twilio_client.py` outbound send,
  `translation.py` Google Translate, `rate_limit.py`, `personal_features.py`.
- `paryushan-brain/brain/` — ADK agent (`agent.py`) and data (`data.py`).
  Without `ANTHROPIC_API_KEY` it falls back to a deterministic menu.
- `app/message_catalog.json` — all English user-facing strings, keyed by message ID.

## Conventions
- Never hardcode user-facing strings; add a key to `app/message_catalog.json`.
- Fill templates (day number, theme) before translation, not after.
- Gujarati comes from Google Translate at send time, cached in the `translation_cache` table (`app/models.py`).
- Tests must not depend on the developer's `.env`: patch `settings.*`, delete env vars
  with `monkeypatch`, and mock Twilio, Google Translate and Anthropic.
- Test phone numbers use the fictional +1555 range only.

## Security — do not weaken
- Credentials come from environment variables only; never hardcode or commit them.
- The webhook validates Twilio request signatures; don't remove or bypass this.
- Logs record event types and hashed phone numbers, never raw message content.
- Personal data on the admin dashboard is intentional and disclosed to users.
  Don't "fix" it by hiding data.

## Don't touch
- `.env` — never read or edit.
- `uv.lock` — change only via `uv add` / `uv lock`.