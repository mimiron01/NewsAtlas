from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class WorkspaceSettings(Base, UUIDPrimaryKeyMixin):
    """Single-row table holding the shared workspace configuration (MVP is single-tenant)."""

    __tablename__ = "workspace_settings"

    company_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    offering_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    digest_send_time: Mapped[str] = mapped_column(String(5), nullable=False, default="07:00")
    ingestion_interval_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Cooldown bookkeeping for the manual trigger endpoints, independent of caller identity
    # (see api/ingestion.py, api/digest.py) — prevents any user from hammering paid external
    # APIs or spamming digest emails by repeatedly calling the manual trigger.
    last_manual_ingestion_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_manual_digest_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Short, rule-based steering note derived from dismissed-signal patterns (no LLM call
    # involved in computing it — see services/feedback.py) and injected into future
    # summarization prompts to bias away from categories users keep dismissing.
    ai_feedback_note: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # --- Admin-configurable Mistral integration settings (see api/settings.py) ---
    # Empty string means "no in-app override" — the effective key falls back to the
    # MISTRAL_API_KEY env var (app/core/config.py) so existing .env-based deployments
    # keep working until an admin explicitly sets/rotates a key here.
    mistral_api_key: Mapped[str] = mapped_column(Text, nullable=False, default="")
    mistral_model: Mapped[str] = mapped_column(String(100), nullable=False, default="mistral-large-latest")
    mistral_triage_model: Mapped[str] = mapped_column(String(100), nullable=False, default="mistral-small-latest")
    mistral_embed_model: Mapped[str] = mapped_column(String(100), nullable=False, default="mistral-embed")
    mistral_triage_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    mistral_dedupe_similarity_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.90)
