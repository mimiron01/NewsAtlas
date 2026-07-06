from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.workspace_settings import WorkspaceSettings


@dataclass
class MistralApiKeyStatus:
    configured: bool
    source: str  # "workspace" | "environment" | "unset"
    last4: str | None


# NewsData.io's key status shares the exact same shape as Mistral's — reusing the
# dataclass rather than defining an identical NewsDataApiKeyStatus one.
ApiKeyStatus = MistralApiKeyStatus


def resolve_mistral_api_key(workspace_settings: WorkspaceSettings, app_settings: Settings) -> str:
    """The in-app override (set by an admin via /settings) always wins when present;
    otherwise falls back to the MISTRAL_API_KEY env var so existing .env-based
    deployments keep working without requiring an admin to re-enter anything."""
    return workspace_settings.mistral_api_key or app_settings.mistral_api_key


def get_mistral_api_key_status(
    workspace_settings: WorkspaceSettings, app_settings: Settings
) -> MistralApiKeyStatus:
    if workspace_settings.mistral_api_key:
        key, source = workspace_settings.mistral_api_key, "workspace"
    elif app_settings.mistral_api_key:
        key, source = app_settings.mistral_api_key, "environment"
    else:
        return MistralApiKeyStatus(configured=False, source="unset", last4=None)
    return MistralApiKeyStatus(configured=True, source=source, last4=key[-4:] if len(key) >= 4 else key)


def resolve_newsdata_api_key(workspace_settings: WorkspaceSettings, app_settings: Settings) -> str:
    """Same in-app-override-wins-over-env-var resolution as resolve_mistral_api_key."""
    return workspace_settings.newsdata_api_key or app_settings.newsdata_api_key


def get_newsdata_api_key_status(
    workspace_settings: WorkspaceSettings, app_settings: Settings
) -> ApiKeyStatus:
    if workspace_settings.newsdata_api_key:
        key, source = workspace_settings.newsdata_api_key, "workspace"
    elif app_settings.newsdata_api_key:
        key, source = app_settings.newsdata_api_key, "environment"
    else:
        return ApiKeyStatus(configured=False, source="unset", last4=None)
    return ApiKeyStatus(configured=True, source=source, last4=key[-4:] if len(key) >= 4 else key)


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
