import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class SignalStatus(str, enum.Enum):
    NEW = "new"
    REVIEWED = "reviewed"
    ARCHIVED = "archived"
    DISMISSED = "dismissed"


class Signal(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "signals"

    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("articles.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    business_relevance: Mapped[str] = mapped_column(Text, nullable=False)
    outreach_snippet_email: Mapped[str] = mapped_column(Text, nullable=False)
    outreach_snippet_linkedin: Mapped[str] = mapped_column(Text, nullable=False, default="")
    outreach_call_opener: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # 1 (background noise) .. 5 (act on this today) — lets the feed/digest surface the
    # highest-value signals first instead of treating every article as equally important.
    relevance_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    signal_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    supporting_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    entities: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Token usage for the summarization call that produced this signal (for per-signal
    # cost visibility; aggregate spend is tracked in ai_usage_logs).
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[SignalStatus] = mapped_column(
        Enum(SignalStatus, name="signal_status"), nullable=False, default=SignalStatus.NEW
    )
    emailed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
