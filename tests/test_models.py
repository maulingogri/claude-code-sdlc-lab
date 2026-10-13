import datetime

from app.db import get_session
from app.models import FastingLog, User


def test_create_and_query_user():
    session = get_session()
    try:
        user = User(phone="+15551112222", language="en")
        session.add(user)
        session.commit()

        fetched = session.query(User).filter(User.phone == "+15551112222").one()
        assert fetched.language == "en"
        assert fetched.onboarding_step == "greeting"
        assert fetched.onboarding_complete is False
    finally:
        session.close()


def test_user_fasting_log_relationship():
    session = get_session()
    try:
        user = User(phone="+15553334444")
        session.add(user)
        session.flush()

        log = FastingLog(user_id=user.id, date=datetime.date(2026, 9, 8), fast_type="upvas")
        session.add(log)
        session.commit()

        session.refresh(user)
        assert len(user.fasting_logs) == 1
        assert user.fasting_logs[0].fast_type == "upvas"
    finally:
        session.close()
