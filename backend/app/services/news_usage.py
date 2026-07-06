import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.article import ArticleSource
from app.models.news_source_usage_log import NewsSourceUsageLog
from app.models.target_company import TargetCompany
from app.models.workspace_settings import WorkspaceSettings

RECENT_ENTRIES_PER_SOURCE = 20


def log_usage(
    db: Session,
    *,
    source: ArticleSource,
    call_type: str = "latest",
    target_company_id: uuid.UUID | None,
    requests_used: int = 1,
    articles_returned: int = 0,
    commit: bool = True,
) -> None:
    """Records an outbound call that actually went out. Read by the rate limiter
    (services/news_rate_limiter.py) and by the Settings-page usage view (api/news_usage.py)."""
    db.add(
        NewsSourceUsageLog(
            source=source,
            call_type=call_type,
            target_company_id=target_company_id,
            requests_used=requests_used,
            articles_returned=articles_returned,
        )
    )
    if commit:
        db.commit()


def log_rate_limited(
    db: Session, *, source: ArticleSource, target_company_id: uuid.UUID | None, commit: bool = True
) -> None:
    """Records a call the rate limiter refused to make (services/news_rate_limiter.py
    returned no headroom). requests_used=0 so this never counts against the limit itself —
    it only exists so an admin can see "rate limited N times" on the Settings page instead
    of just noticing fewer signals than expected with no explanation."""
    db.add(
        NewsSourceUsageLog(
            source=source,
            call_type="rate_limited",
            target_company_id=target_company_id,
            requests_used=0,
            articles_returned=0,
        )
    )
    if commit:
        db.commit()


def _sum_requests_since(db: Session, source: ArticleSource, since: datetime) -> int:
    return (
        db.query(func.coalesce(func.sum(NewsSourceUsageLog.requests_used), 0))
        .filter(
            NewsSourceUsageLog.source == source,
            NewsSourceUsageLog.created_at >= since,
            NewsSourceUsageLog.call_type != "rate_limited",
        )
        .scalar()
        or 0
    )


def _rate_limited_count_since(db: Session, source: ArticleSource, since: datetime) -> int:
    return (
        db.query(func.count(NewsSourceUsageLog.id))
        .filter(
            NewsSourceUsageLog.source == source,
            NewsSourceUsageLog.created_at >= since,
            NewsSourceUsageLog.call_type == "rate_limited",
        )
        .scalar()
        or 0
    )


def get_source_usage_stats(
    db: Session, workspace_settings: WorkspaceSettings
) -> list[dict]:
    """Per-source usage summary + recent activity, used by GET /news-usage and shown
    inline on the Settings page's "News sources" panel (not a separate report)."""
    now = datetime.now(timezone.utc)
    one_minute_ago = now - timedelta(minutes=1)
    one_day_ago = now - timedelta(days=1)

    limits = {
        ArticleSource.NEWSAPI: {
            "enabled": workspace_settings.newsapi_enabled,
            "per_minute_limit": None,
            "per_day_limit": workspace_settings.newsapi_max_requests_per_day,
        },
        ArticleSource.GOOGLE_NEWS_RSS: {
            "enabled": workspace_settings.google_news_rss_enabled,
            "per_minute_limit": workspace_settings.google_news_rss_max_requests_per_minute,
            "per_day_limit": None,
        },
        ArticleSource.NEWSDATA: {
            "enabled": workspace_settings.newsdata_enabled,
            "per_minute_limit": workspace_settings.newsdata_max_requests_per_minute,
            "per_day_limit": workspace_settings.newsdata_max_requests_per_day,
        },
    }

    stats = []
    for source, config in limits.items():
        recent_rows = (
            db.query(NewsSourceUsageLog, TargetCompany.name)
            .outerjoin(TargetCompany, NewsSourceUsageLog.target_company_id == TargetCompany.id)
            .filter(NewsSourceUsageLog.source == source)
            .order_by(NewsSourceUsageLog.created_at.desc())
            .limit(RECENT_ENTRIES_PER_SOURCE)
            .all()
        )
        stats.append(
            {
                "source": source,
                "enabled": config["enabled"],
                "requests_last_minute": _sum_requests_since(db, source, one_minute_ago),
                "requests_per_minute_limit": config["per_minute_limit"],
                "requests_today": _sum_requests_since(db, source, one_day_ago),
                "requests_per_day_limit": config["per_day_limit"],
                "rate_limited_last_24h": _rate_limited_count_since(db, source, one_day_ago),
                "recent": [
                    {
                        "call_type": row.call_type,
                        "target_company_name": name,
                        "requests_used": row.requests_used,
                        "articles_returned": row.articles_returned,
                        "created_at": row.created_at,
                    }
                    for row, name in recent_rows
                ],
            }
        )
    return stats
