from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.workspace_settings import WorkspaceSettings


def get_or_create_workspace_settings(db: Session) -> WorkspaceSettings:
    settings = db.query(WorkspaceSettings).first()
    if settings is None:
        settings = WorkspaceSettings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def enforce_manual_trigger_cooldown(
    db: Session, workspace_settings: WorkspaceSettings, field_name: str, cooldown_seconds: int
) -> None:
    """Rejects the call with 429 if this trigger last ran within cooldown_seconds, regardless
    of who's calling — the cooldown is global, not per-user/IP (see M5 in the security review:
    this protects the operator's NewsAPI/Mistral/SMTP quota and cost, not the caller).
    """
    last_run = getattr(workspace_settings, field_name)
    now = datetime.now(timezone.utc)
    if last_run is not None:
        elapsed = (now - last_run).total_seconds()
        if elapsed < cooldown_seconds:
            retry_after = int(cooldown_seconds - elapsed)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {retry_after}s before triggering this again.",
                headers={"Retry-After": str(retry_after)},
            )
    setattr(workspace_settings, field_name, now)
    db.commit()
