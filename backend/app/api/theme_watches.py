import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.audit import log_event
from app.core.config import get_settings
from app.core.limiter import limiter
from app.db.session import get_db
from app.models.article import ArticleSource
from app.models.ingestion_run import TRIGGER_MANUAL
from app.models.theme_follow import ThemeFollow
from app.models.theme_watch import ThemeWatch
from app.models.user import User, UserRole
from app.schemas.ingestion import IngestionRunStatusResponse
from app.schemas.theme_watch import (
    ThemeFollowerResponse,
    ThemeQueryPreviewRequest,
    ThemeQueryPreviewResponse,
    ThemeWatchBulkDeleteRequest,
    ThemeWatchBulkDeleteResult,
    ThemeWatchCreate,
    ThemeWatchResponse,
    ThemeWatchStatsResponse,
    ThemeWatchUpdate,
)
from app.schemas.topic_template import SuggestedTopicResponse
from app.services.ai_client import AIClient, AIClientError, TemplateExample
from app.services.google_news_rss_client import GoogleNewsRSSClient
from app.services.ingestion_runs import (
    create_run,
    execute_ingestion_run,
    get_running_run,
    to_status_response,
)
from app.services.news_client import NewsClientError
from app.services.news_query import (
    build_theme_query,
    google_when_operator,
    resolve_allowlist,
    resolve_denylist,
)
from app.services.news_rate_limiter import HeadroomStatus, check_headroom
from app.services.news_usage import log_usage
from app.services.theme_follows import (
    ensure_follow,
    find_theme_by_name,
    get_follow,
    get_or_create_theme,
    remove_follow,
    to_response,
)
from app.services.theme_watch_stats import get_theme_watch_stats
from app.services.topic_templates import list_active_templates
from app.services.workspace_settings import (
    enforce_manual_trigger_cooldown,
    enforce_trigger_cooldown,
    get_or_create_workspace_settings,
    resolve_mistral_api_key,
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
        google_news_source_denylist=payload.google_news_source_denylist,
        news_sources=payload.news_sources,
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
    or without one (initial creation), since it takes the raw fields, not an id.

    Shares the query builder with ingestion, so the preview reflects what the saved topic
    will actually fetch — exclusions, denylists and the freshness operator included. A
    preview built any other way would quietly disagree with the real thing, which is worse
    than no preview at all.

    It also makes a real outbound Google News request, so it goes through the same
    headroom check and usage log as every other call: the workspace's self-imposed ceiling
    exists because this feed has no official quota and can block a noisy client, and
    per-user previews are exactly the traffic that would otherwise be invisible to it.
    """
    workspace_settings = get_or_create_workspace_settings(db)
    if not workspace_settings.google_news_rss_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Google News RSS is disabled for this workspace, and it is the only news "
                "source topics can use. Enable it under Settings > News sources."
            ),
        )

    headroom = check_headroom(
        db,
        ArticleSource.GOOGLE_NEWS_RSS,
        per_minute_limit=workspace_settings.google_news_rss_max_requests_per_minute,
        per_day_limit=None,
    )
    if headroom is not HeadroomStatus.OK:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Google News is at this workspace's configured request limit — "
                "try the preview again shortly."
            ),
        )

    since = datetime.now(timezone.utc) - timedelta(days=PREVIEW_LOOKBACK_DAYS)
    query, _truncated = build_theme_query(
        payload.query_terms,
        exclude_terms=payload.exclude_terms,
        # Override semantics, matching a saved topic: an empty list means "search
        # everything", not "fall back to the workspace list".
        allow_sites=resolve_allowlist(
            payload.google_news_source_allowlist,
            workspace_settings.google_news_source_allowlist,
        ),
        deny_sites=resolve_denylist(
            payload.google_news_source_denylist,
            workspace_settings.google_news_source_denylist,
        ),
        when=(
            google_when_operator(since)
            if workspace_settings.google_news_time_operator_enabled
            else None
        ),
    )
    client = GoogleNewsRSSClient(
        country=workspace_settings.google_news_rss_country,
        language=workspace_settings.google_news_rss_language,
    )
    try:
        outcome = client.fetch_articles(
            since=since,
            query_override=query,
            country=payload.google_news_country,
            language=payload.google_news_language,
        )
    except NewsClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Preview fetch failed: {exc}"
        )

    log_usage(
        db,
        source=ArticleSource.GOOGLE_NEWS_RSS,
        call_type="preview",
        target_company_id=None,
        requests_used=outcome.requests_used,
        articles_returned=len(outcome.articles),
        query_text=outcome.query_text,
        articles_raw=outcome.articles_raw,
        drop_counts=outcome.drop_counts,
    )

    return ThemeQueryPreviewResponse(
        article_count=len(outcome.articles),
        sample_headlines=[item.title for item in outcome.articles[:PREVIEW_SAMPLE_HEADLINES]],
    )


@router.get("/suggestions", response_model=list[SuggestedTopicResponse])
@limiter.limit("10/hour")
def get_suggested_topics(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[SuggestedTopicResponse]:
    """AI-personalized topic suggestions grounded in the curated template library — see
    docs/topics-ux-improvements-planning.html §2.3. Computed on demand (a paid Mistral
    call), rate-limited like other manual-trigger endpoints rather than cached/scheduled.
    Never auto-creates anything — "Use this" on the frontend goes through the normal
    apply/create flow, same as picking a template by hand."""
    workspace_settings = get_or_create_workspace_settings(db)
    app_settings = get_settings()
    api_key = resolve_mistral_api_key(workspace_settings, app_settings)
    if not api_key or not workspace_settings.offering_description.strip():
        # No hallucinated generic suggestion without real grounding — point the user at
        # what's missing instead (see §2.3 acceptance criteria).
        return []

    templates = list_active_templates(db, language=workspace_settings.main_language)
    existing_names = [theme.name for theme in db.query(ThemeWatch).all()]

    ai_client = AIClient(
        api_key=api_key,
        model=workspace_settings.mistral_model,
        triage_model=workspace_settings.mistral_triage_model,
        embed_model=workspace_settings.mistral_embed_model,
        max_requests_per_second=app_settings.mistral_max_requests_per_second,
        max_retries=app_settings.mistral_max_retries,
    )
    try:
        suggestions, usage = ai_client.suggest_topics(
            offering_description=workspace_settings.offering_description,
            available_templates=[
                TemplateExample(
                    id=str(t.id),
                    name=t.name,
                    description=t.description,
                    category=t.category,
                    query_terms=t.query_terms,
                    exclude_terms=t.exclude_terms,
                )
                for t in templates
            ],
            existing_topic_names=existing_names,
            output_language=workspace_settings.main_language,
        )
    except AIClientError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    log_event(
        "topic_suggestions_generated",
        request=request,
        actor_id=str(current_user.id),
        suggestion_count=len(suggestions),
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
    )

    templates_by_id = {str(t.id): t for t in templates}
    return [
        SuggestedTopicResponse(
            name=s.name,
            query_terms=s.query_terms,
            exclude_terms=s.exclude_terms,
            rationale=s.rationale,
            based_on_template_id=s.based_on_template_id,
            based_on_template_name=(
                templates_by_id[s.based_on_template_id].name
                if s.based_on_template_id and s.based_on_template_id in templates_by_id
                else None
            ),
        )
        for s in suggestions
    ]


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


@router.post("/bulk-delete", response_model=ThemeWatchBulkDeleteResult)
def bulk_delete_theme_watches(
    payload: ThemeWatchBulkDeleteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ThemeWatchBulkDeleteResult:
    """Bulk variant of DELETE /{theme_watch_id} for the topic list's multi-select —
    mirrors POST /target-companies/bulk-delete's admin-hard-delete vs. follower-unfollow
    branching and not_found-doesn't-fail-the-batch convention exactly (see
    docs/topics-ux-improvements-planning.html §4.4)."""
    deleted = 0
    not_found = 0
    for theme_watch_id in payload.theme_watch_ids:
        theme = db.get(ThemeWatch, theme_watch_id)
        if theme is None:
            not_found += 1
            continue
        if current_user.role == UserRole.ADMIN:
            db.delete(theme)
            deleted += 1
            log_event(
                "admin_theme_deleted", user_id=str(current_user.id), theme_watch_id=str(theme_watch_id)
            )
            continue
        follow = get_follow(db, current_user.id, theme_watch_id)
        if follow is None:
            not_found += 1
            continue
        remove_follow(db, current_user.id, theme_watch_id)
        deleted += 1
    db.commit()
    return ThemeWatchBulkDeleteResult(deleted=deleted, not_found=not_found)


@router.post("/run-now", response_model=IngestionRunStatusResponse, status_code=202)
@limiter.limit("10/hour")
def run_followed_themes_now(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IngestionRunStatusResponse:
    """Fetches news for every active Theme this user follows in one go — the Themen
    page's "Alle Themen-Signale abrufen" button. Unlike POST /target-companies/run-now
    this takes no selection: it always means "all of mine", the same scope the per-theme
    button already covers one theme at a time (POST /{theme_watch_id}/run-now above).
    Muted follows and paused themes are excluded rather than failing the request — same
    tolerant style as the bulk-delete/bulk-run-now endpoints elsewhere.
    """
    eligible_ids = [
        row[0]
        for row in db.query(ThemeFollow.theme_watch_id)
        .join(ThemeWatch, ThemeWatch.id == ThemeFollow.theme_watch_id)
        .filter(
            ThemeFollow.user_id == current_user.id,
            ThemeFollow.is_muted.is_(False),
            ThemeWatch.is_active.is_(True),
        )
        .all()
    ]
    if not eligible_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You aren't following any active Themen to fetch.",
        )

    workspace_settings = get_or_create_workspace_settings(db)
    if not workspace_settings.google_news_rss_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Google News RSS is disabled for this workspace, and it is the only news "
                "source themes can use. Enable it under Settings > News sources."
            ),
        )

    # A run already in flight (a theme's, a company's, or a full one) is handed back as-is
    # rather than started alongside — same rule as POST /ingestion/run-now. Checked before
    # the cooldown is stamped so a click that merely joins an existing run doesn't burn
    # this workspace's clock.
    existing_run = get_running_run(db)
    if existing_run is not None:
        return to_status_response(existing_run)

    # Workspace-wide clock, not the per-theme one enforce_trigger_cooldown uses for a
    # single theme below: this button fetches every one of the caller's themes at once,
    # so it's costed and throttled like the other workspace-wide triggers (the full run,
    # the companies bulk run-now).
    enforce_manual_trigger_cooldown(
        db, workspace_settings, "last_manual_ingestion_at", get_settings().manual_trigger_cooldown_seconds
    )

    run = create_run(
        db,
        trigger=TRIGGER_MANUAL,
        triggered_by_user_id=current_user.id,
        theme_watch_ids=eligible_ids,
    )
    background_tasks.add_task(execute_ingestion_run, run.id)
    log_event(
        "themes_manual_run_triggered",
        request=request,
        actor_id=str(current_user.id),
        theme_count=len(eligible_ids),
        run_id=str(run.id),
    )
    return to_status_response(run)


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


@router.post("/{theme_watch_id}/digest", response_model=ThemeWatchResponse)
def toggle_digest_inclusion(
    theme_watch_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ThemeWatchResponse:
    """Opt this follow's matches in/out of the daily digest email — see
    docs/topics-ux-improvements-planning.html §4.3. Same per-follow shape as /mute."""
    theme = _get_or_404(db, theme_watch_id)
    follow = get_follow(db, current_user.id, theme_watch_id)
    if follow is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Not following this theme"
        )
    follow.include_in_digest = not follow.include_in_digest
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


@router.get("/{theme_watch_id}/stats", response_model=ThemeWatchStatsResponse)
def get_theme_watch_stats_endpoint(
    theme_watch_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ThemeWatchStatsResponse:
    """Per-topic health snapshot (§3.2) — same visibility rule as everything else on a
    topic: any follower, or an admin, not just the creator."""
    theme = _get_or_404(db, theme_watch_id)
    if current_user.role != UserRole.ADMIN and get_follow(db, current_user.id, theme_watch_id) is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not following this theme"
        )
    return get_theme_watch_stats(db, theme.id)


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
