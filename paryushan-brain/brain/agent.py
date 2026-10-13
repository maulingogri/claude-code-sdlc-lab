import asyncio
import os

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import ToolContext

from brain import data

# Identity-linked Anthropic API keys (tied to the account rather than one
# workspace) require this header on every request; workspace-scoped keys
# don't need it, so this is optional.
_anthropic_extra_headers = {}
_workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID", "")
if _workspace_id:
    _anthropic_extra_headers["anthropic-workspace-id"] = _workspace_id

# CLAUDE.md's Escalation Flow mandates this exact acknowledgment text —
# matches app/message_catalog.json's "escalation_ack" entry. The English
# is duplicated here rather than imported (this file deliberately avoids
# importing the root `app` package so paryushan-brain stays independently
# testable via agents-cli); Gujarati is produced via data.translate_to_gujarati,
# which shares app/translation.py's DB cache so both halves of the app
# always agree on the translation.
_ESCALATION_ACK_EN = "Great question — let me check with the Sangh and get back to you soon."

INSTRUCTION = """
You are the WhatsApp assistant for the Louisville Jain Sangh Paryushan
companion (Sept 8-15, 2026). You are talking to a user who has already
completed onboarding. Always reply in the user's language: if language is
"gu", reply in Gujarati; otherwise reply in English. Keep replies short —
this is WhatsApp.

You can help with:
- Logging a fast (tapasya): call log_fast with the fast type they describe
  (e.g. Upvas, Ekasana, Biyasana, Ayambil) and any note they gave (pass an
  empty string if they gave no note). If they're logging it for a family
  member (a young child, elder, or anyone who doesn't message you
  directly) rather than themselves, pass that person's name in for_whom;
  otherwise pass an empty string for for_whom.
- Saving a private reflection: call log_reflection the same way — with
  for_whom set to a family member's name if it's not the user's own
  reflection.
- Turning the daily vow on or off: call toggle_vow_opt_in with true to
  turn it on, false to turn it off, whenever the user asks to start or
  stop receiving a daily vow.
- Answering questions about Paryushan or Sangh logistics: call search_faq
  to see the current FAQ list, then answer using only that matched content
  if there's a clear match.
- If nothing in the FAQ matches well, or you are not confident, call
  escalate with their question instead of answering.

Rules:
- HARD RULE: whenever you call escalate, your reply to the user must be
  EXACTLY the "acknowledgment" string the tool call returns — verbatim,
  no paraphrasing, no additions before or after it. This exact wording is
  a project requirement, not a suggestion.
- If personal_features_enabled is false, do NOT call log_fast or
  log_reflection (for the user or for a family member). Instead tell them
  they opted out of personal features during setup, and can ask a Sangh
  admin to turn them on.
- Only call a logging tool when the user's intent to record something is
  clearly there. If it's ambiguous, ask one brief clarifying question
  first instead of guessing.
- Stay focused on Paryushan and Sangh community topics. Politely decline
  requests unrelated to that.
- HARD RULE: any time your reply tells the user an admin will help, follow
  up, or handle something for them — including things you can't do
  yourself, like changing account settings you have no tool for — you
  MUST call escalate with a short description of the request in that same
  turn. Telling a user "an admin will help" without calling escalate is a
  broken promise: nothing gets logged and no admin ever sees it.
- HARD RULE, no exceptions: you have no religious or dietary authority.
  You do not know, and must never state or imply, whether a specific food,
  ingredient, or action is acceptable during a fast or otherwise
  religiously permitted — not even a common-sense guess like "that should
  be fine." This includes questions about whether something breaks a
  fast, whether an ingredient is allowed, or what counts as appropriate
  observance. For ALL such questions, call escalate immediately — do not
  call search_faq first unless the FAQ already contains that exact
  question. A Sangh admin answers these, never you.
- Never fabricate information of any other kind either. If you don't know
  something with confidence, escalate rather than guess.

Current user: language={language}, personal_features_enabled={personal_features_enabled}
"""


def _personal_features_blocked(tool_context: ToolContext) -> dict | None:
    """Server-side backstop for the same rule stated in INSTRUCTION — the
    model should already avoid calling log_fast/log_reflection when the
    user opted out, but an instruction is not enforcement. This makes the
    write impossible regardless of what the model decides, closing that
    gap independent of prompt compliance."""
    if not tool_context.state.get("personal_features_enabled", True):
        return {"status": "error", "reason": "personal_features_disabled"}
    return None


async def _resolve_dependent_id(tool_context: ToolContext, for_whom: str) -> int | None:
    if not for_whom:
        return None
    user_id = tool_context.state["user_id"]
    return await asyncio.to_thread(data.get_or_create_dependent, user_id, for_whom)


