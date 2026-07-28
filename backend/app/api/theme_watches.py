import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.audit import log_event
from app.db.session import get_db
from app.models.theme_follow import ThemeFollow
from app.models.theme_watch import ThemeWatch
from app.models.user import User, UserRole
from app.schemas.theme_watch import (
    ThemeFollowerResponse,
    ThemeWatchCreate,
    ThemeWatchResponse,
    ThemeWatchUpdate,
)
from app.services.theme_follows import (
    ensure_follow,
    get_follow,
    get_or_create_theme,
    remove_follow,
    to_response,
)
from app.services.workspace_settings import get_or_create_workspace_settings

router = APIRouter(prefix="/theme-watches", tags=["theme-watches"])


def _get_or_404(db: Session, theme_watch_id: uuid.UUID) -> ThemeWatch:
    theme = db.get(ThemeWatch, theme_watch_id)
    if theme is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Theme watch not found")
    return theme


@router.get("", response_model=list[ThemeWatchResponse])
def list_theme_watches(
    scope: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ThemeWatchResponse]:
    if scope == "all":
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="scope=all is admin-only"
            )
        themes = db.query(ThemeWatch).order_by(ThemeWatch.created_at.desc()).all()
        own_follows = {
            follow.theme_watch_id: follow
            for follow in db.query(ThemeFollow).filter(ThemeFollow.user_id == current_user.id)
        }
        return [to_response(db, theme, own_follows.get(theme.id)) for theme in themes]

    rows = (
        db.query(ThemeWatch, ThemeFollow)
        .join(ThemeFollow, ThemeFollow.theme_watch_id == ThemeWatch.id)
        .filter(ThemeFollow.user_id == current_user.id)
        .order_by(ThemeWatch.created_at.desc())
        .all()
    )
    return [to_response(db, theme, follow) for theme, follow in rows]


@router.post("", response_model=ThemeWatchResponse, status_code=status.HTTP_201_CREATED)
def create_theme_watch(
    payload: ThemeWatchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ThemeWatchResponse:
    workspace_settings = get_or_create_workspace_settings(db)
    active_count = db.query(ThemeWatch).filter(ThemeWatch.is_active.is_(True)).count()
    if active_count >= workspace_settings.max_active_theme_watches:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Workspace already has {active_count} active theme watches "
                f"(limit: {workspace_settings.max_active_theme_watches}). Pause or delete one first."
            ),
        )

    theme = get_or_create_theme(
        db,
        name=payload.name,
        query_terms=payload.query_terms,
        industry=payload.industry,
        created_by=current_user.id,
        google_news_source_allowlist=payload.google_news_source_allowlist,
    )
    follow = ensure_follow(
        db, user_id=current_user.id, theme_watch_id=theme.id, assigned_by=current_user.id
    )
    db.commit()
    db.refresh(theme)
    db.refresh(follow)
    return to_response(db, theme, follow)


@router.patch("/{theme_watch_id}", response_model=ThemeWatchResponse)
def update_theme_watch(
    theme_watch_id: uuid.UUID,
    payload: ThemeWatchUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ThemeWatchResponse:
    theme = _get_or_404(db, theme_watch_id)
    follow = get_follow(db, current_user.id, theme_watch_id)
    if current_user.role != UserRole.ADMIN and follow is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not following this theme"
        )
    # Same creator-or-admin gate as TargetCompany (v1 roadmap §5) — applied from day one
    # here rather than shipping the gap again (see docs/theme-search-planning.html §2.1).
    if current_user.role != UserRole.ADMIN and theme.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only this theme's creator or an admin can edit it",
        )

    updates = payload.model_dump(exclude_unset=True)
    if updates.get("is_active") and not theme.is_active:
        workspace_settings = get_or_create_workspace_settings(db)
        active_count = db.query(ThemeWatch).filter(ThemeWatch.is_active.is_(True)).count()
        if active_count >= workspace_settings.max_active_theme_watches:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Workspace already has {active_count} active theme watches "
                    f"(limit: {workspace_settings.max_active_theme_watches}). Pause or delete one first."
                ),
            )

    for field, value in updates.items():
        setattr(theme, field, value)
    db.commit()
    db.refresh(theme)
    return to_response(db, theme, follow)


@router.delete("/{theme_watch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_theme_watch(
    theme_watch_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    theme = _get_or_404(db, theme_watch_id)
    if current_user.role == UserRole.ADMIN:
        db.delete(theme)
        db.commit()
        log_event(
            "admin_theme_deleted", user_id=str(current_user.id), theme_watch_id=str(theme_watch_id)
        )
        return

    follow = get_follow(db, current_user.id, theme_watch_id)
    if follow is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not following this theme"
        )
    remove_follow(db, current_user.id, theme_watch_id)
    db.commit()


@router.post("/{theme_watch_id}/mute", response_model=ThemeWatchResponse)
def toggle_mute(
    theme_watch_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ThemeWatchResponse:
    theme = _get_or_404(db, theme_watch_id)
    follow = get_follow(db, current_user.id, theme_watch_id)
    if follow is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Not following this theme"
        )
    follow.is_muted = not follow.is_muted
    db.commit()
    db.refresh(follow)
    return to_response(db, theme, follow)


@router.get("/{theme_watch_id}/followers", response_model=list[ThemeFollowerResponse])
def list_followers(
    theme_watch_id: uuid.UUID,
    db: Session = Depends(get_db),
    _current_admin: User = Depends(require_admin),
) -> list[ThemeFollowerResponse]:
    _get_or_404(db, theme_watch_id)
    rows = (
        db.query(ThemeFollow, User)
        .join(User, ThemeFollow.user_id == User.id)
        .filter(ThemeFollow.theme_watch_id == theme_watch_id)
        .all()
    )
    return [
        ThemeFollowerResponse(
            user_id=user.id,
            email=user.email,
            name=user.name,
            is_muted=follow.is_muted,
            assigned_by=follow.assigned_by,
            created_at=follow.created_at,
        )
        for follow, user in rows
    ]
