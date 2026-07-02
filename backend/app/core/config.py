from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://newsatlas:newsatlas@localhost:5432/newsatlas"

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 24 * 7

    newsapi_api_key: str = ""
    mistral_api_key: str = ""
    mistral_model: str = "mistral-large-latest"

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_address: str = "signals@example.com"

    ingestion_interval_hours: int = 6
    digest_send_time: str = "07:00"

    cors_origins: list[str] = ["http://localhost:5173"]
    frontend_base_url: str = "http://localhost:5173"

    enable_scheduler: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
