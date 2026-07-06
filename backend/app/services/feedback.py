from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.signal import Signal, SignalStatus
from app.models.workspace_settings import WorkspaceSettings

LOOKBACK_DAYS = 30
MIN_SAMPLE_SIZE = 5
DISMISS_RATE_THRESHOLD = 0.6


def refresh_feedback_note(db: Session, workspace_settings: WorkspaceSettings) -> None:
    """Recomputes a short steering note from dismissed-vs-reviewed signal patterns.

    Deliberately rule-based (a SQL aggregation, no LLM call) rather than asking Mistral
    to analyze the pattern: it runs on every ingestion pass, so keeping it free avoids
    burning tokens on something a GROUP BY already answers. The resulting note is short
    (one line) and only adds a small, fixed number of tokens to each future
    summarization prompt.
    """
    since = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)

    rows = (
        db.query(
            Signal.signal_type,
            func.count(Signal.id),
            func.sum(case((Signal.status == SignalStatus.DISMISSED, 1), else_=0)),
        )
        .filter(
            Signal.created_at >= since,
            Signal.status.in_(
                [SignalStatus.DISMISSED, SignalStatus.REVIEWED, SignalStatus.ARCHIVED]
            ),
            Signal.signal_type.isnot(None),
        )
        .group_by(Signal.signal_type)
        .all()
    )

    low_value_types = sorted(
        signal_type
        for signal_type, total, dismissed in rows
        if total >= MIN_SAMPLE_SIZE and (dismissed / total) >= DISMISS_RATE_THRESHOLD
    )

    note = (
        f"Users have frequently dismissed these signal types as low-value: "
        f"{', '.join(low_value_types)}. Only surface them with relevance_score >= 4."
        if low_value_types
        else ""
    )

    if note != workspace_settings.ai_feedback_note:
        workspace_settings.ai_feedback_note = note
        db.commit()
