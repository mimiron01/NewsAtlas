import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.theme_follow import ThemeFollow
from app.models.theme_watch import ThemeWatch
from app.schemas.theme_watch import ThemeWatchResponse


def find_theme_by_name(db: Session, name: str) -> ThemeWatch | None:
    """Case-insensitive lookup used by the create endpoint to surface a duplicate-name
    confirmation before merging (see docs/topics-ux-improvements-planning.html §1.4),
    rather than the silent merge get_or_create_theme performs on its own."""
    return (
        db.query(ThemeWatch)
        .filter(func.lower(ThemeWatch.name) == name.strip().lower())
        .first()
    )


def get_or_create_theme(
    db: Session,
    *,
    name: str,
    query_terms: list[str],
    industry: str | None,
    created_by: uuid.UUID,
    exclude_terms: list[str] | None = None,
    google_news_source_allowlist: list[str] | None = None,
    google_news_country: str | None = None,
    google_news_language: str | None = None,
    created_from_template_id: uuid.UUID | None = None,
) -> ThemeWatch:
    """Case-insensitive dedupe by name — mirrors get_or_create_company exactly (see
    docs/theme-search-planning.html §1: shared catalog, same dedupe convention). Callers
    that need to distinguish "found existing" from "created new" (to show the duplicate
    confirmation in §1.4) should call find_theme_by_name first instead of relying on this
    function's return value alone."""
    existing = find_theme_by_name(db, name)
    if existing is not None:
        return existing
    theme = ThemeWatch(
        name=name,
        query_terms=query_terms,
        exclude_terms=exclude_terms or [],
        industry=industry,
        created_by=created_by,
        google_news_source_allowlist=google_news_source_allowlist or [],
        google_news_country=google_news_country,
        google_news_language=google_news_language,
        created_from_template_id=created_from_template_id,
    )
    db.add(theme)
    db.flush()
    return theme


def get_follow(db: Session, user_id: uuid.UUID, theme_watch_id: uuid.UUID) -> ThemeFollow | None:
    return (
        db.query(ThemeFollow)
        .filter(ThemeFollow.user_id == user_id, ThemeFollow.theme_watch_id == theme_watch_id)
        .first()
    )


def ensure_follow(
    db: Session,
    *,
    user_id: uuid.UUID,
    theme_watch_id: uuid.UUID,
    assigned_by: uuid.UUID,
) -> ThemeFollow:
    follow = get_follow(db, user_id, theme_watch_id)
    if follow is not None:
        return follow
    follow = ThemeFollow(user_id=user_id, theme_watch_id=theme_watch_id, assigned_by=assigned_by)
    db.add(follow)
    db.flush()
    return follow


def follower_count(db: Session, theme_watch_id: uuid.UUID) -> int:
    return db.query(ThemeFollow).filter(ThemeFollow.theme_watch_id == theme_watch_id).count()


def remove_follow(db: Session, user_id: uuid.UUID, theme_watch_id: uuid.UUID) -> bool:
    """Deletes the follow row; hard-deletes the underlying theme if it was the last
    follower. Returns True if the theme was hard-deleted."""
    follow = get_follow(db, user_id, theme_watch_id)
    if follow is None:
        return False
    db.delete(follow)
    db.flush()
    if follower_count(db, theme_watch_id) == 0:
        theme = db.get(ThemeWatch, theme_watch_id)
        if theme is not None:
            db.delete(theme)
        return True
    return False


def to_response(
    db: Session, theme: ThemeWatch, follow: ThemeFollow | None
) -> ThemeWatchResponse:
    return ThemeWatchResponse(
        id=theme.id,
        name=theme.name,
        query_terms=theme.query_terms,
        exclude_terms=theme.exclude_terms,
        industry=theme.industry,
        is_active=theme.is_active,
        google_news_source_allowlist=theme.google_news_source_allowlist,
        google_news_country=theme.google_news_country,
        google_news_language=theme.google_news_language,
        last_manual_run_at=theme.last_manual_run_at,
        created_by=theme.created_by,
        is_muted=follow.is_muted if follow is not None else None,
        follower_count=follower_count(db, theme.id),
        created_from_template_id=theme.created_from_template_id,
    )
