import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.audit import log_event
from app.core.config import get_settings
from app.core.limiter import limiter
from app.db.session import get_db
from app.models.ingestion_run import STATUS_RUNNING, TRIGGER_MANUAL
from app.models.user import User
from app.schemas.ingestion import IngestionRunStatusResponse
from app.services.ingestion_runs import (
    create_run,
    execute_ingestion_run,
    get_latest_run,
    get_running_run,
    list_runs,
    request_cancel,
    to_status_response,
)
from app.services.workspace_settings import (
    enforce_manual_trigger_cooldown,
    get_or_create_workspace_settings,
)

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/run-now", response_model=IngestionRunStatusResponse, status_code=202)
@limiter.limit("10/hour")
def run_now(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> IngestionRunStatusResponse:
    workspace_settings = get_or_create_workspace_settings(db)
    enforce_manual_trigger_cooldown(
        db,
        workspace_settings,
        "last_manual_ingestion_at",
        get_settings().manual_trigger_cooldown_seconds,
    )

    # A run (manual or scheduled) is already in flight — hand back its progress instead of
    # starting an overlapping second pass over the same target companies/articles.
    existing_run = get_running_run(db)
    if existing_run is not None:
        return to_status_response(existing_run)

    run = create_run(db, trigger=TRIGGER_MANUAL, triggered_by_user_id=current_user.id)
    background_tasks.add_task(execute_ingestion_run, run.id)
    return to_status_response(run)


@router.post("/runs/{run_id}/cancel", response_model=IngestionRunStatusResponse)
def cancel_run(
    run_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> IngestionRunStatusResponse:
    """Admin-only: request that an in-progress run stop. Cooperative, not instant — the
    pipeline notices at its next per-company/per-article checkpoint (see
    services/ingestion.py) and stops cleanly, typically within a few seconds."""
    run = request_cancel(db, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingestion run not found")
    if run.status != STATUS_RUNNING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This run is not currently running"
        )
    log_event(
        "ingestion_run_cancel_requested",
        request=request,
        actor_id=str(current_admin.id),
        run_id=str(run_id),
    )
    return to_status_response(run)


@router.get("/status", response_model=IngestionRunStatusResponse | None)
def get_status(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> IngestionRunStatusResponse | None:
    """Latest ingestion run (manual or scheduled), for the frontend's progress bar to poll
    and to resume tracking a run already in flight after a page reload."""
    run = get_latest_run(db)
    return to_status_response(run) if run is not None else None


@router.get("/runs", response_model=list[IngestionRunStatusResponse])
def get_runs(
    limit: int = 50,
    db: Session = Depends(get_db),
    _current_admin: User = Depends(require_admin),
) -> list[IngestionRunStatusResponse]:
    """Run history for the Settings > Logs admin view, including scheduled runs — so a
    failure in the background job isn't invisible just because no one clicked a button."""
    limit = max(1, min(limit, 100))
    return [to_status_response(run) for run in list_runs(db, limit=limit)]
