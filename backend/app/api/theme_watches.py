import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.audit import log_event
from app.core.config import get_settings
from app.core.limiter import limiter
from app.db.session import get_db
from app.models.ingestion_run import TRIGGER_MANUAL
from app.models.theme_follow import ThemeFollow
from app.models.theme_watch import ThemeWatch
from app.models.user import User, UserRole
from app.schemas.ingestion import IngestionRunStatusResponse
from app.schemas.theme_watch import (
    ThemeFollowerResponse,
    ThemeQueryPreviewRequest,
    ThemeQueryPreviewResponse,
    ThemeWatchCreate,
    ThemeWatchResponse,
    ThemeWatchUpdate,
)
from app.services.google_news_rss_client import GoogleNewsRSSClient
from app.services.ingestion_runs import (
    create_run,
    execute_ingestion_run,
    get_running_run,
    to_status_response,
)
from app.services.news_client import NewsClientError
from app.services.news_query import build_theme_query
from app.services.theme_follows import (
    ensure_follow,
    find_theme_by_name,
    get_follow,
    get_or_create_theme,
    remove_follow,
    to_response,
)
from app.services.workspace_settings import (
    enforce_trigger_cooldown,
    get_or_create_workspace_settings,
)

router = APIRouter(prefix="/theme-watches", tags=["theme-watches"])

# How far back the live preview looks — short enough to answer "does this query find
# anything recent" quickly, independent of a topic's eventual lookback/schedule.
PREVIEW_LOOKBACK_DAYS = 7
PREVIEW_SAMPLE_HEADLINES = 5


def _get_or_404(db: Session, theme_watch_id: uuid.UUID) -> ThemeWatch:
    theme = db.get(ThemeWatch, theme_watch_id)
    if theme is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Theme watch not found")
    return theme


@router.get("", response_model=list[ThemeWatchResponse])
def list_theme_watches(
    scope: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ThemeWatchResponse]:
    if scope == "all":
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="scope=all is admin-only"
            )
        themes = db.query(ThemeWatch).order_by(ThemeWatch.created_at.desc()).all()
        own_follows = {
            follow.theme_watch_id: follow
            for follow in db.query(ThemeFollow).filter(ThemeFollow.user_id == current_user.id)
        }
        return [to_response(db, theme, own_follows.get(theme.id)) for theme in themes]

    rows = (
        db.query(ThemeWatch, ThemeFollow)
        .join(ThemeFollow, ThemeFollow.theme_watch_id == ThemeWatch.id)
        .filter(ThemeFollow.user_id == current_user.id)
        .order_by(ThemeWatch.created_at.desc())
        .all()
    )
    return [to_response(db, theme, follow) for theme, follow in rows]


@router.post("", response_model=ThemeWatchResponse, status_code=status.HTTP_201_CREATED)
def create_theme_watch(
    payload: ThemeWatchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ThemeWatchResponse:
    # Surfaces the shared-catalog dedupe as an explicit choice instead of silently
    # merging into whatever already exists under this name (see
    # docs/topics-ux-improvements-planning.html §1.4). confirm_merge=True (re-submitted
    # by the frontend after the user picks "Follow existing topic") skips straight past
    # this and falls through to get_or_create_theme's own dedupe below.
    if not payload.confirm_merge:
        existing = find_theme_by_name(db, payload.name)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "duplicate_name",
                    "existing_id": str(existing.id),
                    "existing_query_terms": existing.query_terms,
                },
            )

    workspace_settings = get_or_create_workspace_settings(db)
    active_count = db.query(ThemeWatch).filter(ThemeWatch.is_active.is_(True)).count()
    if active_count >= workspace_settings.max_active_theme_watches:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Workspace already has {active_count} active theme watches "
                f"(limit: {workspace_settings.max_active_theme_watches}). Pause or delete one first."
            ),
        )

    theme = get_or_create_theme(
        db,
        name=payload.name,
        query_terms=payload.query_terms,
        exclude_terms=payload.exclude_terms,
        industry=payload.industry,
        created_by=current_user.id,
        google_news_source_allowlist=payload.google_news_source_allowlist,
        google_news_country=payload.google_news_country,
        google_news_language=payload.google_news_language,
    )
    follow = ensure_follow(
        db, user_id=current_user.id, theme_watch_id=theme.id, assigned_by=current_user.id
    )
    db.commit()
    db.refresh(theme)
    db.refresh(follow)
    return to_response(db, theme, follow)


