from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.article import ArticleSource
from app.models.news_source_usage_log import NewsSourceUsageLog


def has_headroom(
    db: Session,
    source: ArticleSource,
    *,
    per_minute_limit: int | None,
    per_day_limit: int | None,
) -> bool:
    """Whether `source` still has room to make another request under its configured
    per-minute/per-day ceilings.

    Counts persisted `news_source_usage_logs` rows rather than any in-memory/counter
    state, so a process restart or redeploy never resets a limit early — the same shape
    as `workspace_settings.enforce_manual_trigger_cooldown`, which already checks a
    persisted timestamp before allowing an action to proceed. A limit of None or <= 0
    is treated as "no ceiling configured" and never blocks.
    """
    now = datetime.now(timezone.utc)

    if per_minute_limit and per_minute_limit > 0:
        count = _count_since(db, source, now - timedelta(minutes=1))
        if count >= per_minute_limit:
            return False

    if per_day_limit and per_day_limit > 0:
        count = _count_since(db, source, now - timedelta(days=1))
        if count >= per_day_limit:
            return False

    return True


def _count_since(db: Session, source: ArticleSource, since: datetime) -> int:
    # Sums requests_used (not row count) since a single NewsData.io call can cost more
    # than one credit, and excludes "rate_limited" marker rows (see services/news_usage.py)
    # — those record a skipped attempt for the Settings-page activity log, not a real call.
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
