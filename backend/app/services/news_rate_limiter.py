import time as _time
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable

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


class HeadroomStatus(str, Enum):
    """Finer-grained result than plain has_headroom(): a per-day ceiling won't free up
    again for hours, so a caller processing a whole run should give up on that source
    for this company, but a per-minute ceiling frees up within the next 60s and is
    worth waiting out instead (see wait_for_minute_headroom)."""

    OK = "ok"
    MINUTE_LIMITED = "minute_limited"
    DAY_LIMITED = "day_limited"


def check_headroom(
    db: Session,
    source: ArticleSource,
    *,
    per_minute_limit: int | None,
    per_day_limit: int | None,
) -> HeadroomStatus:
    """Same headroom check as has_headroom(), but reports which ceiling (if any) is
    currently blocking `source` instead of collapsing both into a single bool."""
    now = datetime.now(timezone.utc)

    if per_day_limit and per_day_limit > 0:
        if _count_since(db, source, now - timedelta(days=1)) >= per_day_limit:
            return HeadroomStatus.DAY_LIMITED

    if per_minute_limit and per_minute_limit > 0:
        if _count_since(db, source, now - timedelta(minutes=1)) >= per_minute_limit:
            return HeadroomStatus.MINUTE_LIMITED

    return HeadroomStatus.OK


def wait_for_minute_headroom(
    db: Session,
    source: ArticleSource,
    *,
    per_minute_limit: int | None,
    should_cancel: Callable[[], bool],
    poll_interval_seconds: float = 2.0,
    max_wait_seconds: float = 65.0,
    sleep: Callable[[float], None] = _time.sleep,
    clock: Callable[[], float] = _time.monotonic,
) -> bool:
    """Blocks until `source` has per-minute headroom again, polling in short increments
    so a cancellation request is noticed quickly rather than only after a full wait.

    A per-minute window always frees up within 60s of its oldest counted request, so
    max_wait_seconds is a defensive cap against clock skew or a misconfigured limit,
    not an outcome this should normally hit. Returns False if should_cancel() fires or
    the cap is reached first (caller falls back to skipping this source, same as
    before); True once headroom is confirmed (including immediately, if there already
    was headroom).
    """
    if not per_minute_limit or per_minute_limit <= 0:
        return True

    deadline = clock() + max_wait_seconds
    while _count_since(db, source, datetime.now(timezone.utc) - timedelta(minutes=1)) >= per_minute_limit:
        if should_cancel():
            return False
        remaining = deadline - clock()
        if remaining <= 0:
            return False
        sleep(min(poll_interval_seconds, remaining))

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
