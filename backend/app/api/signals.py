import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Query as SAQuery, Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.article import Article
from app.models.company_follow import CompanyFollow
from app.models.signal import Signal, SignalStatus
from app.models.target_company import TargetCompany
from app.models.user import User, UserRole
from app.schemas.signal import SignalResponse, SignalStatusUpdate

router = APIRouter(prefix="/signals", tags=["signals"])


def _base_query(db: Session):
    return (
        db.query(Signal, Article, TargetCompany)
        .join(Article, Signal.article_id == Article.id)
        .join(TargetCompany, Article.target_company_id == TargetCompany.id)
    )


def _scope_to_follows(query: SAQuery, db: Session, user: User, *, include_muted: bool) -> SAQuery:
    follows = db.query(CompanyFollow.target_company_id).filter(CompanyFollow.user_id == user.id)
    if not include_muted:
        follows = follows.filter(CompanyFollow.is_muted.is_(False))
    return query.filter(TargetCompany.id.in_(follows.scalar_subquery()))


def _to_response(signal: Signal, article: Article, target_company: TargetCompany) -> SignalResponse:
    return SignalResponse(
        id=signal.id,
        status=signal.status,
        summary=signal.summary,
        business_relevance=signal.business_relevance,
        supporting_quote=signal.supporting_quote or "",
        outreach_snippet_email=signal.outreach_snippet_email,
        outreach_snippet_linkedin=signal.outreach_snippet_linkedin,
        outreach_call_opener=signal.outreach_call_opener,
        relevance_score=signal.relevance_score,
        signal_type=signal.signal_type,
        confidence=signal.confidence,
        entities=signal.entities,
        created_at=signal.created_at,
        article_id=article.id,
        article_title=article.title,
        article_url=article.url,
        article_source_name=article.source_name,
        article_published_at=article.published_at,
        article_source=article.source,
        article_external_sentiment=article.external_sentiment,
        article_external_tags=article.external_tags,
        target_company_id=target_company.id,
        target_company_name=target_company.name,
    )


@router.get("", response_model=list[SignalResponse])
def list_signals(
    company_id: uuid.UUID | None = None,
    status_filter: SignalStatus | None = Query(default=None, alias="status"),
    scope: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[SignalResponse]:
    query = _base_query(db)
    if scope == "all":
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="scope=all is admin-only"
            )
    else:
        query = _scope_to_follows(query, db, current_user, include_muted=False)
    if company_id is not None:
        query = query.filter(TargetCompany.id == company_id)
    if status_filter is not None:
        query = query.filter(Signal.status == status_filter)
    rows = query.order_by(Signal.created_at.desc()).all()
    return [_to_response(*row) for row in rows]


def _accessible_row(db: Session, signal_id: uuid.UUID, current_user: User, scope: str | None):
    query = _base_query(db).filter(Signal.id == signal_id)
    if scope == "all":
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="scope=all is admin-only"
            )
    else:
        query = _scope_to_follows(query, db, current_user, include_muted=True)
    return query.first()


@router.get("/{signal_id}", response_model=SignalResponse)
def get_signal(
    signal_id: uuid.UUID,
    scope: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SignalResponse:
    row = _accessible_row(db, signal_id, current_user, scope)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signal not found")
    return _to_response(*row)


@router.patch("/{signal_id}", response_model=SignalResponse)
def update_signal_status(
    signal_id: uuid.UUID,
    payload: SignalStatusUpdate,
    scope: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SignalResponse:
    row = _accessible_row(db, signal_id, current_user, scope)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signal not found")
    signal, article, target_company = row
    signal.status = payload.status
    db.commit()
    db.refresh(signal)
    return _to_response(signal, article, target_company)
