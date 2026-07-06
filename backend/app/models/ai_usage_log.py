import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class AIUsageLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One row per Mistral API call, for cost/volume visibility.

    Granularity is per target company rather than per article: embedding calls are
    batched across all of a target company's new articles in one request, so attributing
    usage to a single article would be misleading.
    """

    __tablename__ = "ai_usage_logs"

    call_type: Mapped[str] = mapped_column(String(32), nullable=False)  # embedding|triage|summarize
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target_company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("target_companies.id", ondelete="SET NULL"), nullable=True
    )
