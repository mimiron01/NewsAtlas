import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.audit import log_event
from app.core.limiter import limiter
from app.db.session import SessionLocal, get_db
from app.models.company_follow import CompanyFollow
from app.models.target_company import TargetCompany
from app.models.user import User, UserRole
from app.schemas.news_usage import BackfillTriggerResult
from app.schemas.target_company import (
    CompanyFollowerResponse,
    TargetCompanyCreate,
    TargetCompanyResponse,
    TargetCompanyUpdate,
)
from app.services.company_follows import (
    ensure_follow,
    get_follow,
    get_or_create_company,
    remove_follow,
    to_response,
)
from app.services.newsdata_backfill import run_backfill_for_company
from app.services.workspace_settings import get_or_create_workspace_settings

router = APIRouter(prefix="/target-companies", tags=["target-companies"])


def _get_or_404(db: Session, target_company_id: uuid.UUID) -> TargetCompany:
    target_company = db.get(TargetCompany, target_company_id)
    if target_company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target company not found")
    return target_company


def _run_backfill_in_background(target_company_id: uuid.UUID) -> None:
    """Runs in a BackgroundTasks worker after the response has been sent, so it opens its
    own session rather than reusing the request-scoped one (which may already be closed
    by then) — the same pattern services/scheduler.py uses for its background jobs."""
    db = SessionLocal()
    try:
        run_backfill_for_company(db, target_company_id)
    finally:
        db.close()


@router.get("", response_model=list[TargetCompanyResponse])
def list_target_companies(
    scope: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TargetCompanyResponse]:
    if scope == "all":
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="scope=all is admin-only"
            )
        companies = db.query(TargetCompany).order_by(TargetCompany.created_at.desc()).all()
        own_follows = {
            follow.target_company_id: follow
            for follow in db.query(CompanyFollow).filter(CompanyFollow.user_id == current_user.id)
        }
        return [to_response(db, company, own_follows.get(company.id)) for company in companies]

    rows = (
        db.query(TargetCompany, CompanyFollow)
        .join(CompanyFollow, CompanyFollow.target_company_id == TargetCompany.id)
        .filter(CompanyFollow.user_id == current_user.id)
        .order_by(TargetCompany.created_at.desc())
        .all()
    )
    return [to_response(db, company, follow) for company, follow in rows]


@router.post("", response_model=TargetCompanyResponse, status_code=status.HTTP_201_CREATED)
def create_target_company(
    payload: TargetCompanyCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TargetCompanyResponse:
    company = get_or_create_company(
        db,
        name=payload.name,
        keywords=payload.keywords,
        industry=payload.industry,
        created_by=current_user.id,
    )
    follow = ensure_follow(
        db, user_id=current_user.id, target_company_id=company.id, assigned_by=current_user.id
    )
    db.commit()
    db.refresh(company)
    db.refresh(follow)

    workspace_settings = get_or_create_workspace_settings(db)
    if (
        workspace_settings.newsdata_enabled
        and workspace_settings.newsdata_backfill_days > 0
        and company.backfilled_at is None
    ):
        background_tasks.add_task(_run_backfill_in_background, company.id)

    return to_response(db, company, follow)


@router.patch("/{target_company_id}", response_model=TargetCompanyResponse)
def update_target_company(
    target_company_id: uuid.UUID,
    payload: TargetCompanyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TargetCompanyResponse:
    company = _get_or_404(db, target_company_id)
    follow = get_follow(db, current_user.id, target_company_id)
    if current_user.role != UserRole.ADMIN and follow is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not following this company"
        )
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(company, field, value)
    db.commit()
    db.refresh(company)
    return to_response(db, company, follow)


@router.delete("/{target_company_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_target_company(
    target_company_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    company = _get_or_404(db, target_company_id)
    if current_user.role == UserRole.ADMIN:
        db.delete(company)
        db.commit()
        log_event(
            "admin_company_deleted",
            user_id=str(current_user.id),
            company_id=str(target_company_id),
        )
        return

    follow = get_follow(db, current_user.id, target_company_id)
    if follow is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not following this company"
        )
    remove_follow(db, current_user.id, target_company_id)
    db.commit()


@router.post("/{target_company_id}/mute", response_model=TargetCompanyResponse)
def toggle_mute(
    target_company_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TargetCompanyResponse:
    company = _get_or_404(db, target_company_id)
    follow = get_follow(db, current_user.id, target_company_id)
    if follow is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Not following this company"
        )
    follow.is_muted = not follow.is_muted
    db.commit()
    db.refresh(follow)
    return to_response(db, company, follow)


@router.get("/{target_company_id}/followers", response_model=list[CompanyFollowerResponse])
def list_followers(
    target_company_id: uuid.UUID,
    db: Session = Depends(get_db),
    _current_admin: User = Depends(require_admin),
) -> list[CompanyFollowerResponse]:
    _get_or_404(db, target_company_id)
    rows = (
        db.query(CompanyFollow, User)
        .join(User, CompanyFollow.user_id == User.id)
        .filter(CompanyFollow.target_company_id == target_company_id)
        .all()
    )
    return [
        CompanyFollowerResponse(
            user_id=user.id,
            email=user.email,
            name=user.name,
            is_muted=follow.is_muted,
            assigned_by=follow.assigned_by,
            created_at=follow.created_at,
        )
        for follow, user in rows
    ]


@router.post("/{target_company_id}/backfill", response_model=BackfillTriggerResult)
@limiter.limit("10/hour")
def trigger_backfill(
    target_company_id: uuid.UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _current_admin: User = Depends(require_admin),
) -> BackfillTriggerResult:
    """Admin-only: manually trigger a one-time NewsData.io historical archive backfill
    for a company created before this feature shipped, or to re-run after raising
    newsdata_backfill_days (see docs/news-source-expansion-planning.html §10.4)."""
    company = _get_or_404(db, target_company_id)
    workspace_settings = get_or_create_workspace_settings(db)

    if not workspace_settings.newsdata_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="NewsData.io is not enabled for this workspace",
        )
    if workspace_settings.newsdata_backfill_days <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Set a NewsData.io backfill window (newsdata_backfill_days) in Settings first",
        )
    if company.backfilled_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This company has already been backfilled",
        )

    background_tasks.add_task(_run_backfill_in_background, target_company_id)
    log_event(
        "newsdata_backfill_triggered",
        request=request,
        actor_id=str(_current_admin.id),
        company_id=str(target_company_id),
    )
    return BackfillTriggerResult(
        scheduled=True,
        message="Historical backfill scheduled — new signals will appear over the next few minutes.",
        target_company_id=target_company_id,
    )
