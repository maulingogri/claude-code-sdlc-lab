"""In-process integration of the paryushan-brain ADK agent into this
webhook's own FastAPI process (single Railway service — see README).

Session state is kept in `InMemorySessionService`, which is fine for Stage
1 testing but does not survive a process restart. Move to a persistent
session service before real production use.
"""

import asyncio
import os

from dotenv import load_dotenv

load_dotenv()

from app.config import settings  # noqa: E402

os.environ.setdefault("DATABASE_URL", settings.database_url)
os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)
os.environ.setdefault("ANTHROPIC_WORKSPACE_ID", settings.anthropic_workspace_id)

from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402

from brain.agent import root_agent  # noqa: E402

from app.catalog import get_message  # noqa: E402
from app.models import User  # noqa: E402

_APP_NAME = "brain"
# Twilio's webhook has a ~15s timeout — if the model is slow (retries,
# provider overload), we must fall back well before that or the reply
# never reaches the user even though our server "succeeds" internally.
_AGENT_TIMEOUT_SECONDS = 10.0
_session_service = InMemorySessionService()
_runner = Runner(agent=root_agent, app_name=_APP_NAME, session_service=_session_service)


async def _collect_reply(user_id: str, session_id: str, body: str) -> list[str]:
    replies: list[str] = []
    async for event in _runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part.from_text(text=body)]),
    ):
        if event.is_final_response() and event.content and event.content.parts:
            text = "".join(part.text or "" for part in event.content.parts)
            if text:
                replies.append(text)
    return replies


async def run_agent_turn(user: User, body: str) -> list[str]:
    """Route one free-form message through the ADK agent. Returns the
    WhatsApp reply text(s). Raises (or times out) on underlying agent/model
    errors — the caller decides how to fall back."""
    session_id = user.phone
    session = await _session_service.get_session(
        app_name=_APP_NAME, user_id=user.phone, session_id=session_id
    )
    state = {
        "user_id": user.id,
        "language": user.language or "en",
        "personal_features_enabled": user.personal_opt_in,
    }
    if session is None:
        await _session_service.create_session(
            app_name=_APP_NAME, user_id=user.phone, session_id=session_id, state=state
        )
    else:
        session.state.update(state)

    try:
        replies = await asyncio.wait_for(
            _collect_reply(user.phone, session_id, body), timeout=_AGENT_TIMEOUT_SECONDS
        )
    except TimeoutError:
        replies = []

    return replies or [get_message("agent_error_fallback", user.language or "en")]
