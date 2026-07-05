from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.signal import Signal, SignalStatus
from app.models.workspace_settings import WorkspaceSettings

LOOKBACK_DAYS = 30
MIN_SAMPLE_SIZE = 5
DISMISS_RATE_THRESHOLD = 0.6


def refresh_feedback_note(db: Session, workspace_settings: WorkspaceSettings) -> None:
    """Recomputes a short steering note from dismissed-vs-reviewed signal patterns.

    Deliberately rule-based (plain aggregation in Python, no LLM call) rather than
    asking Mistral to analyze the pattern: it runs on every ingestion pass, so keeping
    it free avoids burning tokens on something a simple count already answers. The
    resulting note is short (one line) and only adds a small, fixed number of tokens to
    each future summarization prompt.
    """
    since = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)

    rows = (
        db.query(Signal.signal_type, Signal.status)
        .filter(
            Signal.created_at >= since,
            Signal.status.in_(
                [SignalStatus.DISMISSED, SignalStatus.REVIEWED, SignalStatus.ARCHIVED]
            ),
            Signal.signal_type.isnot(None),
        )
        .all()
    )

    totals: dict[str, int] = {}
    dismissed: dict[str, int] = {}
    for signal_type, status in rows:
        totals[signal_type] = totals.get(signal_type, 0) + 1
        if status == SignalStatus.DISMISSED:
            dismissed[signal_type] = dismissed.get(signal_type, 0) + 1

    low_value_types = sorted(
        signal_type
        for signal_type, total in totals.items()
        if total >= MIN_SAMPLE_SIZE
        and (dismissed.get(signal_type, 0) / total) >= DISMISS_RATE_THRESHOLD
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
