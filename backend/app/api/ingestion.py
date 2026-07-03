from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.limiter import limiter
from app.db.session import get_db
from app.models.user import User
from app.schemas.ingestion import IngestionRunResult
from app.services.ingestion import run_ingestion
from app.services.workspace_settings import (
    enforce_manual_trigger_cooldown,
    get_or_create_workspace_settings,
)

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/run-now", response_model=IngestionRunResult)
@limiter.limit("10/hour")
def run_now(
    request: Request,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> IngestionRunResult:
    workspace_settings = get_or_create_workspace_settings(db)
    enforce_manual_trigger_cooldown(
        db,
        workspace_settings,
        "last_manual_ingestion_at",
        get_settings().manual_trigger_cooldown_seconds,
    )
    return run_ingestion(db)
