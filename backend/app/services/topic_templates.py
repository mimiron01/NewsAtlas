import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.signal import SignalStatus
from app.models.theme_match import ThemeMatch
from app.models.theme_watch import ThemeWatch
from app.models.topic_template import TopicTemplate

PERFORMANCE_LOOKBACK_DAYS = 30


def list_active_templates(db: Session) -> list[TopicTemplate]:
    return (
        db.query(TopicTemplate)
        .filter(TopicTemplate.is_active.is_(True))
        .order_by(TopicTemplate.sort_order.asc(), TopicTemplate.name.asc())
        .all()
    )


def template_performance(db: Session, template_id: uuid.UUID, since_days: int = PERFORMANCE_LOOKBACK_DAYS):
    """Aggregates ThemeMatch.status/relevance_score across every ThemeWatch created from
    this template, across the whole workspace — see
    docs/topics-ux-improvements-planning.html §2.4. Admin-only curation tool, not shown
    to end users; the cross-workspace read is safe since it only touches aggregate
    counts/scores, never article content (see that section's acceptance criteria)."""
    since = datetime.now(timezone.utc) - timedelta(days=since_days)

    adoption_count = (
        db.query(ThemeWatch).filter(ThemeWatch.created_from_template_id == template_id).count()
    )

    rows = (
        db.query(
            func.count(ThemeMatch.id),
            func.sum(case((ThemeMatch.status == SignalStatus.DISMISSED, 1), else_=0)),
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
            func.avg(ThemeMatch.relevance_score),
        )
        .join(ThemeWatch, ThemeMatch.theme_watch_id == ThemeWatch.id)
        .filter(
            ThemeWatch.created_from_template_id == template_id,
            ThemeMatch.fetched_at >= since,
            ThemeMatch.skip_reason.is_(None),
        )
        .first()
    )
    matches_total, dismissed, rated, avg_score = rows if rows else (0, 0, 0, None)
    matches_total = matches_total or 0
    dismissed = dismissed or 0
    rated = rated or 0

    return {
        "template_id": template_id,
        "adoption_count": adoption_count,
        "matches_total": matches_total,
        "dismiss_rate": (dismissed / rated) if rated > 0 else None,
        "avg_relevance_score": float(avg_score) if avg_score is not None else None,
    }
