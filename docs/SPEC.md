# CLAUDE.md — Louisville Jain Sangh Paryushan WhatsApp Agent

## Project Overview
A custom-built, bilingual (English/Gujarati) WhatsApp agent for Louisville Jain
Sangh, delivering uniform content to all users during the 8-day Paryushan
period, September 8–15, 2026, ending at Samvatsari. Combines community
broadcasts with personal features, plus an admin dashboard.

- **Messaging:** Twilio WhatsApp API
- **Language/stack:** Python
- **Languages supported:** English + Gujarati, chosen by user at onboarding
- **Content:** Uniform for all users (no sect-based branching)
- **Data visibility:** Personal logs (fasting, reflections) are visible to
  Sangh admins in the dashboard — disclosed to users at onboarding, not
  presented as fully private

## Chat Architecture
- **1:1 direct messages with the agent** for all core and personal features
  (onboarding, fasting log, reflections, escalations). Do not build group
  chat functionality for these — a group is visible to all members, which
  conflicts with personal features even with the admin-visibility
  disclosure.
- **Whatsapp messages to Louisville Sangh Group:** the WhatsApp Business
  API has no way to post directly into a group chat, so the daily
  broadcast splits into two sends: **Individual** (personalized, to every
  opted-in user — includes what they/their family logged) and **Group**
  (community-only content, no individual detail) sent to whichever
  user(s) are flagged as the group relay in the admin dashboard, who
  manually forward it into the real Sangh WhatsApp group.

## Onboarding Flow
1. Greeting
2. Language choice: English / ગુજરાતી
3. Broadcast opt-in + name, combined in one message/reply (e.g. "YES
   Bhavesh Shah" / "NO Bhavesh Shah"): daily updates (timings,
   announcements) are a low-stakes preference, and a name is needed
   either way — everyone provides one, used to identify them (as the
   head of their household) in the admin dashboard, and in the
   recognition list if opted in below. Kept as one step to save a round
   trip; NOT merged with personal features or recognition below, since
   those carry their own distinct consent disclosures
4. Personal features opt-in: fasting log, private reflections — with the
   disclosure that Sangh admins may view these
5. Public recognition opt-in (separate, optional): share your name in the
   daily group announcement of who fasted the previous day — off by
   default, distinct from the admin-visibility opt-in above
6. Family members (only if personal features are on): name any family
   members (young children, elders) they'll be logging fasts or vows for
   — comma-separated names, or none. Creates their `Dependent` rows
   up front rather than lazily on first log
7. Explicit "Onboarding complete!" confirmation, closing the flow

## Daily Loop (during the festival)
- Morning broadcast, split into two sends (see Chat Architecture above):
  - **Individual** (per user, personalized): day number, theme, local
    Pratikraman timing, announcements, the public recognition list (if
    any), what the user and their family logged the previous day, and
    their daily vow if opted in
  - **Group** (to relay-flagged user(s) only): the same community content
    minus the individual-detail sections, meant for manual reposting
- Free-form replies anytime within the 24h window:
  - Log a fast (type + optional note) — for yourself or a family member
    (young child, elder, etc.) who doesn't message the bot directly
  - Add a private reflection — for yourself or a family member
  - Ask a question (routed to FAQ match or escalation)
  - Opt in/out of a daily Jain-principle vow (admin-approved pool; never
    repeats for the same person while unused approved vows remain)
- Optional evening nudge to log fast/reflection

## Escalation Flow (Q&A the bot can't answer)
1. User asks an unrecognized question
2. Bot immediately acknowledges: "Great question — let me check with the
   Sangh and get back to you soon" (bilingual)
3. Logged to `escalations` table (pending)
4. Admin sees it in the dashboard Inbox tab, replies
5. Reply sent to user via Twilio
6. Admin can flag "Add to FAQ" → stored for the bot to reuse automatically

Scope is the 8-day Paryushan period, ending at Samvatsari. Do not add

## Voice Message Support
- WhatsApp voice notes are `.ogg` files with the OPUS codec; Twilio
  receives these as media on inbound messages and any bot-sent voice
  reply must be encoded the same way to display as a proper voice note.
- **Speech-to-text:** Google Cloud Speech-to-Text — Gujarati and English.
- **Text-to-speech:** Google Cloud TTS — Gujarati and English voices;
  generate reply audio, convert to OPUS/ogg via `ffmpeg`, send as a media
  attachment.
- **Both voice-in and voice-out ship together** — not phased.

## Data Model

