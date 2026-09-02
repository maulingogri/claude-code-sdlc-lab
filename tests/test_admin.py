import datetime
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import settings
from app.db import get_session
from app.main import app
from app.models import FAQ, Broadcast, Escalation, FastingLog, User

AUTH = ("test-admin", "test-password")


def _make_user(**kwargs) -> User:
    session = get_session()
    defaults = {"phone": "+15550001234", "language": "en", "onboarding_step": "complete"}
    defaults.update(kwargs)
    user = User(**defaults)
    session.add(user)
    session.commit()
    session.refresh(user)
    session.close()
    return user


def test_admin_requires_auth():
    with TestClient(app) as client:
        response = client.get("/admin/inbox")
        assert response.status_code == 401


def test_admin_rejects_wrong_credentials():
    with TestClient(app) as client:
        response = client.get("/admin/inbox", auth=("wrong", "wrong"))
        assert response.status_code == 401


def test_admin_disabled_when_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "admin_username", "")
    with TestClient(app) as client:
        response = client.get("/admin/inbox", auth=AUTH)
        assert response.status_code == 503


def test_admin_root_redirects_to_inbox():
    with TestClient(app) as client:
        response = client.get("/admin/", auth=AUTH, follow_redirects=False)
        assert response.status_code in (302, 307)
        assert response.headers["location"] == "/admin/inbox"


def test_inbox_shows_pending_and_answered():
    user = _make_user()
    session = get_session()
    session.add(Escalation(user_id=user.id, question_text="When is Pratikraman?", status="pending"))
    session.add(
        Escalation(
            user_id=user.id,
            question_text="Old question",
            status="answered",
            answer_text="Old answer",
        )
    )
    session.commit()
    session.close()

    with TestClient(app) as client:
        response = client.get("/admin/inbox", auth=AUTH)
        assert response.status_code == 200
        assert "When is Pratikraman?" in response.text
        assert "Old answer" in response.text


def test_reply_to_escalation_sends_and_marks_answered():
    user = _make_user()
    session = get_session()
    escalation = Escalation(user_id=user.id, question_text="Q?", status="pending")
    session.add(escalation)
    session.commit()
    escalation_id = escalation.id
    session.close()

    with patch("app.admin.routes.send_whatsapp_message") as mock_send:
        with TestClient(app) as client:
            response = client.post(
                f"/admin/inbox/{escalation_id}/reply",
                data={"answer_text": "The Pratikraman is at 7 PM."},
                auth=AUTH,
                follow_redirects=False,
            )
        assert response.status_code == 303
        mock_send.assert_called_once_with(user.phone, "The Pratikraman is at 7 PM.")

    session = get_session()
    updated = session.get(Escalation, escalation_id)
    assert updated.status == "answered"
    assert updated.answer_text == "The Pratikraman is at 7 PM."
    session.close()


def test_reply_send_failure_returns_502():
    user = _make_user()
    session = get_session()
    escalation = Escalation(user_id=user.id, question_text="Q?", status="pending")
    session.add(escalation)
    session.commit()
    escalation_id = escalation.id
    session.close()

    with patch("app.admin.routes.send_whatsapp_message", side_effect=RuntimeError("boom")):
        with TestClient(app) as client:
            response = client.post(
                f"/admin/inbox/{escalation_id}/reply", data={"answer_text": "Hi"}, auth=AUTH
            )
        assert response.status_code == 502

    session = get_session()
    still_pending = session.get(Escalation, escalation_id)
    assert still_pending.status == "pending"
    session.close()


