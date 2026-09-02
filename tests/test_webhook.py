from fastapi.testclient import TestClient

from app.main import app

PHONE = "whatsapp:+15559876543"


def _send(client: TestClient, body: str):
    response = client.post("/webhook/twilio", data={"From": PHONE, "Body": body, "To": "whatsapp:+14155238886"})
    assert response.status_code == 200
    assert "application/xml" in response.headers["content-type"]
    return response.text


def test_healthz():
    with TestClient(app) as client:
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_first_contact_sends_greeting_and_language_prompt():
    with TestClient(app) as client:
        xml = _send(client, "hi")
        assert "Jai Jinendra" in xml
        assert "English" in xml


def test_full_onboarding_conversation_via_webhook():
    with TestClient(app) as client:
        _send(client, "hi")  # greeting + language prompt
        xml = _send(client, "1")  # English
        assert "daily Paryushan updates" in xml

        xml = _send(client, "yes")  # broadcast opt-in
        assert "personal features" in xml.lower()

        xml = _send(client, "yes")  # personal opt-in
        assert "recognition" in xml.lower()

        xml = _send(client, "no")  # public recognition opt-in
        assert "all set" in xml.lower()

        # Onboarding complete — unrecognized free text falls back to the menu.
        xml = _send(client, "when is the pratikraman?")
        assert "didn't understand" in xml.lower()
        assert "log a fast" in xml.lower()

        # Full fast-logging flow via the webhook.
        xml = _send(client, "1")
        assert "what type of fast" in xml.lower()
        xml = _send(client, "Upvas")
        assert "add a note" in xml.lower()
        xml = _send(client, "skip")
        assert "fast logged for today (upvas)" in xml.lower()


def test_rejects_request_with_bad_signature_when_validation_enabled(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "skip_twilio_signature_validation", False)
    with TestClient(app) as client:
        response = client.post(
            "/webhook/twilio",
            data={"From": PHONE, "Body": "hi"},
            headers={"X-Twilio-Signature": "not-a-real-signature"},
        )
        assert response.status_code == 403
