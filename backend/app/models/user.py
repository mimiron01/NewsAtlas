import enum

from sqlalchemy import Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    USER = "user"


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Every issued JWT embeds the token_version current at issuance time (see
    # core/security.create_access_token). /auth/logout increments this, which instantly
    # invalidates every previously-issued token for this user (see api/deps.get_current_user)
    # — a counter avoids the precision issues a timestamp-based cutoff would have against
    # JWT's whole-second "iat" granularity.
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
        default=UserRole.USER,
    )
