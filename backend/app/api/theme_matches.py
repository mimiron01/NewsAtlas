import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.signal import SignalStatus
from app.models.theme_match import ThemeMatch
from app.models.theme_watch import ThemeWatch
from app.models.user import User, UserRole
from app.schemas.target_company import TargetCompanyResponse
from app.schemas.theme_match import ThemeMatchResponse, ThemeMatchStatusUpdate
from app.services.company_follows import ensure_follow, get_or_create_company
from app.services.company_follows import to_response as company_to_response
from app.services.theme_match_queries import (
    accessible_theme_match_row,
    base_theme_match_query,
    get_accessible_theme_match,
    scope_to_theme_follows,
    theme_match_row_to_response,
)

router = APIRouter(prefix="/theme-matches", tags=["theme-matches"])


@router.get("", response_model=list[ThemeMatchResponse])
def list_theme_matches(
    theme_id: uuid.UUID | None = None,
    status_filter: SignalStatus | None = Query(default=None, alias="status"),
    scope: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ThemeMatchResponse]:
    query = base_theme_match_query(db)
    if scope == "all":
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="scope=all is admin-only"
            )
    else:
        query = scope_to_theme_follows(query, db, current_user, include_muted=False)
    if theme_id is not None:
        query = query.filter(ThemeWatch.id == theme_id)
    if status_filter is not None:
        query = query.filter(ThemeMatch.status == status_filter)
    rows = query.order_by(ThemeMatch.fetched_at.desc()).all()
    return [theme_match_row_to_response(*row) for row in rows]


@router.get("/{match_id}", response_model=ThemeMatchResponse)
def get_theme_match(
    match_id: uuid.UUID,
    scope: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ThemeMatchResponse:
    row = accessible_theme_match_row(db, match_id, current_user, scope)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Theme match not found")
    return theme_match_row_to_response(*row)


@router.patch("/{match_id}", response_model=ThemeMatchResponse)
def update_theme_match_status(
    match_id: uuid.UUID,
    payload: ThemeMatchStatusUpdate,
    scope: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ThemeMatchResponse:
    row = accessible_theme_match_row(db, match_id, current_user, scope)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Theme match not found")
    match, theme, matched_company = row
    match.status = payload.status
    db.commit()
    db.refresh(match)
    return theme_match_row_to_response(match, theme, matched_company)


@router.post("/{match_id}/track-company", response_model=TargetCompanyResponse)
def track_company_from_match(
    match_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TargetCompanyResponse:
    """Creates/follows a TargetCompany from a match's extracted_company_name — does not
    force a Signal (see docs/theme-search-planning.html §1). Any authenticated user can
    call this, same as direct company creation via POST /target-companies; the match
    must still be one this user can see (follows the theme, or admin scope=all)."""
    match = get_accessible_theme_match(db, match_id, current_user)
    if not match.extracted_company_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This match has no extracted company to track",
        )
    if match.matched_target_company_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This company is already tracked",
        )

    company = get_or_create_company(
        db,
        name=match.extracted_company_name,
        keywords=[],
        industry=None,
        created_by=current_user.id,
    )
    follow = ensure_follow(
        db, user_id=current_user.id, target_company_id=company.id, assigned_by=current_user.id
    )
    match.matched_target_company_id = company.id
    db.commit()
    db.refresh(company)
    db.refresh(follow)
    return company_to_response(db, company, follow)
