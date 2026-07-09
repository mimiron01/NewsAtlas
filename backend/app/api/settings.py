from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.audit import log_event
from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import User
from app.models.workspace_settings import WorkspaceSettings
from app.schemas.settings import WorkspaceSettingsResponse, WorkspaceSettingsUpdate
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
        ingestion_interval_hours=settings.ingestion_interval_hours,
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
        newsdata_enabled=settings.newsdata_enabled,
        newsdata_api_key_configured=newsdata_key_status.configured,
        newsdata_api_key_source=newsdata_key_status.source,
        newsdata_api_key_last4=newsdata_key_status.last4,
        newsdata_full_content_enabled=settings.newsdata_full_content_enabled,
        newsdata_use_native_dedupe=settings.newsdata_use_native_dedupe,
        newsdata_backfill_days=settings.newsdata_backfill_days,
        newsdata_max_requests_per_day=settings.newsdata_max_requests_per_day,
        newsdata_max_requests_per_minute=settings.newsdata_max_requests_per_minute,
    )


@router.get("", response_model=WorkspaceSettingsResponse)
def get_settings_endpoint(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> WorkspaceSettingsResponse:
    return _to_response(get_or_create_workspace_settings(db))


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
    settings.ingestion_interval_hours = payload.ingestion_interval_hours
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
    settings.newsdata_enabled = payload.newsdata_enabled
    settings.newsdata_full_content_enabled = payload.newsdata_full_content_enabled
    settings.newsdata_use_native_dedupe = payload.newsdata_use_native_dedupe
    settings.newsdata_backfill_days = payload.newsdata_backfill_days
    settings.newsdata_max_requests_per_day = payload.newsdata_max_requests_per_day
    settings.newsdata_max_requests_per_minute = payload.newsdata_max_requests_per_minute

    if payload.mistral_api_key is not None:
        settings.mistral_api_key = payload.mistral_api_key
        # Never log the key itself — only whether this save set, cleared, or left it.
        log_event(
            "mistral_api_key_override_changed",
            request=request,
            actor_id=str(current_admin.id),
            key_set=bool(payload.mistral_api_key),
        )

    if payload.newsdata_api_key is not None:
        settings.newsdata_api_key = payload.newsdata_api_key
        log_event(
            "newsdata_api_key_override_changed",
            request=request,
            actor_id=str(current_admin.id),
            key_set=bool(payload.newsdata_api_key),
        )

    db.commit()
    db.refresh(settings)
    scheduler.reschedule(settings.ingestion_interval_hours, settings.digest_send_time)
    return _to_response(settings)
