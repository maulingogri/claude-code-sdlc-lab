from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_number: str = ""  # e.g. "whatsapp:+14155238886" (sandbox)

    # Skip signature validation only for local dev/tests. Must be False in staging/prod.
    skip_twilio_signature_validation: bool = False

    # Database
    database_url: str = "sqlite:///./paryushan.db"

    # Festival window
    paryushan_start_date: str = "2026-09-08"
    paryushan_end_date: str = "2026-09-15"
    default_timezone: str = "America/New_York"

    # Admin dashboard (basic shared login — built in a later stage)
    admin_username: str = ""
    admin_password: str = ""

    # ADK agent (post-onboarding free-form routing: fasting/reflection/
    # family-member logging, FAQ answers, escalation), via Claude through
    # LiteLLM. Falls back to the deterministic numbered menu when empty.
    anthropic_api_key: str = ""
    # Only needed for identity-linked Anthropic API keys — see brain/agent.py
    anthropic_workspace_id: str = ""

    # Google Cloud Translation API (v2, simple API-key auth — no GCP ADC/
    # service account needed). Used for all English<->Gujarati translation;
    # see app/translation.py. Falls back to returning the English text
    # untranslated if this is empty.
    google_translate_api_key: str = ""


settings = Settings()
