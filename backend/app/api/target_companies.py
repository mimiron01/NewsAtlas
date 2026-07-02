import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.target_company import TargetCompany
from app.models.user import User
from app.schemas.target_company import (
    TargetCompanyCreate,
    TargetCompanyResponse,
    TargetCompanyUpdate,
)

router = APIRouter(prefix="/target-companies", tags=["target-companies"])


def _get_or_404(db: Session, target_company_id: uuid.UUID) -> TargetCompany:
    target_company = db.get(TargetCompany, target_company_id)
    if target_company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target company not found")
    return target_company


@router.get("", response_model=list[TargetCompanyResponse])
def list_target_companies(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[TargetCompany]:
    return db.query(TargetCompany).order_by(TargetCompany.created_at.desc()).all()


@router.post("", response_model=TargetCompanyResponse, status_code=status.HTTP_201_CREATED)
def create_target_company(
    payload: TargetCompanyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TargetCompany:
    target_company = TargetCompany(
        name=payload.name,
        keywords=payload.keywords,
        industry=payload.industry,
        created_by=current_user.id,
    )
    db.add(target_company)
    db.commit()
    db.refresh(target_company)
    return target_company


@router.patch("/{target_company_id}", response_model=TargetCompanyResponse)
def update_target_company(
    target_company_id: uuid.UUID,
    payload: TargetCompanyUpdate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> TargetCompany:
    target_company = _get_or_404(db, target_company_id)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(target_company, field, value)
    db.commit()
    db.refresh(target_company)
    return target_company


@router.delete("/{target_company_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_target_company(
    target_company_id: uuid.UUID,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> None:
    target_company = _get_or_404(db, target_company_id)
    db.delete(target_company)
    db.commit()
