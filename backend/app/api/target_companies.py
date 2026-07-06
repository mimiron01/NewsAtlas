import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.audit import log_event
from app.db.session import get_db
from app.models.company_follow import CompanyFollow
from app.models.target_company import TargetCompany
from app.models.user import User, UserRole
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

router = APIRouter(prefix="/target-companies", tags=["target-companies"])


def _get_or_404(db: Session, target_company_id: uuid.UUID) -> TargetCompany:
    target_company = db.get(TargetCompany, target_company_id)
    if target_company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target company not found")
    return target_company


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
