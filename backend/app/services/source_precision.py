"""Per-publisher precision stats, so an admin can see which sources are spending the AI
budget without producing anything useful (see docs/google-news-quality-planning.html §10).

Same rule-based, no-LLM-call philosophy as services/feedback.py, which already derives a
steering note from dismissal patterns — this adds the *domain* dimension alongside that
existing category dimension, and its output feeds a one-click denylist action rather than
a prompt.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.article import Article
from app.models.signal import Signal, SignalStatus

DEFAULT_WINDOW_DAYS = 30
# Below this, the ratios are noise — three articles from a publisher that happened to be
# off-topic says nothing about the publisher.
MIN_ARTICLES_FOR_VERDICT = 5
# Fraction of a domain's articles that must have been triaged out or dismissed before it
# is worth suggesting as a denylist candidate.
DENYLIST_SUGGESTION_THRESHOLD = 0.8


def get_domain_precision_stats(
    db: Session, *, window_days: int = DEFAULT_WINDOW_DAYS, limit: int = 25
) -> list[dict]:
    """Per-source_name counts over the window, worst precision first.

    Grouped by Article.source_name (the publisher as the provider named it) rather than by
    URL host: it's what the UI already shows per signal, and for Google News the stored URL
    is a redirect whose host is always news.google.com until Phase 4 resolution is enabled.
    """
    since = datetime.now(timezone.utc) - timedelta(days=window_days)

    rows = (
        db.query(
            Article.source_name.label("source_name"),
            func.count(Article.id).label("articles"),
            func.sum(case((Article.skip_reason == "triaged_out", 1), else_=0)).label("triaged_out"),
            func.sum(case((Article.skip_reason == "duplicate", 1), else_=0)).label("duplicates"),
            func.sum(case((Signal.id.isnot(None), 1), else_=0)).label("signals"),
            func.sum(case((Signal.status == SignalStatus.DISMISSED, 1), else_=0)).label("dismissed"),
        )
        .outerjoin(Signal, Signal.article_id == Article.id)
        .filter(Article.fetched_at >= since)
        .group_by(Article.source_name)
        .all()
    )

    stats = []
    for row in rows:
        articles = row.articles or 0
        wasted = (row.triaged_out or 0) + (row.dismissed or 0)
        kept = (row.signals or 0) - (row.dismissed or 0)
        # Duplicates are excluded from the denominator: a syndicated repost being
        # recognised as a duplicate is the pipeline working, not the publisher being bad.
        judged = articles - (row.duplicates or 0)
        waste_ratio = (wasted / judged) if judged else 0.0
        stats.append(
            {
                "source_name": row.source_name,
                "articles": articles,
                "signals_kept": max(kept, 0),
                "dismissed": row.dismissed or 0,
                "triaged_out": row.triaged_out or 0,
                "duplicates": row.duplicates or 0,
                "waste_ratio": round(waste_ratio, 3),
                "denylist_suggested": (
                    judged >= MIN_ARTICLES_FOR_VERDICT and waste_ratio >= DENYLIST_SUGGESTION_THRESHOLD
                ),
            }
        )

    stats.sort(key=lambda row: (row["waste_ratio"], row["articles"]), reverse=True)
    return stats[:limit]
