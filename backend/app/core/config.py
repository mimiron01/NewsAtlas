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

    # Encrypts WorkspaceSettings.mistral_api_key/.newsdata_api_key at rest (see
    # app/core/crypto.py) — same hard-fail-in-production convention as jwt_secret above,
    # rather than auto-generating one, so a key isn't silently lost on restart before
    # anything's been persisted with it.
    app_secret_key: str = ""

    newsapi_api_key: str = ""
    # Env-var fallback only, mirroring mistral_api_key — the in-app workspace_settings
    # override (see services/workspace_settings.py) always wins once an admin sets one.
    newsdata_api_key: str = ""
    mistral_api_key: str = ""
    mistral_model: str = "mistral-large-latest"
    # Cheap model used for the pre-summarization relevance triage pass (see ai_client.py,
    # ingestion.py) — filters out low-value articles before spending a full mistral_model call.
    mistral_triage_model: str = "mistral-small-latest"
    mistral_embed_model: str = "mistral-embed"
    # Cosine-similarity threshold above which a new article is treated as a semantic
    # duplicate of an existing one for the same target company (skips triage + summarization).
    mistral_dedupe_similarity_threshold: float = 0.90
    # Toggle for the small-model triage pass; disabling sends every article straight to
    # the full summarization call (higher cost, useful for debugging/comparison).
    mistral_triage_enabled: bool = True
    # Self-imposed pacing cap for outbound Mistral calls (see services/ai_client.py,
    # services/mistral_rate_limiter.py). Mistral enforces requests-per-second limits per
    # account tier and exposes no remaining-quota header, so the client has to stay under
    # a known-safe ceiling rather than discover the real one via 429s. Defaults
    # conservatively for the free/evaluation tier; raise it to match a paid tier's actual
    # limit (visible in the Mistral Admin Console under Limits).
    mistral_max_requests_per_second: float = 1.0
    # Retries per HTTP call (not per article) when Mistral returns 429/5xx or a network
    # error occurs; each retry backs off exponentially, honoring `Retry-After` if present.
    mistral_max_retries: int = 5

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
    if len(settings.app_secret_key) < 32:
        problems.append(
            "APP_SECRET_KEY must be set to a random string of at least 32 characters "
            "(e.g. `openssl rand -hex 32`) — it encrypts stored Mistral/NewsData API keys"
        )

    if problems:
        raise RuntimeError(
            "Refusing to start with APP_ENV=production and insecure configuration:\n- "
            + "\n- ".join(problems)
        )
