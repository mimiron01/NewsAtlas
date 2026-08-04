import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ThemeMatchFavorite(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Mirrors SignalFavorite for ThemeMatch — per-user, not workspace-wide, same as a
    signal favorite."""

    __tablename__ = "theme_match_favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "theme_match_id", name="uq_theme_match_favorites_user_match"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    theme_match_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("theme_matches.id", ondelete="CASCADE"), nullable=False
    )
