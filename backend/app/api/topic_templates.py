import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.audit import log_event
from app.db.session import get_db
from app.models.theme_watch import ThemeWatch
from app.models.topic_template import TopicTemplate
from app.models.user import User
from app.schemas.theme_watch import ThemeWatchResponse
from app.schemas.topic_template import (
    TopicTemplateApplyRequest,
    TopicTemplateCreate,
    TopicTemplatePerformanceResponse,
    TopicTemplateResponse,
    TopicTemplateUpdate,
)
from app.services.theme_follows import ensure_follow, find_theme_by_name, get_or_create_theme, to_response
from app.services.topic_templates import list_active_templates, template_performance
from app.services.workspace_settings import get_or_create_workspace_settings

router = APIRouter(prefix="/topic-templates", tags=["topic-templates"])


def _get_or_404(db: Session, template_id: uuid.UUID) -> TopicTemplate:
    template = db.get(TopicTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic template not found")
    return template


@router.get("", response_model=list[TopicTemplateResponse])
def list_topic_templates(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[TopicTemplateResponse]:
    """Any authenticated user — the gallery is meant to be the default first view for a
    workspace with no topics yet (see docs/topics-ux-improvements-planning.html §4.2),
    not an admin-only surface. Restricted to the workspace's main_language so a German
    workspace sees the German-market template set rather than the English one."""
    workspace_settings = get_or_create_workspace_settings(db)
    return list_active_templates(db, language=workspace_settings.main_language)


@router.post("/{template_id}/apply", response_model=ThemeWatchResponse, status_code=status.HTTP_201_CREATED)
def apply_topic_template(
    template_id: uuid.UUID,
    payload: TopicTemplateApplyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ThemeWatchResponse:
    """Creates a ThemeWatch pre-filled from the template, with any user-supplied overrides
    applied on top — see docs/topics-ux-improvements-planning.html §2.2. Goes through the
    same duplicate-name confirmation (§1.4) and active-topic ceiling as a manual create,
    since applying a template is just a pre-filled create, not a different code path."""
    template = _get_or_404(db, template_id)
    if not template.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This template is no longer available")

    name = payload.name or template.name
    query_terms = payload.query_terms if payload.query_terms is not None else template.query_terms
    exclude_terms = payload.exclude_terms if payload.exclude_terms is not None else template.exclude_terms
    source_allowlist = (
        payload.google_news_source_allowlist
        if payload.google_news_source_allowlist is not None
        else template.suggested_source_allowlist
    )

    if not payload.confirm_merge:
        existing = find_theme_by_name(db, name)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "duplicate_name",
                    "existing_id": str(existing.id),
                    "existing_query_terms": existing.query_terms,
                },
            )

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
        name=name,
        query_terms=query_terms,
        exclude_terms=exclude_terms,
        industry=payload.industry,
        created_by=current_user.id,
        google_news_source_allowlist=source_allowlist,
        created_from_template_id=template.id,
    )
    follow = ensure_follow(
        db, user_id=current_user.id, theme_watch_id=theme.id, assigned_by=current_user.id
    )
    db.commit()
    db.refresh(theme)
    db.refresh(follow)
    log_event(
        "topic_template_applied",
        actor_id=str(current_user.id),
        template_id=str(template.id),
        theme_watch_id=str(theme.id),
    )
    return to_response(db, theme, follow)


# --- Admin management (§2.1: templates are admin-managed rows, not a hardcoded list) ---


@router.post("", response_model=TopicTemplateResponse, status_code=status.HTTP_201_CREATED)
def create_topic_template(
    payload: TopicTemplateCreate,
    db: Session = Depends(get_db),
    _current_admin: User = Depends(require_admin),
) -> TopicTemplateResponse:
    template = TopicTemplate(**payload.model_dump())
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


@router.get("/all", response_model=list[TopicTemplateResponse])
def list_all_topic_templates(
    db: Session = Depends(get_db),
    _current_admin: User = Depends(require_admin),
) -> list[TopicTemplateResponse]:
    """Admin-only — includes inactive templates, unlike GET /topic-templates."""
    return (
        db.query(TopicTemplate)
        .order_by(TopicTemplate.sort_order.asc(), TopicTemplate.name.asc())
        .all()
    )


@router.patch("/{template_id}", response_model=TopicTemplateResponse)
def update_topic_template(
    template_id: uuid.UUID,
    payload: TopicTemplateUpdate,
    db: Session = Depends(get_db),
    _current_admin: User = Depends(require_admin),
) -> TopicTemplateResponse:
    template = _get_or_404(db, template_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(template, field, value)
    db.commit()
    db.refresh(template)
    return template


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_topic_template(
    template_id: uuid.UUID,
    db: Session = Depends(get_db),
    _current_admin: User = Depends(require_admin),
) -> None:
    template = _get_or_404(db, template_id)
    db.delete(template)
    db.commit()


@router.get("/{template_id}/performance", response_model=TopicTemplatePerformanceResponse)
def get_topic_template_performance(
    template_id: uuid.UUID,
    db: Session = Depends(get_db),
    _current_admin: User = Depends(require_admin),
) -> TopicTemplatePerformanceResponse:
    _get_or_404(db, template_id)
    return template_performance(db, template_id)
