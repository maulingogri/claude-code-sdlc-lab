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

        xml = _send(client, "YES Test User")  # broadcast opt-in + name, combined
        assert "personal features" in xml.lower()

        xml = _send(client, "yes")  # personal opt-in
        assert "recognition" in xml.lower()

        xml = _send(client, "no")  # public recognition opt-in
        assert "family members" in xml.lower()

        xml = _send(client, "none")  # no family members to log for
        assert "onboarding complete" in xml.lower()

        # Onboarding complete — unrecognized free text falls back to the menu.
        xml = _send(client, "when is the pratikraman?")
        assert "didn't understand" in xml.lower()
        assert "log a fast" in xml.lower()

        # Full fast-logging flow via the webhook.
        xml = _send(client, "1")
        assert "what type of fast" in xml.lower()
        xml = _send(client, "Upvas")
        assert "is this for you" in xml.lower()
        xml = _send(client, "you")
        assert "add a note" in xml.lower()
        xml = _send(client, "skip")
        assert "fast logged for today (upvas)" in xml.lower()


def test_rate_limit_silently_drops_messages_beyond_the_threshold():
    with TestClient(app) as client:
        for _ in range(15):
            xml = _send(client, "hi")
        assert "<Message>" in xml  # the 15th still gets a normal reply

        response = client.post("/webhook/twilio", data={"From": PHONE, "Body": "hi"})
        assert response.status_code == 200
        assert "<Message>" not in response.text  # silently dropped, no reply

        # A different phone number is unaffected.
        other_phone = "whatsapp:+15559990000"
        response = client.post("/webhook/twilio", data={"From": other_phone, "Body": "hi"})
        assert "<Message>" in response.text


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
