from sqlalchemy import ARRAY, Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class TopicTemplate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An admin-curated, ready-to-use starting point for a ThemeWatch (e.g. "Automotive",
    "Series B+ Funding") — see docs/topics-ux-improvements-planning.html §2.1.

    Rows, not a hardcoded Python list, specifically so template-performance data (§2.4)
    can drive edits without a deploy, and so ai_client.suggest_topics() (§2.3) can be
    grounded in the same set an admin curates rather than generating from scratch.
    """

    __tablename__ = "topic_templates"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # One-line "what this surfaces" copy shown on the template card.
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    # Display-only grouping for the gallery (Industry, Funding & M&A, Regulatory, ...) —
    # never used in matching.
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # None = shown regardless of workspace language ("universal"). "en"/"de" restricts the
    # template to workspaces whose main_language matches, so a German workspace sees a
    # market-specific German set (German search terms, German regulators) instead of a
    # translated copy of the English one — see docs/german-i18n-planning.html.
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    query_terms: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    exclude_terms: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    suggested_source_allowlist: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )
    # Soft-hide from the gallery without losing this template's historical performance
    # data (§2.4) or breaking existing ThemeWatch rows' created_from_template_id FK.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Manual curation ordering within a category; lower sorts first.
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
