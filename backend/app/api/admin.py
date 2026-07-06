import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.audit import log_event
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.admin import AdminCompanyAssignRequest, AdminUserResponse, RoleUpdateRequest
from app.schemas.target_company import TargetCompanyResponse
from app.services.company_follows import (
    ensure_follow,
    get_follow,
    get_or_create_company,
    remove_follow,
    to_response,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _get_user_or_404(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.get("/users", response_model=list[AdminUserResponse])
def list_users(
    db: Session = Depends(get_db),
    _current_admin: User = Depends(require_admin),
) -> list[User]:
    return db.query(User).order_by(User.created_at.asc()).all()


@router.patch("/users/{user_id}/role", response_model=AdminUserResponse)
def update_user_role(
    user_id: uuid.UUID,
    payload: RoleUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> User:
    target_user = _get_user_or_404(db, user_id)

    if target_user.role == UserRole.ADMIN and payload.role != UserRole.ADMIN:
        remaining_admins = db.query(User).filter(User.role == UserRole.ADMIN).count()
        if remaining_admins <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote the last remaining admin.",
            )

    target_user.role = payload.role
    db.commit()
    db.refresh(target_user)
    log_event(
        "admin_role_changed",
        request=request,
        actor_id=str(current_admin.id),
        target_user_id=str(user_id),
        new_role=payload.role.value,
    )
    return target_user


@router.post(
    "/users/{user_id}/companies",
    response_model=TargetCompanyResponse,
    status_code=status.HTTP_201_CREATED,
)
def assign_company(
    user_id: uuid.UUID,
    payload: AdminCompanyAssignRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> TargetCompanyResponse:
    target_user = _get_user_or_404(db, user_id)

    company = get_or_create_company(
        db,
        name=payload.name,
        keywords=payload.keywords,
        industry=payload.industry,
        created_by=current_admin.id,
    )
    follow = ensure_follow(
        db, user_id=target_user.id, target_company_id=company.id, assigned_by=current_admin.id
    )
    db.commit()
    db.refresh(company)
    db.refresh(follow)
    log_event(
        "admin_company_assigned",
        request=request,
        actor_id=str(current_admin.id),
        target_user_id=str(user_id),
        company_id=str(company.id),
    )
    return to_response(db, company, follow)


@router.delete("/users/{user_id}/companies/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
def unassign_company(
    user_id: uuid.UUID,
    company_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> None:
    _get_user_or_404(db, user_id)
    follow = get_follow(db, user_id, company_id)
    if follow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Follow not found")
    remove_follow(db, user_id, company_id)
    db.commit()
    log_event(
        "admin_company_unassigned",
        request=request,
        actor_id=str(current_admin.id),
        target_user_id=str(user_id),
        company_id=str(company_id),
    )
