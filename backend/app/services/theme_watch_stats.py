import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.signal import SignalStatus
from app.models.theme_match import ThemeMatch
from app.schemas.theme_watch import ThemeWatchStatsResponse

STATS_LOOKBACK_30D = 30
STATS_LOOKBACK_7D = 7


def get_theme_watch_stats(db: Session, theme_watch_id: uuid.UUID) -> ThemeWatchStatsResponse:
    """Per-topic health snapshot — see docs/topics-ux-improvements-planning.html §3.2.
    With a hard ceiling on active topics per workspace, users need a way to tell which
    topics are worth their slot without manually filtering the matches feed."""
    now = datetime.now(timezone.utc)
    since_7d = now - timedelta(days=STATS_LOOKBACK_7D)
    since_30d = now - timedelta(days=STATS_LOOKBACK_30D)

    base_query = db.query(ThemeMatch).filter(
        ThemeMatch.theme_watch_id == theme_watch_id, ThemeMatch.skip_reason.is_(None)
    )

    matches_last_7d = base_query.filter(ThemeMatch.fetched_at >= since_7d).count()

    row = (
        db.query(
            func.count(ThemeMatch.id),
            func.sum(
                case(
                    (
                        ThemeMatch.status.in_(
                            [SignalStatus.DISMISSED, SignalStatus.REVIEWED, SignalStatus.ARCHIVED]
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
            func.sum(case((ThemeMatch.status == SignalStatus.DISMISSED, 1), else_=0)),
            func.avg(ThemeMatch.relevance_score),
        )
        .filter(
            ThemeMatch.theme_watch_id == theme_watch_id,
            ThemeMatch.skip_reason.is_(None),
            ThemeMatch.fetched_at >= since_30d,
        )
        .first()
    )
    matches_last_30d, rated, dismissed, avg_score = row if row else (0, 0, 0, None)
    matches_last_30d = matches_last_30d or 0
    rated = rated or 0
    dismissed = dismissed or 0

    last_match_at = (
        db.query(func.max(ThemeMatch.fetched_at))
        .filter(ThemeMatch.theme_watch_id == theme_watch_id, ThemeMatch.skip_reason.is_(None))
        .scalar()
    )

    return ThemeWatchStatsResponse(
        matches_last_7d=matches_last_7d,
        matches_last_30d=matches_last_30d,
        dismiss_rate_30d=(dismissed / rated) if rated > 0 else None,
        avg_relevance_score_30d=float(avg_score) if avg_score is not None else None,
        last_match_at=last_match_at,
    )
