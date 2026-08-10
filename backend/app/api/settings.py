from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.audit import log_event
from app.core.config import get_settings
from app.core.crypto import encrypt_secret
from app.db.session import get_db
from app.models.user import User
from app.models.workspace_settings import WorkspaceSettings
from app.schemas.settings import (
    PublicWorkspaceSettingsResponse,
    WorkspaceSettingsResponse,
    WorkspaceSettingsUpdate,
)
from app.services import scheduler
from app.services.workspace_settings import (
    get_mistral_api_key_status,
    get_newsdata_api_key_status,
    get_or_create_workspace_settings,
)

router = APIRouter(prefix="/settings", tags=["settings"])


def _to_response(settings: WorkspaceSettings) -> WorkspaceSettingsResponse:
    app_settings = get_settings()
    mistral_key_status = get_mistral_api_key_status(settings, app_settings)
    newsdata_key_status = get_newsdata_api_key_status(settings, app_settings)
    return WorkspaceSettingsResponse(
        id=settings.id,
        company_name=settings.company_name,
        offering_description=settings.offering_description,
        digest_send_time=settings.digest_send_time,
        max_articles_per_company_per_run=settings.max_articles_per_company_per_run,
        main_language=settings.main_language,
        mistral_model=settings.mistral_model,
        mistral_triage_model=settings.mistral_triage_model,
        mistral_embed_model=settings.mistral_embed_model,
        mistral_triage_enabled=settings.mistral_triage_enabled,
        mistral_dedupe_similarity_threshold=settings.mistral_dedupe_similarity_threshold,
        mistral_api_key_configured=mistral_key_status.configured,
        mistral_api_key_source=mistral_key_status.source,
        mistral_api_key_last4=mistral_key_status.last4,
        newsapi_enabled=settings.newsapi_enabled,
        newsapi_max_requests_per_day=settings.newsapi_max_requests_per_day,
        google_news_rss_enabled=settings.google_news_rss_enabled,
        google_news_rss_country=settings.google_news_rss_country,
        google_news_rss_language=settings.google_news_rss_language,
        google_news_rss_max_requests_per_minute=settings.google_news_rss_max_requests_per_minute,
        google_news_source_allowlist=settings.google_news_source_allowlist,
        google_news_source_denylist=settings.google_news_source_denylist,
        google_news_time_operator_enabled=settings.google_news_time_operator_enabled,
        google_news_query_strategy=settings.google_news_query_strategy,
        google_news_resolve_urls_enabled=settings.google_news_resolve_urls_enabled,
        google_news_fetch_snippets_enabled=settings.google_news_fetch_snippets_enabled,
        max_enrichment_fetches_per_run=settings.max_enrichment_fetches_per_run,
        max_enrichment_seconds_per_run=settings.max_enrichment_seconds_per_run,
        theme_news_sources=settings.theme_news_sources,
        max_theme_requests_per_run_per_source=settings.max_theme_requests_per_run_per_source,
        newsdata_enabled=settings.newsdata_enabled,
        newsdata_api_key_configured=newsdata_key_status.configured,
        newsdata_api_key_source=newsdata_key_status.source,
        newsdata_api_key_last4=newsdata_key_status.last4,
        newsdata_full_content_enabled=settings.newsdata_full_content_enabled,
        newsdata_use_native_dedupe=settings.newsdata_use_native_dedupe,
        newsdata_backfill_days=settings.newsdata_backfill_days,
        newsdata_max_requests_per_day=settings.newsdata_max_requests_per_day,
        newsdata_max_requests_per_minute=settings.newsdata_max_requests_per_minute,
        max_articles_per_theme_per_run=settings.max_articles_per_theme_per_run,
        max_active_theme_watches=settings.max_active_theme_watches,
        theme_match_min_relevance_score=settings.theme_match_min_relevance_score,
    )


