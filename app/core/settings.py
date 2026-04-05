from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "AI Automation Platform"
    ENV: str = "dev"
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    STORAGE_PATH: str = "./storage/local_dev"
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/ai_platform"

    CRM_WEBHOOK_URL: str = ""
    CRM_API_KEY: str | None = None

    ACCOUNTING_WEBHOOK_URL: str = ""
    ACCOUNTING_API_KEY: str | None = None

    SUPPORT_WEBHOOK_URL: str = ""
    SUPPORT_API_KEY: str | None = None

    MONDAY_API_URL: str = "https://api.monday.com/v2"
    MONDAY_API_KEY: str = ""
    MONDAY_BOARD_ID: int = 0

    FORTNOX_API_URL: str = "https://api.fortnox.se/3"
    FORTNOX_ACCESS_TOKEN: str = ""
    FORTNOX_CLIENT_SECRET: str = ""

    VISMA_API_URL: str = "https://eaccountingapi.vismaonline.com/v2"
    VISMA_ACCESS_TOKEN: str = ""

    GOOGLE_MAIL_API_URL: str = "https://gmail.googleapis.com/gmail/v1"
    GOOGLE_MAIL_ACCESS_TOKEN: str = ""
    GOOGLE_MAIL_USER_ID: str = "me"

    GOOGLE_CALENDAR_API_URL: str = "https://www.googleapis.com/calendar/v3"
    GOOGLE_CALENDAR_ACCESS_TOKEN: str = ""
    GOOGLE_CALENDAR_ID: str = "primary"

    MICROSOFT_GRAPH_API_URL: str = "https://graph.microsoft.com/v1.0"
    MICROSOFT_MAIL_ACCESS_TOKEN: str = ""
    MICROSOFT_CALENDAR_ACCESS_TOKEN: str = ""
    MICROSOFT_CALENDAR_TIMEZONE: str = "W. Europe Standard Time"

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
    )


@lru_cache
def get_settings() -> "Settings":
    return Settings()