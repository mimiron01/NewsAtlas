import uuid

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Query as SAQuery, Session

from app.models.article import Article
from app.models.company_follow import CompanyFollow
from app.models.signal import Signal
from app.models.signal_favorite import SignalFavorite
from app.models.signal_todo import SignalTodo
from app.models.target_company import TargetCompany
from app.models.user import User, UserRole
from app.schemas.signal import SignalResponse

# Shared between app/api/signals.py, app/api/signal_todos.py, and app/api/dashboard.py so
# every entry point into "signals this user can see" uses identical follow-scoping and the
# same single-query favorite/open-todo annotation (see docs/dashboard-favorites-todos-planning.html §7).


def scope_to_follows(query: SAQuery, db: Session, user: User, *, include_muted: bool) -> SAQuery:
    follows = db.query(CompanyFollow.target_company_id).filter(CompanyFollow.user_id == user.id)
    if not include_muted:
        follows = follows.filter(CompanyFollow.is_muted.is_(False))
    return query.filter(TargetCompany.id.in_(follows.scalar_subquery()))


def base_signal_query(db: Session, current_user: User) -> SAQuery:
    """Joins Article/TargetCompany and annotates each row with the current user's
    favorite flag and open-todo count via correlated subqueries, so callers never need a
    second round trip (and rows stay comparable/sortable as one query)."""
    favorited_expr = (
        db.query(SignalFavorite.id)
        .filter(SignalFavorite.signal_id == Signal.id, SignalFavorite.user_id == current_user.id)
        .correlate(Signal)
        .exists()
    )
    open_todo_count_expr = (
        db.query(func.count(SignalTodo.id))
        .filter(
            SignalTodo.signal_id == Signal.id,
            SignalTodo.user_id == current_user.id,
            SignalTodo.is_done.is_(False),
        )
        .correlate(Signal)
        .scalar_subquery()
    )
    return (
        db.query(Signal, Article, TargetCompany, favorited_expr, open_todo_count_expr)
        .join(Article, Signal.article_id == Article.id)
        .join(TargetCompany, Article.target_company_id == TargetCompany.id)
    )


def signal_row_to_response(
    signal: Signal,
    article: Article,
    target_company: TargetCompany,
    is_favorited: bool,
    open_todo_count: int,
) -> SignalResponse:
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
        is_favorited=bool(is_favorited),
        open_todo_count=int(open_todo_count or 0),
    )


def accessible_signal_row(
    db: Session, signal_id: uuid.UUID, current_user: User, scope: str | None = None
):
    query = base_signal_query(db, current_user).filter(Signal.id == signal_id)
    if scope == "all":
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="scope=all is admin-only"
            )
    else:
        query = scope_to_follows(query, db, current_user, include_muted=True)
    return query.first()


def get_accessible_signal(db: Session, signal_id: uuid.UUID, current_user: User) -> Signal:
    """Raises 404 (rather than leaking existence via 403) if the signal doesn't exist or
    the user doesn't follow its target company — used by the favorites/todos endpoints,
    which act on a signal rather than rendering one."""
    row = accessible_signal_row(db, signal_id, current_user)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signal not found")
    return row[0]