@router.get("", response_model=WorkspaceSettingsResponse)
def get_settings_endpoint(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> WorkspaceSettingsResponse:
    return _to_response(get_or_create_workspace_settings(db))


@router.get("/public", response_model=PublicWorkspaceSettingsResponse)
def get_public_settings(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> PublicWorkspaceSettingsResponse:
    """The handful of workspace capability flags every authenticated user needs in order to
    understand what the app can currently do for them — deliberately a separate, tiny
    response rather than relaxing GET /settings, which carries API-key status, provider
    quotas, and the AI configuration and must stay admin-only.

    Concretely: themes can only fetch via Google News RSS, so a non-admin whose topics
    silently return nothing had no way to find out that the source is switched off. Now the
    Themes page can say so, and say whether the workspace's news edition matches the market
    the topic is about.
    """
    settings = get_or_create_workspace_settings(db)
    return PublicWorkspaceSettingsResponse(
        google_news_rss_enabled=settings.google_news_rss_enabled,
        google_news_rss_country=settings.google_news_rss_country,
        google_news_rss_language=settings.google_news_rss_language,
        manual_trigger_cooldown_seconds=get_settings().manual_trigger_cooldown_seconds,
    )


@router.put("", response_model=WorkspaceSettingsResponse)
def update_settings(
    payload: WorkspaceSettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> WorkspaceSettingsResponse:
    settings = get_or_create_workspace_settings(db)
    settings.company_name = payload.company_name
    settings.offering_description = payload.offering_description
    settings.digest_send_time = payload.digest_send_time
    settings.max_articles_per_company_per_run = payload.max_articles_per_company_per_run
    settings.main_language = payload.main_language
    settings.mistral_model = payload.mistral_model
    settings.mistral_triage_model = payload.mistral_triage_model
    settings.mistral_embed_model = payload.mistral_embed_model
    settings.mistral_triage_enabled = payload.mistral_triage_enabled
    settings.mistral_dedupe_similarity_threshold = payload.mistral_dedupe_similarity_threshold

    settings.newsapi_enabled = payload.newsapi_enabled
    settings.newsapi_max_requests_per_day = payload.newsapi_max_requests_per_day
    settings.google_news_rss_enabled = payload.google_news_rss_enabled
    settings.google_news_rss_country = payload.google_news_rss_country
    settings.google_news_rss_language = payload.google_news_rss_language
    settings.google_news_rss_max_requests_per_minute = payload.google_news_rss_max_requests_per_minute
    settings.google_news_source_allowlist = payload.google_news_source_allowlist
    settings.google_news_source_denylist = payload.google_news_source_denylist
    settings.google_news_time_operator_enabled = payload.google_news_time_operator_enabled
    settings.google_news_query_strategy = payload.google_news_query_strategy
    settings.google_news_resolve_urls_enabled = payload.google_news_resolve_urls_enabled
    settings.google_news_fetch_snippets_enabled = payload.google_news_fetch_snippets_enabled
    settings.max_enrichment_fetches_per_run = payload.max_enrichment_fetches_per_run
    settings.max_enrichment_seconds_per_run = payload.max_enrichment_seconds_per_run
    settings.theme_news_sources = payload.theme_news_sources
    settings.max_theme_requests_per_run_per_source = payload.max_theme_requests_per_run_per_source
    settings.newsdata_enabled = payload.newsdata_enabled
    settings.newsdata_full_content_enabled = payload.newsdata_full_content_enabled
    settings.newsdata_use_native_dedupe = payload.newsdata_use_native_dedupe
    settings.newsdata_backfill_days = payload.newsdata_backfill_days
    settings.newsdata_max_requests_per_day = payload.newsdata_max_requests_per_day
    settings.newsdata_max_requests_per_minute = payload.newsdata_max_requests_per_minute
    settings.max_articles_per_theme_per_run = payload.max_articles_per_theme_per_run
    settings.max_active_theme_watches = payload.max_active_theme_watches
    settings.theme_match_min_relevance_score = payload.theme_match_min_relevance_score

    if payload.mistral_api_key is not None:
        # Stored encrypted (see app/core/crypto.py) — the "" clear-override sentinel
        # round-trips fine since encrypt_secret("") is itself "".
        settings.mistral_api_key = encrypt_secret(payload.mistral_api_key)
        # Never log the key itself — only whether this save set, cleared, or left it.
        log_event(
            "mistral_api_key_override_changed",
            request=request,
            actor_id=str(current_admin.id),
            key_set=bool(payload.mistral_api_key),
        )

    if payload.newsdata_api_key is not None:
        settings.newsdata_api_key = encrypt_secret(payload.newsdata_api_key)
        log_event(
            "newsdata_api_key_override_changed",
            request=request,
            actor_id=str(current_admin.id),
            key_set=bool(payload.newsdata_api_key),
        )

    db.commit()
    db.refresh(settings)
    scheduler.reschedule(settings.digest_send_time)
    return _to_response(settings)
