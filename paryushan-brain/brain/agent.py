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


def log_fast(fast_type: str, note: str, tool_context: ToolContext) -> dict:
    """Logs that the user completed a fast (tapasya) today.

    Args:
        fast_type: The type of fast, as the user described it (e.g. "Upvas").
        note: An optional note about the fast. Pass an empty string if none.
    """
    user_id = tool_context.state["user_id"]
    data.log_fast(user_id=user_id, fast_type=fast_type, note=note)
    return {"status": "success", "fast_type": fast_type}


def log_reflection(text: str, tool_context: ToolContext) -> dict:
    """Saves a private reflection for the user.

    Args:
        text: The reflection text to save.
    """
    user_id = tool_context.state["user_id"]
    data.log_reflection(user_id=user_id, text=text)
    return {"status": "success"}


def add_forgiveness_entry(name: str, note: str, tool_context: ToolContext) -> dict:
    """Adds a person to the user's forgiveness (kshamapana) list.

    Args:
        name: The name of the person to add.
        note: An optional note about the relationship or message. Pass an
            empty string if none.
    """
    user_id = tool_context.state["user_id"]
    data.add_forgiveness_entry(user_id=user_id, name=name, note=note)
    return {"status": "success", "name": name}


def search_faq(tool_context: ToolContext) -> dict:
    """Returns the current list of Sangh FAQ question/answer pairs to search
    through for a match to the user's question."""
    language = tool_context.state.get("language", "en")
    return {"status": "success", "faqs": data.list_faqs(language)}


def escalate(question_text: str, tool_context: ToolContext) -> dict:
    """Escalates a question to the Sangh admin team when it isn't covered by
    the FAQ or you aren't confident in an answer.

    Args:
        question_text: The user's question, as they asked it.
    """
    user_id = tool_context.state["user_id"]
    data.create_escalation(user_id=user_id, question_text=question_text)
    return {"status": "success"}


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