@router.post("/preview", response_model=ThemeQueryPreviewResponse)
@limiter.limit("30/hour")
def preview_theme_query(
    payload: ThemeQueryPreviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ThemeQueryPreviewResponse:
    """Live, unsaved-query preview against Google News RSS — no ThemeMatch/ThemeWatch
    rows are created and no AI call is made, so this is free and near-instant (see
    docs/topics-ux-improvements-planning.html §1.3). Works with a theme_watch_id (editing)
    or without one (initial creation), since it takes the raw fields, not an id."""
    workspace_settings = get_or_create_workspace_settings(db)
    if not workspace_settings.google_news_rss_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Google News RSS is disabled for this workspace, and it is the only news "
                "source topics can use. Enable it under Settings > News sources."
            ),
        )

    sources = list(
        dict.fromkeys(
            [*(workspace_settings.google_news_source_allowlist or []),
             *(payload.google_news_source_allowlist or [])]
        )
    )
    query = build_theme_query(payload.query_terms, sources, payload.exclude_terms)
    client = GoogleNewsRSSClient(
        country=workspace_settings.google_news_rss_country,
        language=workspace_settings.google_news_rss_language,
    )
    since = datetime.now(timezone.utc) - timedelta(days=PREVIEW_LOOKBACK_DAYS)
    try:
        fetched = client.fetch_articles(
            since=since,
            query_override=query,
            country=payload.google_news_country,
            language=payload.google_news_language,
        )
    except NewsClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Preview fetch failed: {exc}"
        )

    return ThemeQueryPreviewResponse(
        article_count=len(fetched),
        sample_headlines=[item.title for item in fetched[:PREVIEW_SAMPLE_HEADLINES]],
    )


@router.patch("/{theme_watch_id}", response_model=ThemeWatchResponse)
def update_theme_watch(
    theme_watch_id: uuid.UUID,
    payload: ThemeWatchUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ThemeWatchResponse:
    theme = _get_or_404(db, theme_watch_id)
    follow = get_follow(db, current_user.id, theme_watch_id)
    if current_user.role != UserRole.ADMIN and follow is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not following this theme"
        )
    # Same creator-or-admin gate as TargetCompany (v1 roadmap §5) — applied from day one
    # here rather than shipping the gap again (see docs/theme-search-planning.html §2.1).
    if current_user.role != UserRole.ADMIN and theme.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only this theme's creator or an admin can edit it",
        )

    updates = payload.model_dump(exclude_unset=True)
    if updates.get("is_active") and not theme.is_active:
        workspace_settings = get_or_create_workspace_settings(db)
        active_count = db.query(ThemeWatch).filter(ThemeWatch.is_active.is_(True)).count()
        if active_count >= workspace_settings.max_active_theme_watches:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Workspace already has {active_count} active theme watches "
                    f"(limit: {workspace_settings.max_active_theme_watches}). Pause or delete one first."
                ),
            )

    for field, value in updates.items():
        setattr(theme, field, value)
    db.commit()
    db.refresh(theme)
    return to_response(db, theme, follow)


@router.delete("/{theme_watch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_theme_watch(
    theme_watch_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    theme = _get_or_404(db, theme_watch_id)
    if current_user.role == UserRole.ADMIN:
        db.delete(theme)
        db.commit()
        log_event(
            "admin_theme_deleted", user_id=str(current_user.id), theme_watch_id=str(theme_watch_id)
        )
        return

    follow = get_follow(db, current_user.id, theme_watch_id)
    if follow is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not following this theme"
        )
    remove_follow(db, current_user.id, theme_watch_id)
    db.commit()


