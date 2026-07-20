from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.admin_session_models import VALID_OPERATOR_ROLES


class Settings(BaseSettings):
    APP_NAME: str = "AI Automation Platform"
    ENV: str = "dev"
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    STORAGE_PATH: str = "./storage/local_dev"
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/ai_platform"
    DB_ECHO: bool = False

    # Per-tenant API keys — JSON string mapping tenant_id to api_key.
    # Example: '{"TENANT_1001": "key-abc123", "TENANT_2001": "key-def456"}'
    # Set via TENANT_API_KEYS env var. If empty, auth is disabled (dev mode only).
    TENANT_API_KEYS: str = ""

    # Super-admin API key — protects cross-tenant admin endpoints.
    # Set via ADMIN_API_KEY env var. If empty, admin endpoints fail closed (401).
    # Use X-Admin-API-Key header. Tenant X-API-Key keys are NOT accepted.
    ADMIN_API_KEY: str = ""

    # Optional comma-separated list of admin API keys.
    # If set and non-empty, any key in this list is accepted.
    # Takes precedence over ADMIN_API_KEY when non-empty.
    # Example: ADMIN_API_KEYS=key1,key2,key3
    ADMIN_API_KEYS: str = ""

    # Admin session auth — username + password login via browser.
    # Generate hash: python -c "from app.core.admin_session import hash_password; print(hash_password('pw'))"
    # Generate secret: python -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD_HASH: str = ""
    SESSION_SECRET_KEY: str = ""
    ADMIN_ROLE: str = "admin"
    ADMIN_DISPLAY_NAME: str = ""
    # Comma-separated stable operator IDs (OperatorInfo.id) granted super_admin.
    SUPER_ADMIN_OPERATOR_IDS: str = ""
    # Comma-separated allowed Origin values for POST /auth/admin/login|logout.
    # When empty, same-origin is derived from the incoming request URL.
    ALLOWED_ORIGINS: str = ""

    @field_validator("ADMIN_ROLE")
    @classmethod
    def validate_admin_role(cls, value: str) -> str:
        if value not in VALID_OPERATOR_ROLES:
            allowed = ", ".join(sorted(VALID_OPERATOR_ROLES))
            raise ValueError(f"ADMIN_ROLE must be one of: {allowed}")
        return value

    EMAIL_PROVIDER: str = "google_mail"

    CRM_WEBHOOK_URL: str = ""
    CRM_API_KEY: str | None = None

    ACCOUNTING_WEBHOOK_URL: str = ""
    ACCOUNTING_API_KEY: str | None = None

    SUPPORT_WEBHOOK_URL: str = ""
    SUPPORT_API_KEY: str | None = None

    SLACK_PROVIDER: str = "webhook"
    SLACK_WEBHOOK_URL: str = ""
    SLACK_TIMEOUT_SECONDS: int = 10

    MONDAY_API_URL: str = "https://api.monday.com/v2"
    MONDAY_API_KEY: str = ""
    MONDAY_BOARD_ID: int = 0

    FORTNOX_API_URL: str = "https://api.fortnox.se/3"
    FORTNOX_ACCESS_TOKEN: str = ""
    FORTNOX_CLIENT_SECRET: str = ""

    VISMA_API_URL: str = "https://eaccountingapi.vismaonline.com/v2"
    VISMA_ACCESS_TOKEN: str = ""
    VISMA_CLIENT_ID: str = ""
    VISMA_CLIENT_SECRET: str = ""
    VISMA_REDIRECT_URI: str = ""
    VISMA_SCOPES: str = "ea:api, ea:sales, ea:purchase, ea:accounting, vls:api, offline_access"

    GOOGLE_MAIL_API_URL: str = "https://gmail.googleapis.com/gmail/v1"
    GOOGLE_MAIL_ACCESS_TOKEN: str = ""
    GOOGLE_MAIL_USER_ID: str = "me"
    GOOGLE_OAUTH_REFRESH_TOKEN: str = ""
    GOOGLE_OAUTH_CLIENT_ID: str = ""
    GOOGLE_OAUTH_CLIENT_SECRET: str = ""
    GOOGLE_OAUTH_REDIRECT_URI: str = ""
    GOOGLE_OAUTH_SCOPES: str = (
        "https://www.googleapis.com/auth/gmail.readonly "
        "https://www.googleapis.com/auth/gmail.modify"
    )

    GOOGLE_CALENDAR_API_URL: str = "https://www.googleapis.com/calendar/v3"
    GOOGLE_CALENDAR_ACCESS_TOKEN: str = ""
    GOOGLE_CALENDAR_ID: str = "primary"

    MICROSOFT_GRAPH_API_URL: str = "https://graph.microsoft.com/v1.0"
    MICROSOFT_MAIL_ACCESS_TOKEN: str = ""
    MICROSOFT_CALENDAR_ACCESS_TOKEN: str = ""
    MICROSOFT_CALENDAR_TIMEZONE: str = "W. Europe Standard Time"

    LLM_API_URL: str = "https://api.openai.com/v1/chat/completions"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4.1-mini"
    LLM_TIMEOUT_SECONDS: int = 45
    LLM_TEMPERATURE: float = 0.0
    LLM_MAX_TOKENS: int = 1200
    LLM_RETRY_ATTEMPTS: int = 2
    LLM_RETRY_DELAY_SECONDS: float = 0.8

    # System status metadata (Kapitel 8) — same env var names as backup/restore scripts.
    # Container defaults; host cron uses host paths via inline env (see runbook).
    BACKUP_STATUS_FILE: str = "/app/storage/status/backup_status.json"
    RESTORE_STATUS_FILE: str = "/app/storage/status/restore_status.json"
    BUILD_METADATA_PATH: str = "/app/build-metadata.json"
    BACKUP_EXPECTED_INTERVAL_HOURS: int = 24
    BACKUP_MAX_AGE_HOURS: int = 25
    RESTORE_TEST_MAX_AGE_DAYS: int = 30

    # Operator alert email (Kapitel 10) — platform allowlist only; empty = in-app only.
    OPERATOR_ALERT_RECIPIENT: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
    )


@lru_cache
def get_settings() -> "Settings":
    return Settings()