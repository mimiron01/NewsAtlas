from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.limiter import limiter
from app.db.session import get_db
from app.models.user import User
from app.schemas.digest import DigestRunResult
from app.services.digest import send_daily_digest
from app.services.workspace_settings import (
    enforce_manual_trigger_cooldown,
    get_or_create_workspace_settings,
)

router = APIRouter(prefix="/digest", tags=["digest"])


@router.post("/send-now", response_model=DigestRunResult)
@limiter.limit("10/hour")
def send_now(
    request: Request,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> DigestRunResult:
    workspace_settings = get_or_create_workspace_settings(db)
    enforce_manual_trigger_cooldown(
        db,
        workspace_settings,
        "last_manual_digest_at",
        get_settings().manual_trigger_cooldown_seconds,
    )
    return send_daily_digest(db)
