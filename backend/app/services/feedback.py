from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.signal import Signal, SignalStatus
from app.models.theme_match import ThemeMatch
from app.models.theme_watch import ThemeWatch
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


def refresh_theme_feedback_note(db: Session, theme_watch: ThemeWatch) -> None:
    """Per-topic variant of refresh_feedback_note — see
    docs/topics-ux-improvements-planning.html §3.1. Still rule-based/free (a SQL
    aggregation, no LLM call), scoped to this one topic's own ThemeMatch history rather
    than workspace-wide, since a dismiss pattern on one topic shouldn't bias another's
    prompts.

    ThemeMatch has no signal_type-equivalent categorical field the way Signal does, so
    extracted_company_name is used as a rough proxy for "what kind of content keeps
    getting dismissed" instead — a deliberately simple heuristic (see that section's
    acceptance criteria), not an attempt at semantic clustering.

    Deliberately grouped WITHOUT filtering out NULL extracted_company_name (an earlier
    version did): a NULL name means the article was topical/industry news with no single
    company at its center — exactly the "generic noise, not a company-specific signal"
    shape users report as the problem with topic templates. Excluding it meant the one
    dismiss-pattern learning loop that exists was structurally blind to the single
    dismissal pattern most relevant to that complaint. Grouping by a nullable column
    naturally produces a NULL group for that bucket, aggregated the same way as any named
    company.
    """
    since = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)

    rows = (
        db.query(
            ThemeMatch.extracted_company_name,
            func.count(ThemeMatch.id),
            func.sum(case((ThemeMatch.status == SignalStatus.DISMISSED, 1), else_=0)),
        )
        .filter(
            ThemeMatch.theme_watch_id == theme_watch.id,
            ThemeMatch.fetched_at >= since,
            ThemeMatch.status.in_(
                [SignalStatus.DISMISSED, SignalStatus.REVIEWED, SignalStatus.ARCHIVED]
            ),
        )
        .group_by(ThemeMatch.extracted_company_name)
        .all()
    )

    low_value_names = sorted(
        name
        for name, total, dismissed in rows
        if name is not None and total >= MIN_SAMPLE_SIZE and (dismissed / total) >= DISMISS_RATE_THRESHOLD
    )
    generic_row = next((row for row in rows if row[0] is None), None)
    generic_is_low_value = generic_row is not None and (
        generic_row[1] >= MIN_SAMPLE_SIZE and (generic_row[2] / generic_row[1]) >= DISMISS_RATE_THRESHOLD
    )

    note_parts = []
    if low_value_names:
        note_parts.append(
            f"Users have frequently dismissed matches mentioning these companies as "
            f"low-value for this topic: {', '.join(low_value_names)}. Only surface them "
            f"with relevance_score >= 4."
        )
    if generic_is_low_value:
        note_parts.append(
            "Users have frequently dismissed general/topical articles with no specific "
            "company mentioned as low-value for this topic. Be stricter when no company "
            "can be identified: only give relevance_score >= 4 to company-less articles "
            "with a clear, concrete business angle, not general industry commentary."
        )
    note = " ".join(note_parts)

    if note != theme_watch.ai_feedback_note:
        theme_watch.ai_feedback_note = note
        db.commit()
