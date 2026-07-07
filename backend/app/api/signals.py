import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.signal import Signal, SignalStatus
from app.models.signal_favorite import SignalFavorite
from app.models.target_company import TargetCompany
from app.models.user import User, UserRole
from app.schemas.signal import SignalResponse, SignalStatusUpdate
from app.services.signal_queries import (
    accessible_signal_row,
    base_signal_query,
    get_accessible_signal,
    scope_to_follows,
    signal_row_to_response,
)

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("", response_model=list[SignalResponse])
def list_signals(
    company_id: uuid.UUID | None = None,
    status_filter: SignalStatus | None = Query(default=None, alias="status"),
    scope: str | None = Query(default=None),
    favorited: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[SignalResponse]:
    query = base_signal_query(db, current_user)
    if scope == "all":
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="scope=all is admin-only"
            )
    else:
        query = scope_to_follows(query, db, current_user, include_muted=False)
    if company_id is not None:
        query = query.filter(TargetCompany.id == company_id)
    if status_filter is not None:
        query = query.filter(Signal.status == status_filter)
    if favorited:
        favorite_signal_ids = db.query(SignalFavorite.signal_id).filter(
            SignalFavorite.user_id == current_user.id
        )
        query = query.filter(Signal.id.in_(favorite_signal_ids.scalar_subquery()))
    rows = query.order_by(Signal.created_at.desc()).all()
    return [signal_row_to_response(*row) for row in rows]


@router.get("/{signal_id}", response_model=SignalResponse)
def get_signal(
    signal_id: uuid.UUID,
    scope: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SignalResponse:
    row = accessible_signal_row(db, signal_id, current_user, scope)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signal not found")
    return signal_row_to_response(*row)


@router.patch("/{signal_id}", response_model=SignalResponse)
def update_signal_status(
    signal_id: uuid.UUID,
    payload: SignalStatusUpdate,
    scope: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SignalResponse:
    row = accessible_signal_row(db, signal_id, current_user, scope)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signal not found")
    signal, article, target_company, is_favorited, open_todo_count = row
    signal.status = payload.status
    db.commit()
    db.refresh(signal)
    return signal_row_to_response(signal, article, target_company, is_favorited, open_todo_count)


@router.post("/{signal_id}/favorite", response_model=SignalResponse)
def favorite_signal(
    signal_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SignalResponse:
    get_accessible_signal(db, signal_id, current_user)
    existing = (
        db.query(SignalFavorite)
        .filter(SignalFavorite.signal_id == signal_id, SignalFavorite.user_id == current_user.id)
        .first()
    )
    if existing is None:
        db.add(SignalFavorite(signal_id=signal_id, user_id=current_user.id))
        db.commit()
    row = accessible_signal_row(db, signal_id, current_user)
    return signal_row_to_response(*row)


@router.delete("/{signal_id}/favorite", response_model=SignalResponse)
def unfavorite_signal(
    signal_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SignalResponse:
    get_accessible_signal(db, signal_id, current_user)
    db.query(SignalFavorite).filter(
        SignalFavorite.signal_id == signal_id, SignalFavorite.user_id == current_user.id
    ).delete()
    db.commit()
    row = accessible_signal_row(db, signal_id, current_user)
    return signal_row_to_response(*row)
