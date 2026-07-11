import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.models.article import Article
from app.models.target_company import TargetCompany
from app.models.user import User
from app.schemas.article import SkippedArticleResponse
from app.schemas.signal import SignalResponse
from app.services.ai_client import AIClientError
from app.services.ingestion import ArticleNotEligibleError, promote_skipped_article
from app.services.signal_queries import signal_row_to_response

router = APIRouter(prefix="/articles", tags=["articles"])


@router.get("/skipped", response_model=list[SkippedArticleResponse])
def list_skipped_articles(
    reason: str = Query(default="triaged_out"),
    company_id: uuid.UUID | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    _current_admin: User = Depends(require_admin),
) -> list[SkippedArticleResponse]:
    """Admin-only review queue: articles the pipeline fetched but skipped, with the
    triage LLM's own reason when available — so a low-relevance rate no longer has to be
    taken on faith from an aggregate count alone."""
    limit = max(1, min(limit, 200))
    query = (
        db.query(Article, TargetCompany)
        .join(TargetCompany, Article.target_company_id == TargetCompany.id)
        .filter(Article.skip_reason == reason)
    )
    if company_id is not None:
        query = query.filter(TargetCompany.id == company_id)
    rows = query.order_by(Article.fetched_at.desc()).limit(limit).all()
    return [
        SkippedArticleResponse(
            id=article.id,
            title=article.title,
            url=article.url,
            source_name=article.source_name,
            source=article.source,
            published_at=article.published_at,
            fetched_at=article.fetched_at,
            skip_reason=article.skip_reason,
            triage_reason=article.triage_reason,
            headline_only=article.is_headline_only,
            target_company_id=company.id,
            target_company_name=company.name,
        )
        for article, company in rows
    ]


@router.post(
    "/{article_id}/create-signal",
    response_model=SignalResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_signal_from_skipped_article(
    article_id: uuid.UUID,
    db: Session = Depends(get_db),
    _current_admin: User = Depends(require_admin),
) -> SignalResponse:
    """Manual override for an article the triage pre-filter marked irrelevant: forces the
    full summarization call that filter would otherwise have skipped."""
    article = db.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    try:
        signal = promote_skipped_article(db, article)
    except ArticleNotEligibleError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except AIClientError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    target_company = db.get(TargetCompany, article.target_company_id)
    return signal_row_to_response(signal, article, target_company, is_favorited=False, open_todo_count=0)