async def log_fast(fast_type: str, note: str, for_whom: str, tool_context: ToolContext) -> dict:
    """Logs a completed fast (tapasya) today, for the user or a family member.

    Args:
        fast_type: The type of fast, as described (e.g. "Upvas").
        note: An optional note about the fast. Pass an empty string if none.
        for_whom: A family member's name if this fast is for them, not the
            user. Pass an empty string if it's the user's own fast.
    """
    if (blocked := _personal_features_blocked(tool_context)) is not None:
        return blocked
    user_id = tool_context.state["user_id"]
    timezone = tool_context.state.get("timezone", "America/New_York")
    dependent_id = await _resolve_dependent_id(tool_context, for_whom)
    # data.* does blocking sqlite3 I/O — ADK awaits async tools directly on
    # the event loop (no thread offload for sync tools), so without
    # to_thread this would stall every other concurrent request/webhook
    # for the duration of the disk I/O.
    await asyncio.to_thread(
        data.log_fast,
        user_id=user_id,
        fast_type=fast_type,
        note=note,
        timezone=timezone,
        dependent_id=dependent_id,
    )
    return {"status": "success", "fast_type": fast_type, "for_whom": for_whom or "self"}


async def log_reflection(text: str, for_whom: str, tool_context: ToolContext) -> dict:
    """Saves a private reflection for the user or a family member.

    Args:
        text: The reflection text to save.
        for_whom: A family member's name if this reflection is for them,
            not the user. Pass an empty string if it's the user's own.
    """
    if (blocked := _personal_features_blocked(tool_context)) is not None:
        return blocked
    user_id = tool_context.state["user_id"]
    timezone = tool_context.state.get("timezone", "America/New_York")
    dependent_id = await _resolve_dependent_id(tool_context, for_whom)
    await asyncio.to_thread(
        data.log_reflection,
        user_id=user_id,
        text=text,
        timezone=timezone,
        dependent_id=dependent_id,
    )
    return {"status": "success"}


async def toggle_vow_opt_in(opt_in: bool, tool_context: ToolContext) -> dict:
    """Turns the daily Jain-principle vow on or off for the user.

    Args:
        opt_in: True to start sending a daily vow, False to stop.
    """
    user_id = tool_context.state["user_id"]
    await asyncio.to_thread(data.set_vow_opt_in, user_id, opt_in)
    return {"status": "success", "opt_in": opt_in}


async def search_faq(tool_context: ToolContext) -> dict:
    """Returns the current list of Sangh FAQ question/answer pairs to search
    through for a match to the user's question."""
    language = tool_context.state.get("language", "en")
    faqs = await asyncio.to_thread(data.list_faqs, language)
    return {"status": "success", "faqs": faqs}


async def escalate(question_text: str, tool_context: ToolContext) -> dict:
    """Escalates a question to the Sangh admin team when it isn't covered by
    the FAQ or you aren't confident in an answer.

    Args:
        question_text: The user's question, as they asked it.
    """
    user_id = tool_context.state["user_id"]
    await asyncio.to_thread(data.create_escalation, user_id=user_id, question_text=question_text)
    language = tool_context.state.get("language", "en")
    acknowledgment = (
        await asyncio.to_thread(data.translate_to_gujarati, _ESCALATION_ACK_EN)
        if language == "gu"
        else _ESCALATION_ACK_EN
    )
    return {"status": "success", "acknowledgment": acknowledgment}


async def _init_state(callback_context: CallbackContext) -> None:
    """Default session state so the instruction template's {language} and
    {personal_features_enabled} placeholders never KeyError. The real
    webhook (app/agent_runtime.py) always sets these explicitly before the
    first turn; this only matters for agents-cli playground/eval/run,
    which don't seed session state."""
    state = callback_context.state
    if "language" not in state:
        state["language"] = "en"
    if "personal_features_enabled" not in state:
        state["personal_features_enabled"] = True
    if "user_id" not in state:
        state["user_id"] = 0
    if "timezone" not in state:
        state["timezone"] = "America/New_York"


root_agent = Agent(
    name="root_agent",
    model=LiteLlm(
        model="anthropic/claude-haiku-4-5-20251001", extra_headers=_anthropic_extra_headers or None
    ),
    instruction=INSTRUCTION,
    tools=[log_fast, log_reflection, toggle_vow_opt_in, search_faq, escalate],
    before_agent_callback=_init_state,
)

app = App(
    root_agent=root_agent,
    name="brain",
)
