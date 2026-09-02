from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

PHONE = "whatsapp:+15551230000"


def _onboard(client: TestClient) -> None:
    client.post("/webhook/twilio", data={"From": PHONE, "Body": "hi"})
    client.post("/webhook/twilio", data={"From": PHONE, "Body": "1"})  # English
    client.post("/webhook/twilio", data={"From": PHONE, "Body": "no"})  # broadcast
    client.post("/webhook/twilio", data={"From": PHONE, "Body": "yes"})  # personal features
    client.post("/webhook/twilio", data={"From": PHONE, "Body": "no"})  # public recognition


def test_agent_path_used_when_anthropic_key_configured(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "fake-key")
    monkeypatch.setattr(
        "app.agent_runtime.run_agent_turn", AsyncMock(return_value=["Fast logged, thank you!"])
    )
    with TestClient(app) as client:
        _onboard(client)
        response = client.post("/webhook/twilio", data={"From": PHONE, "Body": "I fasted today"})
        assert "Fast logged, thank you!" in response.text


def test_agent_failure_falls_back_to_error_message(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "fake-key")
    monkeypatch.setattr(
        "app.agent_runtime.run_agent_turn", AsyncMock(side_effect=RuntimeError("boom"))
    )
    with TestClient(app) as client:
        _onboard(client)
        response = client.post("/webhook/twilio", data={"From": PHONE, "Body": "I fasted today"})
        assert "trouble processing" in response.text.lower()


def test_deterministic_menu_used_when_no_anthropic_key(monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    with TestClient(app) as client:
        _onboard(client)
        response = client.post("/webhook/twilio", data={"From": PHONE, "Body": "menu"})
        assert "log a fast" in response.text.lower()