```
users
  id, phone, language (en/gu), broadcast_opt_in, personal_opt_in,
  public_recognition_optin, vow_opt_in, is_group_relay (admin-assigned:
  receives the separate Group broadcast to manually relay), onboarding_step,
  timezone

dependents
  id, guardian_id, name — a family member (young child, elder, etc.) who
  doesn't message the bot directly; their guardian logs on their behalf.
  Recognition visibility follows the guardian's own opt-in, since a
  dependent can't consent for themselves.

fasting_logs
  id, user_id, dependent_id (nullable — set when logged for a family
  member instead of the user), date, fast_type, note

reflections
  id, user_id, dependent_id (nullable, same as above), date, text

vows
  id, text_en, text_gu, approved (bool) — candidate Jain-principle daily
  vows; nothing is sent to a user until an admin approves it

vow_assignments
  id, user_id, vow_id, date — which vow went to whom on which day, so the
  same vow never repeats for one person while unused approved vows remain

escalations
  id, user_id, question_text, status (pending/answered), answer_text,
  added_to_faq (bool), timestamp

faq
  id, question_en, question_gu, answer_en, answer_gu

broadcasts
  id, date, day_number, individual_message_en, group_message_en,
  message_id, sent_at — English-only free-text drafts per day; Gujarati
  is auto-drafted via Google Translate at send time, not stored
```

## Message Catalog & Translation
English strings live in `message_catalog.json`, keyed by message ID (e.g.
`greeting`, `ask_language`, `escalation_ack`, `daily_broadcast_intro`).
Never hardcode user-facing strings directly in application logic — always
add a new key to the catalog and reference it by ID. Dynamic values (day
number, theme) are injected via simple templating, filled in *before*
translation.

Gujarati is generated via the Google Cloud Translation API at send time
(cached in `translation_cache` so repeated strings are only translated
once) rather than hand-written per catalog entry — this applies broadly,
including admin-authored ad-hoc content (custom group messages, vow
candidates): admins write English, Gujarati is auto-drafted.

## Admin Dashboard

| Tab | Purpose |
|---|---|
| **Inbox** | Unanswered/escalated questions, reply box, "Add to FAQ" flag |
| **Content** | Edit daily broadcasts, Sangh directions/logistics, FAQ entries, and the daily-vow pool (admin approval required before a vow goes to any user) |
| **Users** | List of users (language, opt-ins); toggle who's flagged as the group relay; drill into individual fasting logs, reflections, and logged-for family members |
| **Broadcast** | Preview and trigger/schedule the next daily Individual + Group messages; also send a one-off custom message to whoever is flagged as the group relay |

- Auth-gated with a single shared admin login (no per-admin accounts)
- No public route should ever expose user data

## Security & Logging Rules
- Twilio credentials via environment variables only — never hardcode or
  commit credentials
- Webhook must validate Twilio request signatures
- Application/server logs record event types and hashed phone numbers —
  never log raw message content (reflections, custom group messages)
- Basic per-user rate limiting on the webhook
- The admin dashboard is the *intended* place personal data is visible —
  this is a deliberate design choice, disclosed to users, not a logging
  leak. Don't "fix" this by hiding data from the dashboard.

## Hosting
- **Railway** — Hobby plan. Twilio webhook needs a public HTTPS endpoint,
  which Railway provides automatically on deploy.

## Deployment Stages
- **Stage 1 — Testing (before Sept 8):** Twilio Sandbox for WhatsApp, a
  separate Railway "staging" environment/project pointed at the sandbox
  webhook. Small internal test group only.
- **Stage 2 — Production (Sept 8–15):** Registered WhatsApp sender
  (unverified tier — see below), separate Railway "production"
  environment/project with its own database, pointed at the real Twilio
  number's webhook. Keep staging running in parallel for content testing.

## Meta / WhatsApp Sender Setup
- No full Meta Business Verification — using the unverified Cloud API
  tier (up to 250 unique recipients/24h), which covers this ~80–90 user
  community.
- Register the WhatsApp sender number through Twilio Console (Messaging →
  Senders → WhatsApp Senders) using Twilio's self-signup flow — no
  business documents required at this tier.
- Message templates (daily broadcast, per language) still need Meta
  approval before use outside the 24h reply window.

## Build Order
1. Data model + onboarding state machine → test via Twilio sandbox
2. Bilingual message catalog wired in
3. Daily broadcast cron job
4. Personal features: fasting log, reflections (self or family member), daily vow opt-in
5. Escalation flow (ack → dashboard inbox → admin reply → FAQ save)
6. Admin dashboard: Inbox → Content → Users → Broadcast tabs
7. Security pass: signature validation, rate limiting, log hygiene review

## Testing Checklist
Before moving from staging to production, verify:
1. Onboarding flow in both languages
2. Fasting log + reflection entry
3. Escalation → dashboard reply → user receives it
4. Voice note in AND spoken voice reply out
5. Full daily-broadcast dry run to a small test group