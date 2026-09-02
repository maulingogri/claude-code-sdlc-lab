"""Schema-drift guard for paryushan-brain/brain/data.py.

brain/data.py deliberately hand-writes raw SQL against the same tables
app/models.py defines via SQLAlchemy, instead of importing app/models.py —
see that file's module docstring for why. That means nothing at import
time keeps the two in sync; a schema change to app/models.py can silently
break every brain.data function at runtime with no warning until a real
user hits it (this already happened once during development — see the
comment on create_escalation).

This test exercises every brain.data function against a database created
the real way (app.db.init_db(), i.e. from app/models.py's actual current
schema). If the two drift, one of these fails here instead of in
production.
"""

from brain import data

from app.db import get_session
from app.models import FAQ, Dependent, Escalation, FastingLog, Reflection, User


def _make_user() -> User:
    session = get_session()
    user = User(phone="+15557778888", onboarding_step="complete")
    session.add(user)
    session.commit()
    session.refresh(user)
    session.close()
    return user


def test_log_fast_matches_current_schema():
    user = _make_user()
    data.log_fast(user_id=user.id, fast_type="Upvas", note="test note", timezone="America/New_York")

    session = get_session()
    log = session.query(FastingLog).filter(FastingLog.user_id == user.id).one()
    assert log.fast_type == "Upvas"
    assert log.note == "test note"
    assert log.date is not None
    session.close()


def test_log_reflection_matches_current_schema():
    user = _make_user()
    data.log_reflection(user_id=user.id, text="a reflection", timezone="America/New_York")

    session = get_session()
    reflection = session.query(Reflection).filter(Reflection.user_id == user.id).one()
    assert reflection.text == "a reflection"
    session.close()


def test_get_or_create_dependent_matches_current_schema():
    user = _make_user()
    dependent_id = data.get_or_create_dependent(user.id, "Grandma Shah")

    session = get_session()
    dependent = session.get(Dependent, dependent_id)
    assert dependent.guardian_id == user.id
    assert dependent.name == "Grandma Shah"
    session.close()

    # Same name for the same guardian reuses the row rather than duplicating it.
    assert data.get_or_create_dependent(user.id, "Grandma Shah") == dependent_id


def test_log_fast_with_dependent_matches_current_schema():
    user = _make_user()
    dependent_id = data.get_or_create_dependent(user.id, "Grandma Shah")
    data.log_fast(
        user_id=user.id,
        fast_type="Upvas",
        note="",
        timezone="America/New_York",
        dependent_id=dependent_id,
    )

    session = get_session()
    log = session.query(FastingLog).filter(FastingLog.dependent_id == dependent_id).one()
    assert log.user_id == user.id
    assert log.fast_type == "Upvas"
    session.close()


def test_log_reflection_with_dependent_matches_current_schema():
    user = _make_user()
    dependent_id = data.get_or_create_dependent(user.id, "Little Priya")
    data.log_reflection(
        user_id=user.id, text="a reflection", timezone="America/New_York", dependent_id=dependent_id
    )

    session = get_session()
    reflection = session.query(Reflection).filter(Reflection.dependent_id == dependent_id).one()
    assert reflection.text == "a reflection"
    session.close()


def test_set_vow_opt_in_matches_current_schema():
    user = _make_user()
    data.set_vow_opt_in(user.id, True)

    session = get_session()
    refreshed = session.get(User, user.id)
    assert refreshed.vow_opt_in is True
    session.close()


def test_translate_to_gujarati_matches_current_schema():
    # No GOOGLE_TRANSLATE_API_KEY in the test environment, so this exercises
    # the cache-miss + no-key fallback path rather than a real API call —
    # the point of this test is that it queries/writes the translation_cache
    # table without raising, i.e. the schema still matches.
    assert data.translate_to_gujarati("Hello") == "Hello"


def test_list_faqs_matches_current_schema():
    session = get_session()
    session.add(
        FAQ(question_en="Q?", question_gu="ગુજ?", answer_en="A.", answer_gu="ગુજ A.")
    )
    session.commit()
    session.close()

    faqs_en = data.list_faqs("en")
    faqs_gu = data.list_faqs("gu")

    assert faqs_en == [{"question": "Q?", "answer": "A."}]
    assert faqs_gu == [{"question": "ગુજ?", "answer": "ગુજ A."}]


def test_create_escalation_matches_current_schema():
    user = _make_user()
    data.create_escalation(user_id=user.id, question_text="A question")

    session = get_session()
    escalation = session.query(Escalation).filter(Escalation.user_id == user.id).one()
    assert escalation.question_text == "A question"
    assert escalation.status == "pending"
    assert escalation.added_to_faq is False
    session.close()
