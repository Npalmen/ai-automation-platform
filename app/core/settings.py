from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    APP_NAME: str = "AI Automation Platform"
    ENV: str = "dev"
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    STORAGE_PATH: str = "./storage/local_dev"
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/ai_platform"

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True
    )


@lru_cache
def get_settings() -> "Settings":
    return Settings()