@router.post("/{theme_watch_id}/mute", response_model=ThemeWatchResponse)
def toggle_mute(
    theme_watch_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ThemeWatchResponse:
    theme = _get_or_404(db, theme_watch_id)
    follow = get_follow(db, current_user.id, theme_watch_id)
    if follow is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Not following this theme"
        )
    follow.is_muted = not follow.is_muted
    db.commit()
    db.refresh(follow)
    return to_response(db, theme, follow)


@router.post("/{theme_watch_id}/run-now", response_model=IngestionRunStatusResponse, status_code=202)
@limiter.limit("20/hour")
def run_theme_now(
    theme_watch_id: uuid.UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IngestionRunStatusResponse:
    """Fetches news for this one theme only, without waiting for the next scheduled run or
    triggering a full pass over every target company.

    Open to any follower of the theme (not admin-only): the same people who can create a
    theme and edit its query terms are the ones who need to see whether a query change
    actually works, and iterating on a query via "wait up to N hours for the scheduler" is
    not a workable loop. The cost is bounded the same way the full run is — one Google News
    request plus at most max_articles_per_theme_per_run summarizations.
    """
    theme = _get_or_404(db, theme_watch_id)
    if current_user.role != UserRole.ADMIN and get_follow(db, current_user.id, theme_watch_id) is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not following this theme"
        )
    if not theme.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This theme is paused. Resume it before fetching news for it.",
        )

    workspace_settings = get_or_create_workspace_settings(db)
    if not workspace_settings.google_news_rss_enabled:
        # Fails loudly instead of starting a run that provably cannot fetch anything —
        # Google News RSS is the only news source themes can use.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Google News RSS is disabled for this workspace, and it is the only news "
                "source themes can use. Enable it under Settings > News sources."
            ),
        )

    # A run already in flight (this theme's, another theme's, or a full one) is handed back
    # as-is rather than started alongside — same rule as POST /ingestion/run-now, and it
    # keeps the frontend's single progress bar honest. Checked before the cooldown is
    # stamped so a click that merely joins an existing run doesn't burn this theme's clock.
    existing_run = get_running_run(db)
    if existing_run is not None:
        return to_status_response(existing_run)

    # Per-theme clock, deliberately not the workspace-wide last_manual_ingestion_at: one
    # theme's fetch shouldn't lock out another theme's, nor the full-run button.
    enforce_trigger_cooldown(
        db, theme, "last_manual_run_at", get_settings().manual_trigger_cooldown_seconds
    )

    run = create_run(
        db,
        trigger=TRIGGER_MANUAL,
        triggered_by_user_id=current_user.id,
        theme_watch_id=theme.id,
    )
    background_tasks.add_task(execute_ingestion_run, run.id)
    log_event(
        "theme_manual_run_triggered",
        request=request,
        actor_id=str(current_user.id),
        theme_watch_id=str(theme_watch_id),
        run_id=str(run.id),
    )
    return to_status_response(run)


@router.get("/{theme_watch_id}/followers", response_model=list[ThemeFollowerResponse])
def list_followers(
    theme_watch_id: uuid.UUID,
    db: Session = Depends(get_db),
    _current_admin: User = Depends(require_admin),
) -> list[ThemeFollowerResponse]:
    _get_or_404(db, theme_watch_id)
    rows = (
        db.query(ThemeFollow, User)
        .join(User, ThemeFollow.user_id == User.id)
        .filter(ThemeFollow.theme_watch_id == theme_watch_id)
        .all()
    )
    return [
        ThemeFollowerResponse(
            user_id=user.id,
            email=user.email,
            name=user.name,
            is_muted=follow.is_muted,
            assigned_by=follow.assigned_by,
            created_at=follow.created_at,
        )
        for follow, user in rows
    ]