def test_add_to_faq_flow():
    user = _make_user(language="en")
    session = get_session()
    escalation = Escalation(
        user_id=user.id,
        question_text="What time is Samvatsari Pratikraman?",
        status="answered",
        answer_text="7 PM at the Sangh hall.",
    )
    session.add(escalation)
    session.commit()
    escalation_id = escalation.id
    session.close()

    with TestClient(app) as client:
        form_response = client.get(f"/admin/inbox/{escalation_id}/add-to-faq", auth=AUTH)
        assert form_response.status_code == 200
        assert "What time is Samvatsari Pratikraman?" in form_response.text

        submit_response = client.post(
            f"/admin/inbox/{escalation_id}/add-to-faq",
            data={
                "question_en": "What time is Samvatsari Pratikraman?",
                "question_gu": "સંવત્સરી પ્રતિક્રમણ ક્યારે છે?",
                "answer_en": "7 PM at the Sangh hall.",
                "answer_gu": "સાંજે 7 વાગ્યે સંઘ હોલમાં.",
            },
            auth=AUTH,
            follow_redirects=False,
        )
        assert submit_response.status_code == 303

    session = get_session()
    faq = session.query(FAQ).one()
    assert faq.question_en == "What time is Samvatsari Pratikraman?"
    updated_escalation = session.get(Escalation, escalation_id)
    assert updated_escalation.added_to_faq is True
    session.close()


def test_content_broadcast_create_and_edit():
    with TestClient(app) as client:
        create_response = client.post(
            "/admin/content/broadcast",
            data={
                "date": "2026-09-08",
                "day_number": "1",
                "theme_en": "Compassion",
                "theme_gu": "કરુણા",
                "pratikraman_timing": "7:00 PM",
                "announcements_en": "Arrive early.",
                "announcements_gu": "",
            },
            auth=AUTH,
            follow_redirects=False,
        )
        assert create_response.status_code == 303

        edit_response = client.post(
            "/admin/content/broadcast",
            data={
                "date": "2026-09-08",
                "day_number": "1",
                "theme_en": "Compassion (updated)",
                "theme_gu": "કરુણા",
                "pratikraman_timing": "7:30 PM",
                "announcements_en": "",
                "announcements_gu": "",
            },
            auth=AUTH,
            follow_redirects=False,
        )
        assert edit_response.status_code == 303

    session = get_session()
    broadcasts = session.query(Broadcast).all()
    assert len(broadcasts) == 1  # updated in place, not duplicated
    assert broadcasts[0].theme_en == "Compassion (updated)"
    assert broadcasts[0].pratikraman_timing == "7:30 PM"
    session.close()


def test_content_faq_create_edit_delete():
    with TestClient(app) as client:
        client.post(
            "/admin/content/faq",
            data={
                "question_en": "Q1",
                "question_gu": "ગુજ Q1",
                "answer_en": "A1",
                "answer_gu": "ગુજ A1",
            },
            auth=AUTH,
        )

    session = get_session()
    faq = session.query(FAQ).one()
    faq_id = faq.id
    session.close()

    with TestClient(app) as client:
        edit_form = client.get(f"/admin/content?edit_faq_id={faq_id}", auth=AUTH)
        assert "Q1" in edit_form.text

        client.post(
            "/admin/content/faq",
            data={
                "faq_id": str(faq_id),
                "question_en": "Q1 updated",
                "question_gu": "ગુજ Q1",
                "answer_en": "A1",
                "answer_gu": "ગુજ A1",
            },
            auth=AUTH,
        )

    session = get_session()
    assert session.query(FAQ).one().question_en == "Q1 updated"
    session.close()

    with TestClient(app) as client:
        client.post(f"/admin/content/faq/{faq_id}/delete", auth=AUTH)

    session = get_session()
    assert session.query(FAQ).count() == 0
    session.close()


def test_users_list_and_detail():
    user = _make_user(display_name="Test User")
    session = get_session()
    session.add(FastingLog(user_id=user.id, date=datetime.date(2026, 9, 8), fast_type="Upvas"))
    session.commit()
    session.close()

    with TestClient(app) as client:
        list_response = client.get("/admin/users", auth=AUTH)
        assert user.phone in list_response.text

        detail_response = client.get(f"/admin/users/{user.id}", auth=AUTH)
        assert detail_response.status_code == 200
        assert "Upvas" in detail_response.text


