import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Text
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
    outreach_snippet: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[SignalStatus] = mapped_column(
        Enum(SignalStatus, name="signal_status"), nullable=False, default=SignalStatus.NEW
    )
    emailed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
