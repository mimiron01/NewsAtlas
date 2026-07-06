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
    get_or_create_workspace_settings,
)

router = APIRouter(prefix="/settings", tags=["settings"])


def _to_response(settings: WorkspaceSettings) -> WorkspaceSettingsResponse:
    key_status = get_mistral_api_key_status(settings, get_settings())
    return WorkspaceSettingsResponse(
        id=settings.id,
        company_name=settings.company_name,
        offering_description=settings.offering_description,
        digest_send_time=settings.digest_send_time,
        ingestion_interval_hours=settings.ingestion_interval_hours,
        mistral_model=settings.mistral_model,
        mistral_triage_model=settings.mistral_triage_model,
        mistral_embed_model=settings.mistral_embed_model,
        mistral_triage_enabled=settings.mistral_triage_enabled,
        mistral_dedupe_similarity_threshold=settings.mistral_dedupe_similarity_threshold,
        mistral_api_key_configured=key_status.configured,
        mistral_api_key_source=key_status.source,
        mistral_api_key_last4=key_status.last4,
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
    settings.mistral_model = payload.mistral_model
    settings.mistral_triage_model = payload.mistral_triage_model
    settings.mistral_embed_model = payload.mistral_embed_model
    settings.mistral_triage_enabled = payload.mistral_triage_enabled
    settings.mistral_dedupe_similarity_threshold = payload.mistral_dedupe_similarity_threshold

    if payload.mistral_api_key is not None:
        settings.mistral_api_key = payload.mistral_api_key
        # Never log the key itself — only whether this save set, cleared, or left it.
        log_event(
            "mistral_api_key_override_changed",
            request=request,
            actor_id=str(current_admin.id),
            key_set=bool(payload.mistral_api_key),
        )

    db.commit()
    db.refresh(settings)
    scheduler.reschedule(settings.ingestion_interval_hours, settings.digest_send_time)
    return _to_response(settings)
