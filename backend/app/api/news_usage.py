from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.news_usage import NewsUsageSummary
from app.services.news_usage import get_source_usage_stats
from app.services.workspace_settings import get_or_create_workspace_settings

router = APIRouter(prefix="/news-usage", tags=["news-usage"])


@router.get("", response_model=NewsUsageSummary)
def get_news_usage(
    db: Session = Depends(get_db),
    _current_admin: User = Depends(require_admin),
) -> NewsUsageSummary:
    """Admin-only: per-source request/credit usage against each source's configured
    rate limit, plus recent activity — the data backing the inline usage view on the
    Settings page's "News sources" panel (see docs/news-source-expansion-planning.html §12),
    not just a standalone report."""
    workspace_settings = get_or_create_workspace_settings(db)
    return NewsUsageSummary(sources=get_source_usage_stats(db, workspace_settings))
