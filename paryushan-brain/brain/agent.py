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

# CLAUDE.md's Escalation Flow mandates this exact bilingual acknowledgment
# text — matches app/message_catalog.json's "escalation_ack" entry.
# Duplicated here rather than imported, same as brain/data.py's schema
# duplication: this file deliberately avoids importing the root `app`
# package so paryushan-brain stays independently testable via agents-cli.
# Keep both copies in sync by hand if the wording ever changes.
_ESCALATION_ACK = {
    "en": "Great question — let me check with the Sangh and get back to you soon.",
    "gu": "સરસ પ્રશ્ન — હું સંઘ સાથે તપાસ કરીને તમને ટૂંક સમયમાં જવાબ આપીશ.",
}

INSTRUCTION = """
You are the WhatsApp assistant for the Louisville Jain Sangh Paryushan
companion (Sept 8-15, 2026). You are talking to a user who has already
completed onboarding. Always reply in the user's language: if language is
"gu", reply in Gujarati; otherwise reply in English. Keep replies short —
this is WhatsApp.

You can help with:
- Logging a fast (tapasya): call log_fast with the fast type they describe
  (e.g. Upvas, Ekasana, Biyasana, Ayambil) and any note they gave (pass an
  empty string if they gave no note).
- Saving a private reflection: call log_reflection with their reflection
  text.
- Adding someone to their forgiveness list (kshamapana): call
  add_forgiveness_entry with the name and an optional note (empty string if
  none given).
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
- If personal_features_enabled is false, do NOT call log_fast,
  log_reflection, or add_forgiveness_entry. Instead tell the user they
  opted out of personal features during setup, and can ask a Sangh admin
  to turn them on.
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
    model should already avoid calling log_fast/log_reflection/
    add_forgiveness_entry when the user opted out, but an instruction is
    not enforcement. This makes the write impossible regardless of what
    the model decides, closing that gap independent of prompt compliance."""
    if not tool_context.state.get("personal_features_enabled", True):
        return {"status": "error", "reason": "personal_features_disabled"}
    return None


async def log_fast(fast_type: str, note: str, tool_context: ToolContext) -> dict:
    """Logs that the user completed a fast (tapasya) today.

    Args:
        fast_type: The type of fast, as the user described it (e.g. "Upvas").
        note: An optional note about the fast. Pass an empty string if none.
    """
    if (blocked := _personal_features_blocked(tool_context)) is not None:
        return blocked
    user_id = tool_context.state["user_id"]
    timezone = tool_context.state.get("timezone", "America/New_York")
    # data.* does blocking sqlite3 I/O — ADK awaits async tools directly on
    # the event loop (no thread offload for sync tools), so without
    # to_thread this would stall every other concurrent request/webhook
    # for the duration of the disk I/O.
    await asyncio.to_thread(data.log_fast, user_id=user_id, fast_type=fast_type, note=note, timezone=timezone)
    return {"status": "success", "fast_type": fast_type}


async def log_reflection(text: str, tool_context: ToolContext) -> dict:
    """Saves a private reflection for the user.

    Args:
        text: The reflection text to save.
    """
    if (blocked := _personal_features_blocked(tool_context)) is not None:
        return blocked
    user_id = tool_context.state["user_id"]
    timezone = tool_context.state.get("timezone", "America/New_York")
    await asyncio.to_thread(data.log_reflection, user_id=user_id, text=text, timezone=timezone)
    return {"status": "success"}


async def add_forgiveness_entry(name: str, note: str, tool_context: ToolContext) -> dict:
    """Adds a person to the user's forgiveness (kshamapana) list.

    Args:
        name: The name of the person to add.
        note: An optional note about the relationship or message. Pass an
            empty string if none.
    """
    if (blocked := _personal_features_blocked(tool_context)) is not None:
        return blocked
    user_id = tool_context.state["user_id"]
    await asyncio.to_thread(data.add_forgiveness_entry, user_id=user_id, name=name, note=note)
    return {"status": "success", "name": name}


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
    acknowledgment = _ESCALATION_ACK.get(language, _ESCALATION_ACK["en"])
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
    tools=[log_fast, log_reflection, add_forgiveness_entry, search_faq, escalate],
    before_agent_callback=_init_state,
)

app = App(
    root_agent=root_agent,
    name="brain",
)
