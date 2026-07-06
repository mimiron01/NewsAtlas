from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.models.user import User
from app.models.workspace_settings import WorkspaceSettings
from app.schemas.settings import WorkspaceSettingsResponse, WorkspaceSettingsUpdate
from app.services import scheduler
from app.services.workspace_settings import get_or_create_workspace_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=WorkspaceSettingsResponse)
def get_settings(
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> WorkspaceSettings:
    return get_or_create_workspace_settings(db)


@router.put("", response_model=WorkspaceSettingsResponse)
def update_settings(
    payload: WorkspaceSettingsUpdate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> WorkspaceSettings:
    settings = get_or_create_workspace_settings(db)
    settings.company_name = payload.company_name
    settings.offering_description = payload.offering_description
    settings.digest_send_time = payload.digest_send_time
    settings.ingestion_interval_hours = payload.ingestion_interval_hours
    db.commit()
    db.refresh(settings)
    scheduler.reschedule(settings.ingestion_interval_hours, settings.digest_send_time)
    return settings