def test_broadcast_tab_no_content_shows_empty():
    with TestClient(app) as client:
        response = client.get("/admin/broadcast", auth=AUTH)
        assert response.status_code == 200
        assert "No broadcast content" in response.text


def test_broadcast_send_marks_sent_and_calls_twilio():
    today = datetime.date.today()
    user = _make_user(broadcast_opt_in=True)
    session = get_session()
    session.add(
        Broadcast(
            date=today,
            day_number=1,
            theme_en="Compassion",
            theme_gu="કરુણા",
            pratikraman_timing="7:00 PM",
        )
    )
    session.commit()
    session.close()

    with patch("app.broadcast.send_whatsapp_message") as mock_send:
        with TestClient(app) as client:
            preview_response = client.get("/admin/broadcast", auth=AUTH)
            assert "Compassion" in preview_response.text

            send_response = client.post("/admin/broadcast/send", auth=AUTH, follow_redirects=False)
        assert send_response.status_code == 303
        assert send_response.headers["location"] == "/admin/broadcast?sent=1&failed=0"
        mock_send.assert_called_once()
        assert mock_send.call_args[0][0] == user.phone
        assert "Compassion" in mock_send.call_args[0][1]

    session = get_session()
    broadcast = session.query(Broadcast).filter(Broadcast.date == today).one()
    assert broadcast.sent_at is not None
    session.close()

    with TestClient(app) as client:
        flash_response = client.get("/admin/broadcast?sent=1&failed=0", auth=AUTH)
        assert "Sent successfully to 1 recipient" in flash_response.text
        assert 'class="flash flash-error"' not in flash_response.text


def test_broadcast_send_total_failure_does_not_mark_sent():
    today = datetime.date.today()
    _make_user(broadcast_opt_in=True)
    session = get_session()
    session.add(
        Broadcast(
            date=today,
            day_number=1,
            theme_en="Compassion",
            theme_gu="કરુણા",
            pratikraman_timing="7:00 PM",
        )
    )
    session.commit()
    session.close()

    with patch("app.broadcast.send_whatsapp_message", side_effect=RuntimeError("Twilio down")):
        with TestClient(app) as client:
            send_response = client.post("/admin/broadcast/send", auth=AUTH, follow_redirects=False)
        assert send_response.headers["location"] == "/admin/broadcast?sent=0&failed=1"

    session = get_session()
    broadcast = session.query(Broadcast).filter(Broadcast.date == today).one()
    assert broadcast.sent_at is None
    session.close()

    with TestClient(app) as client:
        flash_response = client.get("/admin/broadcast?sent=0&failed=1", auth=AUTH)
        assert "Send failed for all 1 recipient" in flash_response.text
        assert 'class="flash flash-error"' in flash_response.text


def test_broadcast_send_with_no_recipients_shows_clear_message_not_false_success():
    today = datetime.date.today()
    session = get_session()
    session.add(
        Broadcast(
            date=today,
            day_number=1,
            theme_en="Compassion",
            theme_gu="કરુણા",
            pratikraman_timing="7:00 PM",
        )
    )
    session.commit()
    session.close()

    with patch("app.broadcast.send_whatsapp_message") as mock_send:
        with TestClient(app) as client:
            send_response = client.post("/admin/broadcast/send", auth=AUTH, follow_redirects=False)
        assert send_response.headers["location"] == "/admin/broadcast?sent=0&failed=0"
        mock_send.assert_not_called()

    with TestClient(app) as client:
        flash_response = client.get("/admin/broadcast?sent=0&failed=0", auth=AUTH)
        assert "No one is opted in" in flash_response.text
        assert "Sent successfully to 0" not in flash_response.text
        assert 'class="flash flash-error"' not in flash_response.text
