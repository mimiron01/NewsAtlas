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
    # Per-follow (not per-topic) opt-in to include this topic's matches in the daily
    # digest email, same scoping as is_muted — one user opting in doesn't add matches to
    # a co-follower's digest. Defaults false so no existing user's digest changes shape
    # without an explicit action. See docs/topics-ux-improvements-planning.html §4.3.
    include_in_digest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
