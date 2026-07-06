import uuid
from datetime import datetime

from sqlalchemy import ARRAY, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class Article(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "articles"

    target_company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("target_companies.id", ondelete="CASCADE"), nullable=False
    )
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # mistral-embed vector over title+description, used for cheap semantic-duplicate
    # detection before spending a full chat-completion call on near-identical coverage.
    embedding: Mapped[list[float] | None] = mapped_column(ARRAY(Float), nullable=True)
    duplicate_of_article_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("articles.id", ondelete="SET NULL"), nullable=True
    )
    # Why no Signal was created, when applicable: "duplicate", "triaged_out", "ai_error".
    # NULL means a Signal was created (or the article hasn't been processed yet).
    skip_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
