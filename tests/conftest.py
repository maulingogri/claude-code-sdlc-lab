import os
import tempfile

_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp_db.name}")
os.environ.setdefault("SKIP_TWILIO_SIGNATURE_VALIDATION", "true")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test-auth-token")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "ACtest")
os.environ.setdefault("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")
os.environ.setdefault("ADMIN_USERNAME", "test-admin")
os.environ.setdefault("ADMIN_PASSWORD", "test-password")
# Force the deterministic-menu path by default — never let a real key in
# .env make tests hit the live Claude API. test_agent_routing.py mocks the
# agent explicitly for the tests that need the key path.
os.environ["ANTHROPIC_API_KEY"] = ""

import pytest  # noqa: E402

from app.db import Base, engine, init_db  # noqa: E402
from app.rate_limit import reset as reset_rate_limiter  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_db():
    init_db()
    # Several tests send many messages from the same phone number in
    # quick succession (e.g. a full onboarding conversation) — without
    # resetting between tests, accumulated calls across the whole session
    # would eventually trip the rate limiter and break unrelated tests.
    reset_rate_limiter()
    yield
    Base.metadata.drop_all(bind=engine)
