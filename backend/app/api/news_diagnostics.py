"""Admin-only diagnostics for the news-fetch pipeline: a query preview that spends no AI
budget, and per-publisher precision stats.

The preview is the tool that turns every tuning question in
docs/google-news-quality-planning.html from an argument into an experiment — it runs
exactly one real fetch and reports what came back and why each entry would have been
kept or dropped, without embedding, triaging, summarizing, or writing a single row to
`articles`.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.limiter import limiter
from app.db.session import get_db
from app.models.article import ArticleSource
from app.models.user import User
from app.schemas.news_diagnostics import (
    DomainPrecisionStat,
    QueryPreviewEntry,
    QueryPreviewRequest,
    QueryPreviewResponse,
)
from app.services.google_news_rss_client import GoogleNewsRSSClient
from app.services.news_client import NewsClientError
from app.services.news_query import (
    MAX_QUERY_WORDS,
    article_mentions_company,
    build_google_news_query,
    build_theme_query,
    google_when_operator,
    resolve_allowlist,
    resolve_denylist,
)
from app.services.news_rate_limiter import HeadroomStatus, check_headroom
from app.services.news_usage import log_usage
from app.services.source_precision import get_domain_precision_stats
from app.services.workspace_settings import get_or_create_workspace_settings

router = APIRouter(prefix="/news-diagnostics", tags=["news-diagnostics"])


@router.post("/google-news/preview", response_model=QueryPreviewResponse)
@limiter.limit("10/minute")
def preview_google_news_query(
    request: Request,
    payload: QueryPreviewRequest,
    db: Session = Depends(get_db),
    _current_admin: User = Depends(require_admin),
) -> QueryPreviewResponse:
    """Runs one Google News query against a provisional configuration and reports the
    outcome of every entry it returned.

    Rate-limited and admin-gated for the same reason /ingestion/run-now is: it triggers a
    real outbound request on demand. It counts against the configured Google News ceiling
    like any other call, so a preview can't be used to sidestep the limiter.
    """
    workspace_settings = get_or_create_workspace_settings(db)

    status_ = check_headroom(
        db,
        ArticleSource.GOOGLE_NEWS_RSS,
        per_minute_limit=workspace_settings.google_news_rss_max_requests_per_minute,
        per_day_limit=None,
    )
    if status_ is not HeadroomStatus.OK:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Google News RSS is at its configured rate limit — try again shortly.",
        )

    lookback_hours = max(payload.lookback_hours, 1)
    since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    # None on the payload means "whatever the workspace is configured to do", so a preview
    # reflects the real pipeline by default but can be used to A/B the operator itself.
    time_operator_enabled = (
        workspace_settings.google_news_time_operator_enabled
        if payload.time_operator_enabled is None
        else payload.time_operator_enabled
    )
    when = google_when_operator(since) if time_operator_enabled else None

    allow_sites = resolve_allowlist(
        payload.source_allowlist, workspace_settings.google_news_source_allowlist
    )
    deny_sites = resolve_denylist(
        payload.source_denylist, workspace_settings.google_news_source_denylist
    )

    if payload.query_terms:
        query, truncated = build_theme_query(
            payload.query_terms,
            exclude_terms=payload.exclude_terms,
            allow_sites=allow_sites,
            deny_sites=deny_sites,
            when=when,
        )
    else:
        query, truncated = build_google_news_query(
            name=payload.name or "",
            aliases=payload.aliases,
            context_terms=payload.context_terms,
            exclude_terms=payload.exclude_terms,
            allow_sites=allow_sites,
            deny_sites=deny_sites,
            when=when,
            require_name_in_title=payload.require_name_in_title,
        )

    country = payload.country or workspace_settings.google_news_rss_country
    language = payload.language or workspace_settings.google_news_rss_language
    client = GoogleNewsRSSClient(country=country, language=language)

    try:
        outcome = client.fetch_articles(since=since, query_override=query)
    except NewsClientError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

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

    # The grounding stage the real pipeline would apply next, reported per entry rather
    # than applied — the point of a preview is to see what would be dropped and why.
    identity = [payload.name, *(payload.aliases or [])] if payload.name else []
    entries = []
    for article in outcome.articles:
        grounded = (
            True
            if not identity
            else article_mentions_company(
                title=article.title,
                description=article.description,
                full_content=None,
                name=payload.name or "",
                aliases=payload.aliases,
            )
        )
        entries.append(
            QueryPreviewEntry(
                title=article.title,
                source_name=article.source_name,
                url=article.url,
                published_at=article.published_at,
                outcome="kept" if grounded else "not_grounded",
            )
        )

    return QueryPreviewResponse(
        query_text=query,
        word_count=len(query.split()),
        max_words=MAX_QUERY_WORDS,
        truncated=truncated,
        country=country,
        language=language,
        entries_raw=outcome.articles_raw,
        drop_counts=outcome.drop_counts,
        entries=entries,
    )


@router.get("/source-precision", response_model=list[DomainPrecisionStat])
def get_source_precision(
    window_days: int = 30,
    db: Session = Depends(get_db),
    _current_admin: User = Depends(require_admin),
) -> list[DomainPrecisionStat]:
    """Which publishers are producing signals worth keeping, and which are only producing
    triage-outs and dismissals — the data behind the denylist suggestions in Settings."""
    return [
        DomainPrecisionStat(**row)
        for row in get_domain_precision_stats(db, window_days=max(1, min(window_days, 365)))
    ]
