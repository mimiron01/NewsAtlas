import uuid

from sqlalchemy import Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ThemeFollow(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Mirrors CompanyFollow exactly — see docs/theme-search-planning.html §2.2."""

    __tablename__ = "theme_follows"
    __table_args__ = (
        UniqueConstraint("user_id", "theme_watch_id", name="uq_theme_follows_user_theme"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    theme_watch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("theme_watches.id", ondelete="CASCADE"), nullable=False
    )
    is_muted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
