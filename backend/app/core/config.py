from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_DEFAULT_JWT_SECRET = "change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    # Alias because the env var is APP_ENV, not ENVIRONMENT (pydantic-settings maps env
    # vars to field names by default, so this would otherwise silently never be read).
    environment: Literal["development", "production"] = Field(
        default="development", alias="APP_ENV"
    )

    database_url: str = "postgresql+psycopg2://newsatlas:newsatlas@localhost:5432/newsatlas"

    jwt_secret: str = INSECURE_DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 24  # 24h; short-lived by design, see M4 in security review

    signup_invite_code: str = ""

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
    manual_trigger_cooldown_seconds: int = 60

    cors_origins: list[str] = ["http://localhost:5173"]
    frontend_base_url: str = "http://localhost:5173"

    enable_scheduler: bool = True
    enable_rate_limiting: bool = True

    max_request_body_bytes: int = 2_000_000


@lru_cache
def get_settings() -> Settings:
    return Settings()


def assert_secure_for_production(settings: Settings) -> None:
    """Refuse to boot with known-insecure configuration when running in production.

    Development defaults intentionally stay permissive so local/test runs don't need
    every secret configured; production must set them explicitly.
    """
    if settings.environment != "production":
        return

    problems: list[str] = []
    if settings.jwt_secret == INSECURE_DEFAULT_JWT_SECRET or len(settings.jwt_secret) < 32:
        problems.append(
            "JWT_SECRET must be set to a random string of at least 32 characters "
            "(e.g. `openssl rand -hex 32`)"
        )
    if not settings.signup_invite_code:
        problems.append(
            "SIGNUP_INVITE_CODE must be set — signup is disabled entirely without it"
        )

    if problems:
        raise RuntimeError(
            "Refusing to start with APP_ENV=production and insecure configuration:\n- "
            + "\n- ".join(problems)
        )
